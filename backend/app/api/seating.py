"""Seating HTTP surface, split into two strictly separated entries.

写入口（可插不可改）
--------------------
* ``POST /seating/plans``          —— 只能 **新增** 一条方案行（INSERT）。
* ``POST /seating/plans/{id}/void`` —— 只能给已有行 **打作废标记**（翻转 status 位）。

写入口永不 UPDATE 已落库方案的 ``result_json`` 正文：一旦插入，正文即冻结。

只读校验入口（只读、只报分码）
------------------------------
* ``GET /seating/validate`` —— 只把某历史行的落库正文与现网考室参数比对，返回
  **漂移分码**。它不改任何历史行，也不借校验插入新方案；无方案时固定返回空结果。

间距类漂移分码与同卷类漂移分码互斥（见 :func:`seat_engine.detect_drift`）。
"""
from __future__ import annotations
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import (
    detect_drift,
    find_violations,
    place_candidates,
    plan_to_dict,
    assignments_from_body,
)

router = APIRouter(prefix="/seating", tags=["seating"])

PLAN_ACTIVE = "active"
PLAN_VOIDED = "voided"


def _get_hall(db: Session, hall_id: int) -> Hall:
    hall = db.get(Hall, hall_id)
    if hall is None:
        raise HTTPException(status_code=404, detail=f"考室 {hall_id} 不存在")
    return hall


# --------------------------------------------------------------------------- #
# 写入口：可插不可改
# --------------------------------------------------------------------------- #
@router.post("/plans")
def create_plan(hall_id: int, db: Session = Depends(get_db)):
    """新增一条排座方案行。唯一允许的正文写动作是 INSERT 一条新行。"""
    hall = _get_hall(db, hall_id)
    cands = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in db.scalars(
            select(Candidate).where(Candidate.hall_id == hall_id).order_by(Candidate.id)
        ).all()
    ]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    body = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols)

    # 只 INSERT，绝不 UPDATE 既有行正文。
    plan = SeatPlan(
        hall_id=hall.id,
        result_json=json.dumps(body, ensure_ascii=False),
        gen_rows=hall.rows,
        gen_cols=hall.cols,
        gen_min_dist=hall.min_manhattan,
        status=PLAN_ACTIVE,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"plan_id": plan.id, "status": plan.status, **body}


@router.post("/plans/{plan_id}/void")
def void_plan(plan_id: int, db: Session = Depends(get_db)):
    """给已有方案行打作废标记。只翻转 status/voided_at，result_json 正文保持冻结。"""
    plan = db.get(SeatPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"方案 {plan_id} 不存在")
    if plan.status != PLAN_VOIDED:
        plan.status = PLAN_VOIDED
        plan.voided_at = datetime.utcnow()
        db.commit()
        db.refresh(plan)
    # 明确不触碰 plan.result_json。
    return {"plan_id": plan.id, "status": plan.status}


@router.get("/plans")
def list_plans(hall_id: int, db: Session = Depends(get_db)):
    """只读列出某考室的方案行（正文摘要，不修改任何数据）。"""
    _get_hall(db, hall_id)
    plans = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id)
    ).all()
    return [
        {
            "plan_id": p.id,
            "hall_id": p.hall_id,
            "status": p.status,
            "gen_rows": p.gen_rows,
            "gen_cols": p.gen_cols,
            "gen_min_dist": p.gen_min_dist,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "voided_at": p.voided_at.isoformat() if p.voided_at else None,
        }
        for p in plans
    ]


@router.get("/plans/latest")
def latest_plan(hall_id: int, db: Session = Depends(get_db)):
    """只读返回最新生效方案的落库正文（供排座图渲染），不修改、不新增。"""
    _get_hall(db, hall_id)
    plan = db.scalars(
        select(SeatPlan)
        .where(SeatPlan.hall_id == hall_id, SeatPlan.status == PLAN_ACTIVE)
        .order_by(SeatPlan.id.desc())
    ).first()
    if plan is None:
        return {"plan_id": None, "assignments": [], "violations": []}
    body = json.loads(plan.result_json or "{}")
    return {"plan_id": plan.id, "status": plan.status, **body}


# --------------------------------------------------------------------------- #
# 只读校验入口：只报漂移分码，不改历史行，不插新方案
# --------------------------------------------------------------------------- #
@router.get("/validate")
def validate(hall_id: int, db: Session = Depends(get_db)):
    """只读校验最新生效方案相对现网参数是否漂移。

    无方案时固定返回空结果；整个处理路径只读，绝不 add/UPDATE/commit。
    """
    hall = _get_hall(db, hall_id)

    plan_count = db.scalar(
        select(func.count()).select_from(SeatPlan).where(SeatPlan.hall_id == hall_id)
    ) or 0
    plan = db.scalars(
        select(SeatPlan)
        .where(SeatPlan.hall_id == hall_id, SeatPlan.status == PLAN_ACTIVE)
        .order_by(SeatPlan.id.desc())
    ).first()

    # 无方案：固定空结果，不写库。
    if plan is None:
        return {
            "hall_id": hall.id,
            "plan_count": plan_count,
            "active_plan_id": None,
            "current_min_dist": hall.min_manhattan,
            "generated_min_dist": None,
            "drift_codes": [],
        }

    # 纯函数比对落库正文，不做任何写操作。
    assignments = assignments_from_body(plan.result_json)
    drift_codes = detect_drift(
        rows=plan.gen_rows,
        cols=plan.gen_cols,
        current_min_dist=hall.min_manhattan,
        generated_min_dist=plan.gen_min_dist,
        assignments=assignments,
    )
    return {
        "hall_id": hall.id,
        "plan_count": plan_count,
        "active_plan_id": plan.id,
        "current_min_dist": hall.min_manhattan,
        "generated_min_dist": plan.gen_min_dist,
        "drift_codes": drift_codes,
    }

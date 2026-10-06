"""排座方案的「写入口」与「只读校验入口」。

两条入口严格分离、互斥:

- 写入口(create_plan / void_plan):只能 INSERT 新方案行,或把已有行打上
  voided 作废标记。已落库的 result_json 正文一经写入,任何入口都不得
  UPDATE —— 本模块刻意不提供任何修改 result_json 的函数。
- 只读校验入口(validate_plans):纯读。若现网参数(最小曼哈顿距、行列、
  考生-试卷映射)与某历史行生成时的快照不一致,只返回漂移分码;既不修改
  该历史行,也不借校验插入新方案。「写入口可插不可改」与「校验为了变绿
  去改历史」互斥,校验绝不做写库动作。

漂移分码互斥:每条漂移记录只落一个码 ——
- MIN_DIST_DRIFT(间距类):仅由间距参数(最小曼哈顿距/行列)漂移产生;
- SAME_PAPER_DRIFT(同卷类):仅由考生-试卷套映射漂移产生。
两类判定输入不相交,间距漂移不会假报同卷码,反之亦然。
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import find_violations, place_candidates, plan_to_dict

DRIFT_MIN_DIST = "MIN_DIST_DRIFT"      # 间距类漂移码
DRIFT_SAME_PAPER = "SAME_PAPER_DRIFT"  # 同卷类漂移码
DRIFT_CODES = (DRIFT_MIN_DIST, DRIFT_SAME_PAPER)


# ---------------------------------------------------------------- 写入口

def create_plan(db: Session, hall_id: int) -> dict:
    """写入口:按现网参数排一版并 INSERT 新方案行;不触碰任何已落库行。"""
    hall = db.get(Hall, hall_id)
    if hall is None:
        raise LookupError(f"hall {hall_id} not found")
    candidates = db.scalars(
        select(Candidate).where(Candidate.hall_id == hall_id).order_by(Candidate.id)
    ).all()
    cand_dicts = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in candidates
    ]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cand_dicts)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    body = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols, hall.min_manhattan)
    plan = SeatPlan(hall_id=hall.id, result_json=json.dumps(body, ensure_ascii=False))
    db.add(plan)  # 仅 INSERT;已有行不在此函数出现
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "hall_id": plan.hall_id, "voided": plan.voided, **body}


def void_plan(db: Session, plan_id: int) -> None:
    """写入口:仅允许把 voided 作废标记置位;result_json 正文不在此函数出现。"""
    plan = db.get(SeatPlan, plan_id)
    if plan is None:
        raise LookupError(f"plan {plan_id} not found")
    plan.voided = True
    db.commit()


# -------------------------------------------------------------- 只读校验入口

def empty_report(hall_id: int) -> dict:
    """无方案时的固定空结果(校验入口约定返回值,且不写库)。"""
    return {"hall_id": hall_id, "plans_checked": 0, "drifts": []}


def validate_plans(db: Session, hall_id: int) -> dict:
    """只读校验:对每条未作废方案行,比对现网参数与生成快照,返回漂移分码。

    全程只有 SELECT —— 不 INSERT 新方案,不 UPDATE 历史行。
    """
    hall = db.get(Hall, hall_id)
    if hall is None:
        raise LookupError(f"hall {hall_id} not found")
    plans = db.scalars(
        select(SeatPlan)
        .where(SeatPlan.hall_id == hall_id, SeatPlan.voided.is_(False))
        .order_by(SeatPlan.id)
    ).all()
    if not plans:
        return empty_report(hall_id)

    current_paper = {
        c.id: c.paper_id
        for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()
    }
    drifts: list[dict] = []
    for plan in plans:
        body = json.loads(plan.result_json)
        params = body.get("params", {})
        # 间距类漂移:现网最小距/行列 与生成快照不一致 —— 只落 MIN_DIST_DRIFT
        if (
            params.get("min_manhattan") != hall.min_manhattan
            or params.get("rows") != hall.rows
            or params.get("cols") != hall.cols
        ):
            drifts.append({
                "plan_id": plan.id,
                "code": DRIFT_MIN_DIST,
                "detail": (
                    f"现网最小距/行列 ({hall.min_manhattan}, {hall.rows}x{hall.cols}) "
                    f"≠ 生成快照 ({params.get('min_manhattan')}, "
                    f"{params.get('rows')}x{params.get('cols')})"
                ),
            })
        # 同卷类漂移:考生当前试卷套与生成时快照不一致 —— 只落 SAME_PAPER_DRIFT
        changed = [
            a["candidate_id"]
            for a in body.get("assignments", [])
            if current_paper.get(a.get("candidate_id")) != a.get("paper_id")
        ]
        if changed:
            drifts.append({
                "plan_id": plan.id,
                "code": DRIFT_SAME_PAPER,
                "detail": f"考生试卷套已变更: candidate_ids={changed}",
            })
    return {"hall_id": hall_id, "plans_checked": len(plans), "drifts": drifts}


# ------------------------------------------------------------------ 只读查询

def list_plans(db: Session, hall_id: int) -> list[dict]:
    plans = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id)
    ).all()
    return [
        {
            "id": p.id,
            "hall_id": p.hall_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "voided": p.voided,
            "stats": json.loads(p.result_json).get("stats", {}),
        }
        for p in plans
    ]


def get_plan(db: Session, plan_id: int) -> dict:
    plan = db.get(SeatPlan, plan_id)
    if plan is None:
        raise LookupError(f"plan {plan_id} not found")
    return {
        "id": plan.id,
        "hall_id": plan.hall_id,
        "voided": plan.voided,
        **json.loads(plan.result_json),
    }


def latest_active_plan(db: Session, hall_id: int) -> dict | None:
    plan = db.scalars(
        select(SeatPlan)
        .where(SeatPlan.hall_id == hall_id, SeatPlan.voided.is_(False))
        .order_by(SeatPlan.id.desc())
    ).first()
    if plan is None:
        return None
    return {"id": plan.id, "hall_id": plan.hall_id, "voided": plan.voided,
            **json.loads(plan.result_json)}

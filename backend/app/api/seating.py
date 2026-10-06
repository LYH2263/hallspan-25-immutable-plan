"""排座 API:写入口(POST)与只读校验入口(GET /validate)严格分离。

- POST /plans            写入口:只 INSERT 新方案行
- POST /plans/{id}/void  写入口:只打作废标记(voided=True)
- GET  /validate         只读校验入口:只返回漂移分码,不写库、不改历史行
- GET  /plans, /plans/{id}, /violations  只读查询
已落库方案正文(result_json)没有任何端点可以 UPDATE。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import plan_store

router = APIRouter(prefix="/seating", tags=["seating"])


@router.post("/plans")
def create_plan(hall_id: int, db: Session = Depends(get_db)):
    """写入口:新增一版方案(append-only,不改历史行)。"""
    try:
        return plan_store.create_plan(db, hall_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/plans/{plan_id}/void", status_code=204)
def void_plan(plan_id: int, db: Session = Depends(get_db)):
    """写入口:仅置作废标记,正文不动。"""
    try:
        plan_store.void_plan(db, plan_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/validate")
def validate(hall_id: int, db: Session = Depends(get_db)):
    """只读校验入口:漂移分码互斥(间距类/同卷类);无方案时返回固定空结果。"""
    try:
        return plan_store.validate_plans(db, hall_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans")
def list_plans(hall_id: int, db: Session = Depends(get_db)):
    return plan_store.list_plans(db, hall_id)


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        return plan_store.get_plan(db, plan_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/violations")
def violations(hall_id: int, db: Session = Depends(get_db)):
    """最新一版未作废方案的违规清单(只读);无方案时返回固定空结果。"""
    plan = plan_store.latest_active_plan(db, hall_id)
    if plan is None:
        return {"hall_id": hall_id, "violations": []}
    return {"hall_id": hall_id, "plan_id": plan["id"], "violations": plan["violations"]}

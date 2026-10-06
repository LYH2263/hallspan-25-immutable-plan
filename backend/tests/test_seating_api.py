"""端到端：写入口可插不可改 / 校验只读只报分码 / 间距与同卷分码互斥。"""
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models.models import Hall, SeatPlan
from app.services.seat_engine import (
    DRIFT_DISTANCE,
    DRIFT_SAME_PAPER,
    detect_drift,
)


def _set_hall_min_dist(hall_id: int, value: int) -> None:
    """模拟「现网最小距」配置变更（直接改库，不走排座写入口）。"""
    db = SessionLocal()
    try:
        hall = db.get(Hall, hall_id)
        hall.min_manhattan = value
        db.commit()
    finally:
        db.close()


def _stored_body(plan_id: int) -> str:
    db = SessionLocal()
    try:
        return db.get(SeatPlan, plan_id).result_json
    finally:
        db.close()


def _plan_count() -> int:
    db = SessionLocal()
    try:
        return db.query(SeatPlan).count()
    finally:
        db.close()


def test_seed_plan_then_raise_min_dist_distance_drift_only(client: TestClient):
    # 1) 种子数据（min_dist=2）先走写入口排一版 —— 只能新增方案行。
    created = client.post("/api/seating/plans", params={"hall_id": 1})
    assert created.status_code == 200
    plan_id = created.json()["plan_id"]
    assert _plan_count() == 1
    body_before = _stored_body(plan_id)

    # 2) 改大现网最小距 2 -> 3。
    _set_hall_min_dist(1, 3)

    # 3) 走只读校验入口。
    res = client.get("/api/seating/validate", params={"hall_id": 1})
    assert res.status_code == 200
    data = res.json()

    # 出现间距漂移码……
    assert DRIFT_DISTANCE in data["drift_codes"]
    # ……且不得假报同卷码（两类分码互斥，至多一个）。
    assert DRIFT_SAME_PAPER not in data["drift_codes"]
    assert len(data["drift_codes"]) == 1
    assert data["current_min_dist"] == 3
    assert data["generated_min_dist"] == 2

    # 旧行正文不变。
    assert _stored_body(plan_id) == body_before
    # 方案条数不变（校验不借机会插入新方案）。
    assert _plan_count() == 1
    assert data["plan_count"] == 1
    assert data["active_plan_id"] == plan_id


def test_validate_with_no_plan_is_fixed_empty_and_writes_nothing(client: TestClient):
    assert _plan_count() == 0
    res = client.get("/api/seating/validate", params={"hall_id": 1})
    assert res.status_code == 200
    data = res.json()
    # 固定空结果。
    assert data["drift_codes"] == []
    assert data["active_plan_id"] is None
    assert data["generated_min_dist"] is None
    assert data["plan_count"] == 0
    # 不写库。
    assert _plan_count() == 0


def test_write_entry_inserts_but_never_overwrites_existing_body(client: TestClient):
    first = client.post("/api/seating/plans", params={"hall_id": 1}).json()
    first_id, first_body = first["plan_id"], _stored_body(first["plan_id"])

    # 再排一版：应是新增第二条，而不是 UPDATE 第一条。
    second = client.post("/api/seating/plans", params={"hall_id": 1}).json()
    assert second["plan_id"] != first_id
    assert _plan_count() == 2
    # 第一条正文保持冻结。
    assert _stored_body(first_id) == first_body


def test_void_only_flips_status_and_keeps_body_frozen(client: TestClient):
    plan_id = client.post("/api/seating/plans", params={"hall_id": 1}).json()["plan_id"]
    body_before = _stored_body(plan_id)

    res = client.post(f"/api/seating/plans/{plan_id}/void")
    assert res.status_code == 200
    assert res.json()["status"] == "voided"

    assert _stored_body(plan_id) == body_before  # 正文仍冻结
    db = SessionLocal()
    try:
        row = db.get(SeatPlan, plan_id)
        assert row.status == "voided"
        assert row.voided_at is not None
    finally:
        db.close()

    # 作废后校验固定落到空结果（无生效方案），且不新增方案。
    data = client.get("/api/seating/validate", params={"hall_id": 1}).json()
    assert data["drift_codes"] == []
    assert data["active_plan_id"] is None
    assert _plan_count() == 1


def test_drift_codes_are_mutually_exclusive_at_engine_level():
    # 两个同卷考生四邻相邻（距离 1）；现网 min_dist=2 与生成时 1 不一致。
    # 此时间距类与同卷类条件都成立，但只允许返回间距码。
    assigns = [
        {"candidate_id": 1, "paper_id": 1, "row": 0, "col": 0},
        {"candidate_id": 2, "paper_id": 1, "row": 0, "col": 1},
    ]
    codes = detect_drift(3, 3, current_min_dist=2, generated_min_dist=1, assignments=assigns)
    assert codes == [DRIFT_DISTANCE]


def test_same_paper_drift_when_distance_unchanged():
    # 参数未漂移（生成时=现网=1），但落库正文同卷四邻相邻 -> 仅同卷码。
    assigns = [
        {"candidate_id": 1, "paper_id": 1, "row": 0, "col": 0},
        {"candidate_id": 2, "paper_id": 1, "row": 0, "col": 1},
    ]
    codes = detect_drift(3, 3, current_min_dist=1, generated_min_dist=1, assignments=assigns)
    assert codes == [DRIFT_SAME_PAPER]


def test_no_drift_when_body_satisfies_current_settings():
    assigns = [
        {"candidate_id": 1, "paper_id": 1, "row": 0, "col": 0},
        {"candidate_id": 2, "paper_id": 2, "row": 0, "col": 2},
    ]
    codes = detect_drift(3, 3, current_min_dist=2, generated_min_dist=2, assignments=assigns)
    assert codes == []

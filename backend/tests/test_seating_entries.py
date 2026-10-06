"""写入口 / 只读校验入口分离的契约测试。

核心场景:种子数据 → 排一版 → 改现网最小距 → 走校验:
旧行正文不变、方案条数不变、出现间距漂移码、且不得假报同卷码。
"""
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import Candidate, Hall, SeatPlan
from app.services import plan_store
from app.services.seed import seed_if_empty


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def bodies(db):
    """从库里重新读出全部方案行 (id, result_json, voided),绕过会话缓存。"""
    db.expire_all()
    return {
        p.id: (p.result_json, p.voided)
        for p in db.scalars(select(SeatPlan).order_by(SeatPlan.id)).all()
    }


# ------------------------------------------------------------- 写入口契约

def test_write_entry_appends_only_and_never_rewrites_history(db):
    seed_if_empty(db)
    p1 = plan_store.create_plan(db, 1)
    p2 = plan_store.create_plan(db, 1)
    rows = bodies(db)
    assert len(rows) == 2  # 两次写入口 = 两行,append-only
    assert json.loads(rows[p1["id"]][0])["params"]["min_manhattan"] == 2
    assert rows[p1["id"]][0] != "" and rows[p2["id"]][0] != ""
    # 再排一版后,第一行正文与刚落库时完全一致(可插不可改)
    assert rows[p1["id"]][0] == db.get(SeatPlan, p1["id"]).result_json


def test_void_only_flips_flag_never_body(db):
    seed_if_empty(db)
    p = plan_store.create_plan(db, 1)
    before = bodies(db)[p["id"]][0]
    plan_store.void_plan(db, p["id"])
    body, voided = bodies(db)[p["id"]]
    assert voided is True          # 只允许打作废标记
    assert body == before          # 正文一字未动


def test_voided_plan_excluded_from_validation(db):
    seed_if_empty(db)
    p = plan_store.create_plan(db, 1)
    plan_store.void_plan(db, p["id"])
    db.get(Hall, 1).min_manhattan = 5
    db.commit()
    assert plan_store.validate_plans(db, 1) == plan_store.empty_report(1)


# ----------------------------------------------------------- 只读校验入口

def test_validate_empty_when_no_plans_and_writes_nothing(db):
    seed_if_empty(db)
    report = plan_store.validate_plans(db, 1)
    assert report == {"hall_id": 1, "plans_checked": 0, "drifts": []}  # 固定空结果
    assert bodies(db) == {}  # 校验不写库:没有借校验插入新方案


def test_validate_clean_when_nothing_changed(db):
    seed_if_empty(db)
    plan_store.create_plan(db, 1)
    report = plan_store.validate_plans(db, 1)
    assert report["plans_checked"] == 1
    assert report["drifts"] == []


def test_min_dist_change_yields_spacing_drift_only(db):
    """种子 → 排一版 → 改最小距 → 校验:出间距码,不假报同卷码。"""
    seed_if_empty(db)
    p = plan_store.create_plan(db, 1)
    before = bodies(db)

    hall = db.get(Hall, 1)
    hall.min_manhattan = 3  # 现网最小距变更
    db.commit()

    report = plan_store.validate_plans(db, 1)
    codes = [d["code"] for d in report["drifts"]]
    assert plan_store.DRIFT_MIN_DIST in codes          # 出现间距漂移码
    assert plan_store.DRIFT_SAME_PAPER not in codes    # 不得假报同卷码
    assert bodies(db) == before                        # 旧行正文不变、方案条数不变


def test_paper_remap_yields_same_paper_drift_only(db):
    """间距码与同卷码互斥:只改试卷映射时,不得假报间距码。"""
    seed_if_empty(db)
    plan_store.create_plan(db, 1)
    before = bodies(db)

    cand = db.scalars(select(Candidate).where(Candidate.hall_id == 1)).first()
    other = db.scalars(
        select(Candidate).where(Candidate.paper_id != cand.paper_id)
    ).first()
    cand.paper_id = other.paper_id  # 考生-试卷映射变更
    db.commit()

    report = plan_store.validate_plans(db, 1)
    codes = [d["code"] for d in report["drifts"]]
    assert plan_store.DRIFT_SAME_PAPER in codes
    assert plan_store.DRIFT_MIN_DIST not in codes
    assert bodies(db) == before  # 校验依旧一字未写


def test_drift_codes_are_mutually_exclusive_per_record(db):
    """每条漂移记录只落一个码,且码值必在互斥码表内。"""
    seed_if_empty(db)
    plan_store.create_plan(db, 1)
    hall = db.get(Hall, 1)
    hall.min_manhattan = 4
    cand = db.scalars(select(Candidate).where(Candidate.hall_id == 1)).first()
    cand.paper_id = -1  # 映射到一个不存在的试卷套,必然构成同卷漂移
    db.commit()

    report = plan_store.validate_plans(db, 1)
    assert report["drifts"], "两种漂移同时存在时也应分别成码"
    for d in report["drifts"]:
        assert d["code"] in plan_store.DRIFT_CODES
        assert set(d.keys()) == {"plan_id", "code", "detail"}

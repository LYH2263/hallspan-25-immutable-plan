# HallSpan 考场排座

考室网格排座系统:FastAPI + PostgreSQL 后端,Vue 3 + Vite 前端。
排座规则:任意两考生曼哈顿距离 ≥ 考室最小间距;同试卷套考生不得四邻相邻。

## 快速开始

```bash
docker compose up --build   # 前端 :4900,API :9900,Postgres :5450
cd backend && pytest        # 后端测试(纯内存 SQLite,无需 Postgres)
```

## 排座方案的两条入口(严格分离)

| 入口 | 端点 | 语义 |
| --- | --- | --- |
| 写入口 | `POST /api/seating/plans?hall_id=N` | 只 **INSERT** 新方案行(append-only) |
| 写入口 | `POST /api/seating/plans/{id}/void` | 只把已有行打上 `voided` 作废标记 |
| 只读校验入口 | `GET /api/seating/validate?hall_id=N` | 只返回漂移分码,**不写库** |

- 已落库的方案正文(`result_json`)一经写入,任何端点都不得 UPDATE ——
  「写入口可插不可改」与「校验为了变绿去改历史」互斥。
- 每行方案落库时带生成参数快照(`params`:最小间距/行列),校验入口用它
  与现网参数比对,只回分码、不改历史行、也不借校验插入新方案。
- 无方案时校验返回固定空结果
  `{"hall_id": N, "plans_checked": 0, "drifts": []}`,且不写库。

### 漂移分码(互斥)

| 分码 | 类别 | 触发条件 |
| --- | --- | --- |
| `MIN_DIST_DRIFT` | 间距类 | 现网最小间距/行列 ≠ 生成快照 |
| `SAME_PAPER_DRIFT` | 同卷类 | 考生当前试卷套 ≠ 生成时快照 |

每条漂移记录只落一个码,两类判定输入不相交,不会互相假报。

## 目录

```
backend/
  app/api/         路由(seating.py 为写/校验入口)
  app/services/    seat_engine.py 纯排座算法;plan_store.py 入口语义
  app/models/      SQLAlchemy 模型(SeatPlan 含 voided 作废标记)
  tests/           引擎测试 + 入口分离契约测试
frontend/src/      Vue 视图(排座图 / 违规与漂移 / 统计 等)
```

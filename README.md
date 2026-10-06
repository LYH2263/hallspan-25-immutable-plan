# HallSpan 考场排座

最小曼哈顿间距约束下的考场排座服务，FastAPI + SQLAlchemy + Vue 3。

## 排座写入口 vs 只读校验入口（严格分离）

写入口遵循「**可插不可改**」：

- `POST /api/seating/plans` —— 只能 **新增** 一条方案行（INSERT）。
- `POST /api/seating/plans/{id}/void` —— 只能给已有行 **打作废标记**（翻转 `status`）。

一旦方案行落库，其 `result_json` 正文即冻结，写入口永不 UPDATE 正文。

只读校验入口「**只报分码**」：

- `GET /api/seating/validate?hall_id=...` —— 把某历史行的落库正文与现网考室
  参数比对，仅返回漂移分码。**不改历史行，也不借校验插入新方案。**
- 无方案时固定返回空结果（`drift_codes: []`），且不写库。

漂移分码两类**互斥**（至多返回一个）：

- `DRIFT_DISTANCE`：间距类漂移 —— 现网最小距与该历史行生成时不一致，且旧行正文
  里确有更近的座位对。
- `DRIFT_SAME_PAPER`：同卷类漂移 —— 同试卷套四邻相邻。

间距类优先；命中间距类时不再报同卷类，避免「改大最小距」假报同卷码。

## 本地运行

```bash
docker compose up --build
# API: http://localhost:9900  前端: http://localhost:4900
```

后端测试：

```bash
cd backend && python -m pytest
```

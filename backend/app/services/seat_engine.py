"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent.

Drift codes (mutually exclusive — at most one is ever returned for a plan):
  * ``DRIFT_DISTANCE``  — 间距类漂移: 现网最小距与该历史行生成时不一致，落库座位
    正文中已存在小于现网最小距的座位对。
  * ``DRIFT_SAME_PAPER`` — 同卷类漂移: 落库座位正文中存在同试卷套四邻相邻。

两类分码互斥：间距类优先。一旦命中间距类，绝不再报同卷类，避免「改大最小距」
时把结构性的相邻误报成同卷漂移。
"""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass

# 漂移分码常量
DRIFT_DISTANCE = "DRIFT_DISTANCE"
DRIFT_SAME_PAPER = "DRIFT_SAME_PAPER"

@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int

@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str

def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out

def place_candidates(rows: int, cols: int, min_dist: int, candidates: list[dict]) -> tuple[list[SeatAssign], list[dict]]:
    """Greedy: try seats row-major; accept if manhattan >= min_dist to all placed AND no same paper 4-neigh."""
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied:
                    continue
                ok = True
                for pos, other in occupied.items():
                    if manhattan((r, c), pos) < min_dist:
                        ok = False
                        break
                    if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                        ok = False
                        break
                if not ok:
                    continue
                # also check 4-neigh same paper against current neighbors
                for nr, nc in neighbors4(r, c, rows, cols):
                    if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                        ok = False
                        break
                if not ok:
                    continue
                assign = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
                occupied[(r, c)] = assign
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(cand)
    return list(occupied.values()), unplaced

def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    viols: list[Violation] = []
    by_pos = {(a.row, a.col): a for a in assigns}
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols

def plan_to_dict(assigns: list[SeatAssign], unplaced: list[dict], viols: list[Violation], rows: int, cols: int) -> dict:
    return {
        "rows": rows,
        "cols": cols,
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": rows * cols,
        },
    }


def assignments_from_body(result_json: str) -> list[dict]:
    """Extract the seat-assignment records from a *stored* plan body (read-only)."""
    try:
        body = json.loads(result_json or "{}")
    except (TypeError, ValueError):
        return []
    assignments = body.get("assignments")
    return list(assignments) if isinstance(assignments, list) else []


def _has_distance_violation(min_dist: int, assigns: list[dict]) -> bool:
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            if manhattan((a["row"], a["col"]), (b["row"], b["col"])) < min_dist:
                return True
    return False


def _has_same_paper_adjacent(rows: int, cols: int, assigns: list[dict]) -> bool:
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            if a.get("paper_id") == b.get("paper_id") and (
                (b["row"], b["col"]) in neighbors4(a["row"], a["col"], rows, cols)
            ):
                return True
    return False


def detect_drift(
    rows: int,
    cols: int,
    current_min_dist: int,
    generated_min_dist: int | None,
    assignments: list[dict],
) -> list[str]:
    """Pure read-only drift check of a *historical* plan body vs. current hall settings.

    Returns the mutually-exclusive drift codes (at most one). Never mutates input and
    performs no I/O. Distance drift takes precedence over same-paper drift.
    """
    # 间距类漂移：现网最小距与生成时不一致，且旧行正文里确有更近的座位对。
    params_differ = generated_min_dist is not None and current_min_dist != generated_min_dist
    if params_differ and _has_distance_violation(current_min_dist, assignments):
        return [DRIFT_DISTANCE]
    # 只有在未命中间距类时，才评估同卷类 —— 两类分码互斥。
    if _has_same_paper_adjacent(rows, cols, assignments):
        return [DRIFT_SAME_PAPER]
    return []

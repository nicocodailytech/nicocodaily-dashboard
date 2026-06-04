#!/usr/bin/env python3
"""Build dashboard data.json by parsing 派工看板.md (the orchestration board).

Single source of truth: ~/nicocodaily-brain/派工看板.md (see CLAUDE.md 鐵則).
No Notion, no network — pure stdlib markdown parsing so it runs identically on
the VPS and inside the GitHub Pages Action (which gets a synced copy of the md
in the same directory as this script).

Board path resolution order:
  1. $BOARD_PATH env
  2. ./派工看板.md  (synced copy next to this script — used in CI)
  3. ../../派工看板.md  (brain repo root — used on the VPS)
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find_board():
    env = os.environ.get("BOARD_PATH")
    candidates = [Path(env)] if env else []
    candidates += [HERE / "派工看板.md", HERE.parent.parent / "派工看板.md"]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "派工看板.md not found. Set BOARD_PATH or place it next to fetch_data.py. "
        f"Looked in: {[str(c) for c in candidates]}"
    )


# Status emoji -> (tag, human label). Order matters: check most-specific first.
STATUS_MAP = [
    ("🟢🟢", "live",    "已上線"),
    ("🟢",   "live",    "運行中"),
    ("🟡",   "partial", "部分完成"),
    ("🔵",   "scoping", "規劃中"),
    ("🔴",   "urgent",  "需處理"),
    ("✅",   "done",    "完成"),
    ("❌",   "killed",  "已廢除"),
    ("⏸️",   "paused",  "暫停"),
    ("⏸",    "paused",  "暫停"),
]


def classify(status_cell):
    for emoji, tag, label in STATUS_MAP:
        if emoji in status_cell:
            return emoji, tag, label
    return "", "none", ""


def split_rows(cell_line):
    # "| a | b | c |" -> ["a", "b", "c"]
    parts = [c.strip() for c in cell_line.strip().strip("|").split("|")]
    return parts


def is_separator(cells):
    return all(re.fullmatch(r":?-+:?", c or "-") for c in cells)


def parse(md_path):
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # ── frontmatter ──
    board_updated = ""
    maintainer = ""
    fm = re.search(r"^---\n(.*?)\n---", text, re.S | re.M)
    if fm:
        for ln in fm.group(1).splitlines():
            if ln.startswith("updated:"):
                board_updated = ln.split(":", 1)[1].strip()
            elif ln.startswith("maintainer:"):
                maintainer = ln.split(":", 1)[1].strip()

    # ── walk sections ──
    section = None
    projects = []
    pending_user = []
    priorities = []
    snapshot = []
    builder_lines = []
    coco_line = ""

    for ln in lines:
        h = re.match(r"^##\s+(.*)$", ln)
        if h:
            title = h.group(1)
            if "全專案狀態" in title:
                section = "projects"
            elif "待用戶" in title:
                section = "pending"
            elif "開工優先" in title:
                section = "priorities"
            elif "進度快照" in title:
                section = "snapshot"
            elif "小建" in title:
                section = "builder"
            elif "可可" in title:
                section = "coco"
                coco_line = re.sub(r"^[🐚\s]*(可可[:：])?", "", title).strip()
            else:
                section = None
            continue

        s = ln.strip()
        if section == "projects" and s.startswith("|"):
            cells = split_rows(ln)
            if len(cells) < 4:
                continue
            if is_separator(cells):
                continue
            if not re.match(r"^\d+$", cells[0]):  # header row ("#")
                continue
            status_cell = cells[3]
            emoji, tag, label = classify(status_cell)
            projects.append({
                "num": int(cells[0]),
                "name": cells[1],
                "window": cells[2],
                "status_text": status_cell,
                "status_emoji": emoji,
                "status_tag": tag,
                "status_label": label,
            })
        elif section == "pending" and s.startswith("- "):
            pending_user.append(s[2:].strip())
        elif section == "priorities":
            m = re.match(r"^\d+\.\s+(.*)$", s)
            if m:
                priorities.append(m.group(1).strip())
        elif section == "snapshot" and s.startswith("- "):
            snapshot.append(s[2:].strip())
        elif section == "builder" and s.startswith("- "):
            builder_lines.append(s[2:].strip())

    # ── team (real current roster, not the dead Mac/MiniMax) ──
    xiaojian_state = next(
        (b for b in builder_lines if "跑中" in b or "feat/" in b),
        builder_lines[0] if builder_lines else "待命",
    )
    team = [
        {"name": "L1 Windows Claude", "role": "決策 / 派工 / 審 code", "level": "L1", "state": "在主窗"},
        {"name": "小建 (VPS)", "role": "L2 雲端工程 · 24/7", "level": "L2", "state": xiaojian_state},
        {"name": "可可", "role": "LINE 倉助", "level": "OPS", "state": coco_line or "LINE 倉助上線"},
    ]

    # ── glance stats ──
    counts = {}
    for p in projects:
        counts[p["status_tag"]] = counts.get(p["status_tag"], 0) + 1
    stats = {
        "pending_user": len(pending_user),
        "live": counts.get("live", 0),
        "scoping": counts.get("scoping", 0),
        "done": counts.get("done", 0),
        "urgent": counts.get("urgent", 0),
        "total": len(projects),
    }

    now_tz = datetime.now(timezone(timedelta(hours=8)))
    return {
        "generated_at": now_tz.isoformat(),
        "board_updated": board_updated,
        "maintainer": maintainer,
        "stats": stats,
        "projects": projects,
        "pending_user": pending_user,
        "priorities": priorities,
        "snapshot": snapshot,
        "team": team,
    }


def main():
    board = find_board()
    data = parse(board)
    out = HERE / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"data.json built from {board.name}: "
        f"{data['stats']['total']} projects, "
        f"{data['stats']['pending_user']} pending-user items, "
        f"board updated {data['board_updated']}"
    )


if __name__ == "__main__":
    main()

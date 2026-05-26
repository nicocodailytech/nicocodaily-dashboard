#!/usr/bin/env python3
"""Fetch Notion task data for NICOCODAILY Dashboard."""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DATABASE_ID = "ea19337c2d8540fb8948f52a5bd16ca0"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

PROJECTS = [
    {"num": 1,  "name": "快速生圖",       "status": "運行中",   "executor": "Mac Claude",     "desc": "圖片生成 API，內容生產管線"},
    {"num": 2,  "name": "發布",           "status": "過渡中",   "executor": "Mac Claude",     "desc": "待併入 #5 剪片+發布"},
    {"num": 3,  "name": "MiniMax 倉庫",   "status": "運行中",   "executor": "MiniMax",        "desc": "CF Worker 橋接，QDM↔GW webhook"},
    {"num": 4,  "name": "NICOCHAT",       "status": "進行中",   "executor": "Mobile Claude",  "desc": "客服/CRM 層，AI 客服助理"},
    {"num": 5,  "name": "剪片+發布",      "status": "規劃中",   "executor": "Mac Claude",     "desc": "剪片自動化 + 社群發布"},
    {"num": 6,  "name": "VTO 換衣",       "status": "0%",       "executor": "Windows Claude", "desc": "虛擬試穿，成長工具層"},
    {"num": 7,  "name": "採購彙整",       "status": "0%",       "executor": "MiniMax",        "desc": "接 LINE/倉庫系統"},
    {"num": 8,  "name": "AI 投資",        "status": "待定",     "executor": "Windows Claude", "desc": "高風險，需人工監督"},
    {"num": 9,  "name": "AI 廣告投放",    "status": "規劃中",   "executor": "Windows Claude", "desc": "Meta API，成長工具層"},
    {"num": 10, "name": "爬蟲市調",       "status": "完成",     "executor": "Mac Claude",     "desc": "nicocodaily.com 202 連結已分析"},
    {"num": 11, "name": "TG 情報入口",    "status": "完成",     "executor": "Mac Claude",     "desc": "Telegram Bot 摘要分類路由"},
    {"num": 12, "name": "系統整合",       "status": "進行中",   "executor": "Windows Claude", "desc": "L1/L2/L3 架構建設"},
    {"num": 13, "name": "AI 藝術庫",      "status": "規劃中",   "executor": "Mac Claude",     "desc": "收集背景/模特兒/服飾素材"},
]


def query_all_tasks():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_results = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = requests.post(url, headers=HEADERS, json=body, timeout=15)
        data = res.json()
        all_results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return all_results


def query_recent_activity(limit=10):
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    body = {
        "page_size": limit,
        "filter": {"or": [
            {"property": "狀態", "select": {"equals": "完成"}},
            {"property": "狀態", "select": {"equals": "失敗"}},
        ]},
        "sorts": [{"property": "完成時間", "direction": "descending"}],
    }
    res = requests.post(url, headers=HEADERS, json=body, timeout=15)
    return res.json().get("results", [])


def get_prop_text(props, key):
    prop = props.get(key, {})
    ptype = prop.get("type", "")
    if ptype == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    if ptype == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    if ptype == "select":
        sel = prop.get("select") or {}
        return sel.get("name", "")
    if ptype == "date":
        dt = prop.get("date") or {}
        return dt.get("start", "")
    return ""


def main():
    now_tz = datetime.now(timezone(timedelta(hours=8)))

    tasks = query_all_tasks()
    from collections import Counter
    status_counts = Counter()
    today = now_tz.strftime("%Y-%m-%d")
    completed_today = 0

    for t in tasks:
        p = t["properties"]
        status = get_prop_text(p, "狀態")
        status_counts[status] += 1
        if status == "完成":
            dt = get_prop_text(p, "完成時間")
            if dt and dt.startswith(today):
                completed_today += 1

    activity_raw = query_recent_activity(10)
    activity = []
    for t in activity_raw:
        p = t["properties"]
        title = get_prop_text(p, "任務")
        status = get_prop_text(p, "狀態")
        executor = get_prop_text(p, "執行者")
        date = get_prop_text(p, "完成時間")
        if title:
            activity.append({
                "title": title,
                "status": status,
                "executor": executor,
                "date": date,
            })

    data = {
        "updated_at": now_tz.isoformat(),
        "tasks": {
            "pending": status_counts.get("待執行", 0),
            "in_progress": status_counts.get("進行中", 0),
            "failed": status_counts.get("失敗", 0),
            "completed_today": completed_today,
            "completed_total": status_counts.get("完成", 0),
        },
        "projects": PROJECTS,
        "activity": activity,
    }

    out = Path(__file__).parent / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"data.json updated: pending={data['tasks']['pending']} "
          f"in_progress={data['tasks']['in_progress']} "
          f"failed={data['tasks']['failed']} "
          f"completed={data['tasks']['completed_total']}")


if __name__ == "__main__":
    main()

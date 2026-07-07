#!/usr/bin/env python3
"""Tests for xueqiu-investor-activity."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xueqiu_activity.py"


def test_collect_watchlist_csv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "watchlist.csv"
        out = root / "out"
        csv_path.write_text("type,code,name,group,note\nwatchlist,600519,贵州茅台,白酒,长期观察\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(csv_path), "--out-dir", str(out), "--collected-at", "2026-07-07T15:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        event = json.loads((out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["schema"] == "collectorx.event.v1"
        assert event["kind"] == "watchlist"
        assert event["data"]["symbol"] == "600519"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["xueqiu_is_strong_trade_source"] is False


def test_collect_posts_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "activities.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                [
                    {"type": "post", "title": "复盘", "text": "今天减仓新能源，原因是估值和成交量。", "created_at": "2026-07-07T10:00:00+08:00"},
                    {"type": "follow_user", "screen_name": "某研究员", "url": "https://xueqiu.com/u/1"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out)], check=True, text=True, capture_output=True)
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["kind"] for event in events] == ["note", "profile"]


if __name__ == "__main__":
    test_collect_watchlist_csv()
    test_collect_posts_json()
    print("xueqiu-investor-activity tests passed.")

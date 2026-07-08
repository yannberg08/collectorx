#!/usr/bin/env python3
"""Tests for the SoulMirror TickTick collector entrypoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "collect_for_soulmirror.py"
REPO_ROOT = ROOT.parents[2]
COLLECTOR_YAML = REPO_ROOT / "collectors" / "generic" / "ticktick.yaml"
SKILL_MD = ROOT.parent / "SKILL.md"


def test_missing_auth_fails_without_empty_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "HOME": tmp,
        }
        env.pop("TICKTICK_TOKEN", None)
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            text=True,
            capture_output=True,
            env=env,
        )
        assert result.returncode == 12
        assert result.stdout.strip() == ""
        payload = json.loads(result.stderr)
        assert payload["ok"] is False
        assert payload["error"] == "ticktick_auth_required"


def test_authorized_snapshot_collects_active_and_completed_tasks() -> None:
    seen_auth: list[str | None] = []
    seen_payloads: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _json(self, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_payload(self) -> dict:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return json.loads(raw.decode("utf-8") or "{}")

        def do_GET(self) -> None:  # noqa: N802
            seen_auth.append(self.headers.get("Authorization"))
            if self.path == "/project":
                self._json([{"id": "p-research", "name": "投研任务"}])
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            seen_auth.append(self.headers.get("Authorization"))
            payload = self._read_payload()
            seen_payloads.append(payload)
            if self.path == "/task/filter":
                self._json(
                    [
                        {
                            "id": "t-active",
                            "projectId": "p-research",
                            "title": "复盘宁德时代交易",
                            "dueDate": "2026-07-09T09:00:00+0800",
                            "timeZone": "Asia/Shanghai",
                            "repeatFlag": "RRULE:FREQ=WEEKLY;BYDAY=TH",
                            "reminders": ["TRIGGER:PT30M"],
                            "status": 0,
                            "priority": 3,
                            "tags": ["复盘"],
                            "items": [
                                {"id": "i-1", "title": "检查买入理由", "status": 1},
                                {"id": "i-2", "title": "复核仓位", "status": 0},
                            ],
                        },
                        {
                            "id": "t-inbox",
                            "projectId": "inbox123",
                            "title": "看基金季报",
                            "startDate": "2026-07-10T10:00:00+0800",
                            "status": 0,
                        },
                    ]
                )
                return
            if self.path == "/task/completed":
                self._json(
                    [
                        {
                            "id": "t-active",
                            "projectId": "p-research",
                            "title": "复盘宁德时代交易",
                            "completedTime": "2026-07-08T20:00:00+0800",
                            "status": 2,
                        },
                        {
                            "id": "t-done",
                            "projectId": "p-research",
                            "title": "归档上周交易计划",
                            "completedTime": "2026-07-08T21:00:00+0800",
                            "status": 2,
                        },
                    ]
                )
                return
            self.send_response(404)
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            **os.environ,
            "TICKTICK_TOKEN": "test-token",
            "TICKTICK_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}",
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--completed-limit", "25"],
            text=True,
            capture_output=True,
            env=env,
            check=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    records = json.loads(result.stdout)
    assert result.stderr.strip() == ""
    assert len(records) == 3
    assert [record["id"] for record in records] == ["ticktick:t-active", "ticktick:t-inbox", "ticktick:t-done"]
    assert records[0]["project"] == "投研任务"
    assert records[0]["due"] == "2026-07-09T09:00:00+0800"
    assert records[0]["timeZone"] == "Asia/Shanghai"
    assert records[0]["repeat"] == "RRULE:FREQ=WEEKLY;BYDAY=TH"
    assert records[0]["reminders"] == ["TRIGGER:PT30M"]
    assert records[0]["checklistTotal"] == 2
    assert records[0]["checklistCompleted"] == 1
    assert records[0]["data"]["sourceBucket"] == "active"
    assert records[1]["project"] == "收件箱"
    assert records[2]["data"]["sourceBucket"] == "completed"
    assert "test-token" not in result.stdout
    assert all(auth == "Bearer test-token" for auth in seen_auth)
    assert {"status": [0]} in seen_payloads
    assert {} in seen_payloads


def test_soulmirror_prompt_keeps_auth_out_of_collection() -> None:
    collector_text = COLLECTOR_YAML.read_text(encoding="utf-8")
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    collector_flat = " ".join(collector_text.split())

    assert "apiVersion: soulmirror/v1" in collector_text
    assert "do not start an OAuth flow" in collector_flat
    assert "do not run auth.py connect / register / authorize" in collector_flat
    assert "Do not write an error object into the result file" in collector_flat
    assert "TICKTICK_AUTH_REQUIRED" in collector_text
    assert "COLLECTED <number-of-records>" in collector_text

    assert "SoulMirror 定时/立即采集阶段只允许检查授权状态和读取任务" in skill_text
    assert "错误对象只会出现在" in skill_text
    assert "不得把它写进 snapshot/result file" in skill_text


if __name__ == "__main__":
    test_missing_auth_fails_without_empty_snapshot()
    test_authorized_snapshot_collects_active_and_completed_tasks()
    test_soulmirror_prompt_keeps_auth_out_of_collection()
    print("ticktick SoulMirror collector tests passed.")

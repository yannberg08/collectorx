#!/usr/bin/env python3
"""Tests for the FinClaw batch runner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/run_finclaw_batch.py", *args],
        cwd=str(ROOT),
        text=True,
        check=False,
        capture_output=True,
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def fake_writer_code() -> str:
    return """
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
collector = sys.argv[2]
event_dir = out / "lake" / collector
event_dir.mkdir(parents=True, exist_ok=True)
event = {
    "schema": "collectorx.event.v1",
    "id": collector + "-event-1",
    "collector": collector,
    "source": "fixture",
    "owner_scope": "user",
    "kind": "other",
    "time": "2026-07-08T00:00:00+08:00",
    "collected_at": "2026-07-08T00:00:00+08:00",
    "data": {"ok": True},
    "raw_ref": {"type": "fixture"},
    "privacy": {"sensitive": False, "local_only": True},
}
(event_dir / "events.jsonl").write_text(json.dumps(event, ensure_ascii=False) + "\\n", encoding="utf-8")
(out / "manifest.json").write_text(
    json.dumps({"collector": collector, "event_count": 1}, ensure_ascii=False),
    encoding="utf-8",
)
"""


def build_manifest(out_dir: Path, *, command_argv: list[str] | None = None) -> dict[str, object]:
    argv = command_argv or [sys.executable, "-c", fake_writer_code(), str(out_dir), "fake"]
    return {
        "schema": "collectorx.finclaw_batch_manifest.v1",
        "runbook_schema": "collectorx.finclaw_runbook.v1",
        "summary": {
            "total": 1,
            "ready_steps": 1,
            "blocked_steps": 0,
            "by_stage": {"ready_collectors": 1},
        },
        "auto_upstream_links": [],
        "ready_steps": [
            {
                "step": 1,
                "id": "fake",
                "stage": "ready_collectors",
                "priority": "P0",
                "category": "vertical",
                "runner": "command",
                "argv": argv,
                "display_command": "fixture",
                "depends_on": [],
                "output_dir": str(out_dir),
                "lake_events_jsonl": str(out_dir / "lake" / "fake" / "events.jsonl"),
                "post_run_validation": {
                    "ready": True,
                    "argv": [
                        sys.executable,
                        "tools/validate_collector_package.py",
                        str(out_dir),
                        "--collector",
                        "fake",
                        "--json",
                    ],
                    "command": "fixture validation",
                    "require_evidence": False,
                },
            }
        ],
        "blocked_steps": [],
    }


def test_dry_run_does_not_execute_steps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "manifest.json"
        out_dir = tmp_path / "out"
        manifest = build_manifest(out_dir, command_argv=[sys.executable, "-c", "raise SystemExit(99)"])
        write_json(manifest_path, manifest)
        proc = run_runner("--manifest", str(manifest_path), "--json")
        assert proc.returncode == 0, proc.stderr or proc.stdout
        report = json.loads(proc.stdout)
        assert report["schema"] == "collectorx.finclaw_batch_run_report.v1"
        assert report["mode"] == "dry_run"
        assert report["summary"]["attempted_steps"] == 0
        assert report["steps"][0]["status"] == "dry_run"
        assert not out_dir.exists()


def test_execute_runs_step_and_post_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "manifest.json"
        out_dir = tmp_path / "out"
        write_json(manifest_path, build_manifest(out_dir))
        proc = run_runner("--manifest", str(manifest_path), "--execute", "--json")
        assert proc.returncode == 0, proc.stderr or proc.stdout
        report = json.loads(proc.stdout)
        assert report["mode"] == "execute"
        assert report["summary"]["attempted_steps"] == 1
        assert report["summary"]["succeeded_steps"] == 1
        assert report["steps"][0]["status"] == "success"
        assert report["steps"][0]["post_run_validation"]["status"] == "success"
        assert (out_dir / "lake" / "fake" / "events.jsonl").exists()


def test_execute_stops_on_failed_step() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "manifest.json"
        out_dir = tmp_path / "out"
        manifest = build_manifest(out_dir, command_argv=[sys.executable, "-c", "raise SystemExit(7)"])
        write_json(manifest_path, manifest)
        proc = run_runner("--manifest", str(manifest_path), "--execute", "--json")
        assert proc.returncode == 1
        report = json.loads(proc.stdout)
        assert report["summary"]["attempted_steps"] == 1
        assert report["summary"]["failed_steps"] == 1
        assert report["steps"][0]["status"] == "failed"
        assert report["steps"][0]["exit_code"] == 7
        assert report["steps"][0]["post_run_validation"]["status"] == "skipped_after_failed_step"


def test_execute_requires_ready_post_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "manifest.json"
        out_dir = tmp_path / "out"
        manifest = build_manifest(out_dir)
        manifest["ready_steps"][0]["post_run_validation"] = {
            "ready": False,
            "argv": [],
            "command": None,
            "require_evidence": False,
        }
        write_json(manifest_path, manifest)
        proc = run_runner("--manifest", str(manifest_path), "--execute", "--json")
        assert proc.returncode == 1
        report = json.loads(proc.stdout)
        assert report["summary"]["failed_steps"] == 1
        assert report["steps"][0]["status"] == "validation_not_ready"
        assert report["steps"][0]["post_run_validation"]["status"] == "not_ready"


def test_catalog_p0_dry_run_report_keeps_blocked_steps() -> None:
    proc = run_runner("--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--json")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    report = json.loads(proc.stdout)
    assert report["mode"] == "dry_run"
    assert report["summary"]["ready_steps"] == 6
    assert report["summary"]["blocked_steps"] == 6
    assert len(report["steps"]) == 6
    assert all(step["status"] == "dry_run" for step in report["steps"])


def test_require_all_ready_fails_when_blocked_steps_remain() -> None:
    proc = run_runner("--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--require-all-ready", "--json")
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    assert report["summary"]["blocked_steps"] == 6


def main() -> int:
    test_dry_run_does_not_execute_steps()
    test_execute_runs_step_and_post_validation()
    test_execute_stops_on_failed_step()
    test_execute_requires_ready_post_validation()
    test_catalog_p0_dry_run_report_keeps_blocked_steps()
    test_require_all_ready_fails_when_blocked_steps_remain()
    print("finclaw batch runner tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

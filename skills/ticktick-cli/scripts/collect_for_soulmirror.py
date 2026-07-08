#!/usr/bin/env python3
"""Export TickTick tasks as a SoulMirror collector JSON array.

This script is intentionally dependency-light so the collector can run it without
installing Typer/Pydantic first. It exits non-zero when auth is missing, instead
of returning [] and making the dashboard look falsely healthy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.dida365.com/open/v1"
TOKEN_FILE = Path.home() / ".covo" / "ticktick.json"
SCOPE = "tasks:write tasks:read"


def load_token() -> str | None:
    token = os.environ.get("TICKTICK_TOKEN")
    if token and token.strip():
        return token.strip()
    try:
        payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    token = payload.get("access_token")
    return token.strip() if isinstance(token, str) and token.strip() else None


def request_json(token: str, method: str, path: str, payload: Any = None, base_url: str = DEFAULT_BASE_URL) -> Any:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "ticktick-cli/soulmirror-collector",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {body}") from exc
    return json.loads(raw) if raw.strip() else None


def list_active_tasks(token: str, base_url: str) -> list[dict[str, Any]]:
    payload = request_json(token, "POST", "task/filter", {"status": [0]}, base_url=base_url)
    return payload if isinstance(payload, list) else []


def list_completed_tasks(token: str, base_url: str, limit: int) -> list[dict[str, Any]]:
    payload = request_json(token, "POST", "task/completed", {}, base_url=base_url)
    tasks = payload if isinstance(payload, list) else []
    return tasks[:limit] if limit >= 0 else tasks


def list_projects(token: str, base_url: str) -> list[dict[str, Any]]:
    payload = request_json(token, "GET", "project", base_url=base_url)
    return payload if isinstance(payload, list) else []


def to_record(task: dict[str, Any], project_names: dict[str, str], bucket: str) -> dict[str, Any]:
    task_id = task.get("id")
    project_id = task.get("projectId")
    project_name = project_names.get(str(project_id)) or (
        "收件箱" if str(project_id or "").startswith("inbox") else project_id
    )
    data = dict(task)
    data["projectName"] = project_name
    data["sourceBucket"] = bucket
    return {
        "id": f"ticktick:{task_id}" if task_id else None,
        "title": task.get("title"),
        "due": task.get("dueDate") or task.get("startDate"),
        "project": project_name,
        "projectId": project_id,
        "status": task.get("status"),
        "priority": task.get("priority"),
        "tags": task.get("tags"),
        "data": data,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-limit", type=int, default=500)
    parser.add_argument("--no-completed", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("TICKTICK_BASE_URL", DEFAULT_BASE_URL))
    args = parser.parse_args()

    token = load_token()
    if not token:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "ticktick_auth_required",
                    "message": "滴答清单未连接。请先通过产品里的“连接滴答清单”完成一次授权。",
                    "token_file": str(TOKEN_FILE),
                    "managed_oauth_env": "TICKTICK_OAUTH_BROKER_URL",
                    "scope": SCOPE,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 12

    projects = list_projects(token, args.base_url)
    project_names = {
        str(item.get("id")): str(item.get("name"))
        for item in projects
        if item.get("id") and item.get("name")
    }

    records = [to_record(task, project_names, "active") for task in list_active_tasks(token, args.base_url)]
    if not args.no_completed:
        records.extend(
            to_record(task, project_names, "completed")
            for task in list_completed_tasks(token, args.base_url, args.completed_limit)
        )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = record.get("id") or json.dumps(record.get("data"), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    print(json.dumps(deduped, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

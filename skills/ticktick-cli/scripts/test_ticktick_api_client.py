#!/usr/bin/env python3
"""Focused tests for TickTick OpenAPI request shapes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ticktick_api_client import TicktickApiClient  # noqa: E402


def make_json_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.text = json.dumps(payload, ensure_ascii=False)
    response.content = response.text.encode("utf-8")
    response.headers = {"Content-Type": "application/json"}
    response.json = lambda: payload
    return response


def test_completed_tasks_use_documented_date_fields_and_local_limit() -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=make_json_response(
            [
                {"id": "done-1", "projectId": "p1", "title": "复盘A", "status": 2},
                {"id": "done-2", "projectId": "p1", "title": "复盘B", "status": 2},
            ]
        )
    )
    client = TicktickApiClient(token="test-token", base_url="https://api.dida365.com/open/v1", session=session)

    tasks = client.list_completed_tasks(
        completed_time_from="2026-07-01T00:00:00+0800",
        completed_time_to="2026-07-08T23:59:59+0800",
        limit=1,
    )

    assert [task.id for task in tasks] == ["done-1"]
    request_kwargs = session.request.call_args.kwargs
    assert request_kwargs["method"] == "POST"
    assert request_kwargs["url"].endswith("/task/completed")
    assert request_kwargs["json"] == {
        "startDate": "2026-07-01T00:00:00+0800",
        "endDate": "2026-07-08T23:59:59+0800",
    }
    assert "limit" not in request_kwargs["json"]


if __name__ == "__main__":
    test_completed_tasks_use_documented_date_fields_and_local_limit()
    print("ticktick api client tests passed.")

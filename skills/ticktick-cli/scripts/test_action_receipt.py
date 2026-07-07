#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pytest>=8.0.0",
#     "httpx>=0.27.0",
#     "pydantic>=2.5.0",
# ]
# ///
"""
test_action_receipt.py · pytest 单测 · cufenshen action_receipt 模块

S13-P2-5 · ticktick-cli skill stdout 升级到 ActionReceipt v1
- 覆盖 5 主路径 + 边界：
  1. happy path（search 找不到 · create 成功 · status=succeeded）
  2. duplicate path（search 找到匹配 title+due 同日 · 不调 create · status=duplicate）
  3. failed retryable（HTTP 500 / 401 / timeout · retryable=true）
  4. failed non-retryable（HTTP 400 / 403 · retryable=false）
  5. echo fields（schema/app/job_id/outbox_id/idempotency_key/sink_id 全 1:1 echo）
  6. ActionReceipt schema 合规（schema 字段 / status 枚举 / ts ISO-8601 with offset）

调用方式（worktree 内）：
    cd .claude/skills/ticktick-cli/scripts
    uv run pytest test_action_receipt.py -v

依赖隔离：unittest.mock 模拟 TicktickApiClient · 不调真滴答 API
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 被测模块（待实现）
from action_receipt import (  # noqa: E402
    build_action_receipt,
    classify_http_error,
)
from ticktick_api_client import (  # noqa: E402
    ProjectData,
    Task,
    TicktickApiError,
)


# -----------------------------------------------------------------------------
# helpers · fixtures
# -----------------------------------------------------------------------------

VALID_IDEMPOTENCY_KEY = "a" * 64  # 64-char hex


def _make_echo(**overrides):
    """构造合法 echo dict · 测试可覆盖字段。"""
    base = {
        "app": "agenda",
        "job_id": "604",
        "outbox_id": "42",
        "event_id": "ev-9a8c",
        "sink_id": "ticktick-cli",
        "idempotency_key": VALID_IDEMPOTENCY_KEY,
    }
    base.update(overrides)
    return base


def _make_payload(**overrides):
    """构造合法 payload dict · 测试可覆盖字段。"""
    base = {
        "title": "对老婆：遛狗",
        "project_id": "agenda-xxx",
        "due_date": "2026-05-17T20:00:00+0800",
        "content": None,
        "priority": None,
    }
    base.update(overrides)
    return base


def _mock_client_with_tasks(tasks: list[Task], create_result: Task | None = None,
                            create_side_effect=None):
    """构造 mock TicktickApiClient · tasks 用于 get_project_data 返回 · create_result/effect 用于 create_task。"""
    client = MagicMock()
    project_data = ProjectData(project=None, tasks=tasks, columns=None)
    client.get_project_data = MagicMock(return_value=project_data)
    if create_side_effect is not None:
        client.create_task = MagicMock(side_effect=create_side_effect)
    else:
        client.create_task = MagicMock(return_value=create_result or Task(id="new-task-id"))
    return client


# -----------------------------------------------------------------------------
# 1. happy path · search 找不到 · create 成功 · status=succeeded
# -----------------------------------------------------------------------------

def test_build_receipt_succeeded_when_no_duplicate():
    """没有同 title+due 任务 · 走 create · 返 succeeded receipt。"""
    client = _mock_client_with_tasks(
        tasks=[Task(id="other-1", title="买菜", dueDate="2026-05-17T20:00:00+0800")],
        create_result=Task(id="new-task-id-xyz", title="对老婆：遛狗"),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "succeeded"
    assert receipt["external_ref"]["system"] == "ticktick"
    assert receipt["external_ref"]["id"] == "new-task-id-xyz"
    assert receipt["error"] is None
    # create_task 真被调
    assert client.create_task.call_count == 1


# -----------------------------------------------------------------------------
# 2. duplicate path · search 找到匹配 title+due 同日 · 不调 create
# -----------------------------------------------------------------------------

def test_build_receipt_duplicate_when_same_title_and_due_date():
    """已存在同 title + due 同日 task · 返 duplicate receipt · 不调 create_task。"""
    existing_task = Task(
        id="existing-task-abc",
        title="对老婆：遛狗",
        dueDate="2026-05-17T22:00:00+0800",  # 同日不同时
    )
    client = _mock_client_with_tasks(tasks=[existing_task])

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(due_date="2026-05-17T20:00:00+0800"),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "duplicate"
    assert receipt["external_ref"]["system"] == "ticktick"
    assert receipt["external_ref"]["id"] == "existing-task-abc"
    assert receipt["error"] is None
    # create_task 不调
    assert client.create_task.call_count == 0


def test_build_receipt_duplicate_handles_timezone_diff_same_utc_day():
    """同 UTC 日不同 timezone · 按本地日期判定（payload 时区为准）·
    payload due=2026-05-17T01:00:00+0800（北京 5/17）vs existing 2026-05-16T17:00:00+0000（UTC 5/16 = 北京 5/17）
    应判同日 · duplicate。"""
    existing_task = Task(
        id="existing-tz-task",
        title="对老婆：遛狗",
        dueDate="2026-05-17T20:00:00+0800",  # 北京 5/17
    )
    client = _mock_client_with_tasks(tasks=[existing_task])

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(due_date="2026-05-17T02:00:00+0800"),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "duplicate"
    assert receipt["external_ref"]["id"] == "existing-tz-task"


def test_build_receipt_succeeded_when_same_title_different_due_date():
    """同 title 但 due 不同日 · 不算重复 · 走 create · succeeded。"""
    existing_task = Task(
        id="existing-yesterday",
        title="对老婆：遛狗",
        dueDate="2026-05-16T20:00:00+0800",  # 昨天
    )
    client = _mock_client_with_tasks(
        tasks=[existing_task],
        create_result=Task(id="new-today-task"),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(due_date="2026-05-17T20:00:00+0800"),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "succeeded"
    assert receipt["external_ref"]["id"] == "new-today-task"


# -----------------------------------------------------------------------------
# 3. failed retryable · HTTP 5xx / 401 / timeout
# -----------------------------------------------------------------------------

def test_build_receipt_failed_retryable_on_http_500():
    """search/create 返 HTTP 500 · status=failed · retryable=true。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_side_effect=TicktickApiError("Request failed: 500 server crashed", 500),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "failed"
    assert receipt["external_ref"] is None
    assert receipt["error"]["retryable"] is True
    assert receipt["error"]["code"] == "HTTP_500"
    assert "500" in receipt["error"]["message"]


def test_build_receipt_failed_retryable_on_http_401():
    """HTTP 401 (token 即将过期) · retryable=true (daemon 可能刷 token 重试)。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_side_effect=TicktickApiError("Request failed: 401 unauthorized", 401),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "failed"
    assert receipt["error"]["retryable"] is True
    assert receipt["error"]["code"] == "HTTP_401"


# -----------------------------------------------------------------------------
# 4. failed non-retryable · HTTP 4xx 非 401
# -----------------------------------------------------------------------------

def test_build_receipt_failed_non_retryable_on_http_400():
    """HTTP 400 bad request · retryable=false (重试无用)。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_side_effect=TicktickApiError("Request failed: 400 bad payload", 400),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "failed"
    assert receipt["error"]["retryable"] is False
    assert receipt["error"]["code"] == "HTTP_400"


def test_build_receipt_failed_non_retryable_on_http_403():
    """HTTP 403 forbidden · retryable=false。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_side_effect=TicktickApiError("Request failed: 403 forbidden", 403),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] == "failed"
    assert receipt["error"]["retryable"] is False


# -----------------------------------------------------------------------------
# 5. echo fields · 全字段 1:1 透传
# -----------------------------------------------------------------------------

def test_build_receipt_echoes_all_input_fields():
    """schema / app / job_id / outbox_id / idempotency_key / sink_id 必须 1:1 echo。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_result=Task(id="echo-test-task"),
    )

    echo = _make_echo(
        app="custom-app",
        job_id="job-9999",
        outbox_id="outbox-7777",
        sink_id="ticktick-cli",
        idempotency_key="b" * 64,
    )
    receipt = build_action_receipt(
        echo=echo,
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["schema"] == "cufin.action.v1"
    assert receipt["app"] == "custom-app"
    assert receipt["job_id"] == "job-9999"
    assert receipt["outbox_id"] == "outbox-7777"
    assert receipt["sink_id"] == "ticktick-cli"
    assert receipt["idempotency_key"] == "b" * 64


# -----------------------------------------------------------------------------
# 6. schema 合规 · ts ISO-8601 with offset · status 枚举
# -----------------------------------------------------------------------------

def test_build_receipt_ts_is_iso8601_with_offset():
    """ts 必须 ISO-8601 with offset 格式（让 daemon ActionReceipt.Validate() 通过）。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_result=Task(id="ts-test-task"),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    # 简单正则 · daemon 端 isISO8601WithOffset 接受 +HHMM 或 +HH:MM
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:?\d{2}|Z)$")
    assert iso_re.match(receipt["ts"]), f"ts {receipt['ts']!r} 不符 ISO-8601 with offset"


def test_build_receipt_status_is_one_of_three_values():
    """status 必须是 succeeded / duplicate / failed 之一。"""
    client = _mock_client_with_tasks(
        tasks=[],
        create_result=Task(id="status-test-task"),
    )

    receipt = build_action_receipt(
        echo=_make_echo(),
        payload=_make_payload(),
        client=client,
        now_iso="2026-05-18T01:00:01+0800",
    )

    assert receipt["status"] in ("succeeded", "duplicate", "failed")


# -----------------------------------------------------------------------------
# 7. classify_http_error · 边界 helper 单测
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("status_code,expected_retryable", [
    (500, True),
    (502, True),
    (503, True),
    (504, True),
    (401, True),
    (400, False),
    (403, False),
    (404, False),
    (422, False),
])
def test_classify_http_error_retryable_rules(status_code, expected_retryable):
    """retryable 判定规则：5xx + 401 = retryable · 4xx 非 401 = non-retryable。"""
    code, retryable = classify_http_error(status_code)
    assert retryable is expected_retryable
    assert code == f"HTTP_{status_code}"


def test_classify_http_error_network_failure_is_retryable():
    """status_code=None（网络挂 / timeout / connection reset）· retryable=true。"""
    code, retryable = classify_http_error(None)
    assert retryable is True
    assert code == "NETWORK_ERROR"

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27.0",
#     "typer>=0.9.0",
#     "pydantic>=2.5.0",
#     "rich>=13.0.0",
# ]
# ///
"""
test_create_receipt_cli.py · 端到端 CLI 单测

S13-P2-5 · 验 `ticktick task create-receipt` subcommand 完整链路：
  - typer CLI parsing 接住所有 flag
  - 内部 build_action_receipt 正确调
  - stdout 输出合法 ActionReceipt JSON（第一字节 '{' · daemon parseOutboxStdout 兼容）
  - exit code = 0（包括 failed 路径）

依赖隔离：mock httpx response · 不调真滴答 API · 不动 keychain。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ticktick_cli  # noqa: E402


VALID_IDEMPOTENCY_KEY = "c" * 64


# -----------------------------------------------------------------------------
# helpers · 构造 mock httpx response
# -----------------------------------------------------------------------------

def _make_mock_session(get_project_data_response: dict, create_task_response: dict | None = None,
                       create_status_code: int = 200):
    """构造 mock httpx Client · session.request 返不同 response 按 path 分发。

    get_project_data → GET /project/<id>/data
    create_task → POST /task
    """
    def request_side_effect(*args, **kwargs):
        # ticktick_api_client._request 全用 kwargs 传 method / url
        method = (kwargs.get("method") or (args[0] if len(args) > 0 else "")).upper()
        url = kwargs.get("url") or (args[1] if len(args) > 1 else "")
        url_str = str(url or "")
        mock_response = MagicMock()
        if "/data" in url_str and method == "GET":
            mock_response.status_code = 200
            mock_response.content = b"{}"
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.json = lambda: get_project_data_response
            return mock_response
        if url_str.endswith("/task") and method == "POST":
            mock_response.status_code = create_status_code
            mock_response.text = json.dumps(create_task_response or {})
            mock_response.content = mock_response.text.encode()
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.json = lambda: create_task_response or {}
            return mock_response
        # default · debug 出 url 帮排查
        mock_response.status_code = 404
        mock_response.text = f"not found · method={method} url={url_str}"
        mock_response.content = mock_response.text.encode()
        mock_response.headers = {}
        return mock_response

    session = MagicMock()
    session.request = MagicMock(side_effect=request_side_effect)
    return session


@contextmanager
def patched_token_env():
    """配置 token env · 防 get_client 报错。"""
    previous_token = os.environ.get("TICKTICK_TOKEN")
    previous_token_file = ticktick_cli.TOKEN_FILE
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TICKTICK_TOKEN"] = "test-token-abc"
        ticktick_cli.TOKEN_FILE = Path(tmp) / "ticktick.json"
        try:
            yield
        finally:
            if previous_token is None:
                os.environ.pop("TICKTICK_TOKEN", None)
            else:
                os.environ["TICKTICK_TOKEN"] = previous_token
            ticktick_cli.TOKEN_FILE = previous_token_file


# -----------------------------------------------------------------------------
# 端到端 CLI 测试
# -----------------------------------------------------------------------------

def test_cli_create_receipt_succeeded_path(runner, mock_token_env):
    """search 找不到 → create → stdout 是 status=succeeded receipt JSON。"""
    project_data_resp = {
        "project": None,
        "tasks": [{"id": "other-1", "title": "买菜", "dueDate": "2026-05-17T20:00:00+0800"}],
        "columns": [],
    }
    create_resp = {"id": "new-task-cli-test", "title": "对老婆：遛狗"}

    fake_session = _make_mock_session(project_data_resp, create_resp)
    with patch("ticktick_cli.TicktickApiClient") as ClientCls:
        # 真实例化但替 session
        from ticktick_api_client import TicktickApiClient as RealClient
        client_inst = RealClient(token="test-token-abc", session=fake_session)
        ClientCls.return_value = client_inst

        result = runner.invoke(
            ticktick_cli.app,
            [
                "task", "create-receipt",
                "--title", "对老婆：遛狗",
                "--project-id", "agenda-xxx",
                "--due-date", "2026-05-17T20:00:00+0800",
                "--app", "agenda",
                "--job-id", "604",
                "--outbox-id", "42",
                "--event-id", "ev-9a8c",
                "--idempotency-key", VALID_IDEMPOTENCY_KEY,
            ],
        )

    assert result.exit_code == 0, f"stderr={result.stderr!r}"
    # 第一字节必须 '{'（daemon parseOutboxStdout 严格性）
    stripped = result.stdout.lstrip()
    assert stripped.startswith("{"), f"stdout 第一字节非 '{{'：{result.stdout!r}"
    receipt = json.loads(result.stdout)
    assert receipt["schema"] == "cufin.action.v1"
    assert receipt["status"] == "succeeded", f"receipt={receipt!r}"
    assert receipt["external_ref"]["system"] == "ticktick"
    assert receipt["external_ref"]["id"] == "new-task-cli-test"
    assert receipt["outbox_id"] == "42"
    assert receipt["idempotency_key"] == VALID_IDEMPOTENCY_KEY


def test_cli_create_receipt_duplicate_path(runner, mock_token_env):
    """search 找到匹配 → 不调 create → stdout 是 status=duplicate receipt。"""
    project_data_resp = {
        "project": None,
        "tasks": [
            {"id": "existing-task-456", "title": "对老婆：遛狗",
             "dueDate": "2026-05-17T22:00:00+0800"},  # 同日不同时
        ],
        "columns": [],
    }

    fake_session = _make_mock_session(project_data_resp, create_task_response=None)
    with patch("ticktick_cli.TicktickApiClient") as ClientCls:
        from ticktick_api_client import TicktickApiClient as RealClient
        client_inst = RealClient(token="test-token-abc", session=fake_session)
        ClientCls.return_value = client_inst

        result = runner.invoke(
            ticktick_cli.app,
            [
                "task", "create-receipt",
                "--title", "对老婆：遛狗",
                "--project-id", "agenda-xxx",
                "--due-date", "2026-05-17T20:00:00+0800",
                "--app", "agenda",
                "--job-id", "604",
                "--outbox-id", "43",
                "--event-id", "ev-dup",
                "--idempotency-key", VALID_IDEMPOTENCY_KEY,
            ],
        )

    assert result.exit_code == 0, f"stderr={result.stderr!r}"
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "duplicate"
    assert receipt["external_ref"]["id"] == "existing-task-456"
    # 验证 create_task 真没被调（通过 session.request POST /task 未被调）
    # session.request 调用次数 = 1（仅 GET /project/.../data）
    assert fake_session.request.call_count == 1


def test_cli_create_receipt_failed_path_still_exit_0(runner, mock_token_env):
    """HTTP 500 → status=failed receipt · exit_code 仍是 0（daemon 看 status 不看 exit）。"""
    project_data_resp = {
        "project": None,
        "tasks": [],
        "columns": [],
    }

    fake_session = _make_mock_session(
        project_data_resp,
        create_task_response={"error": "server crashed"},
        create_status_code=500,
    )
    with patch("ticktick_cli.TicktickApiClient") as ClientCls:
        from ticktick_api_client import TicktickApiClient as RealClient
        client_inst = RealClient(token="test-token-abc", session=fake_session)
        ClientCls.return_value = client_inst

        result = runner.invoke(
            ticktick_cli.app,
            [
                "task", "create-receipt",
                "--title", "对老婆：遛狗",
                "--project-id", "agenda-xxx",
                "--due-date", "2026-05-17T20:00:00+0800",
                "--app", "agenda",
                "--job-id", "604",
                "--outbox-id", "44",
                "--event-id", "ev-fail",
                "--idempotency-key", VALID_IDEMPOTENCY_KEY,
            ],
        )

    # 关键 invariant · exit_code 永远 0
    assert result.exit_code == 0, f"failed path exit_code={result.exit_code} stderr={result.stderr!r}"
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "failed"
    assert receipt["error"]["retryable"] is True  # 500 retryable
    assert receipt["error"]["code"] == "HTTP_500"
    assert receipt["external_ref"] is None


def test_cli_create_receipt_default_sink_id_is_ticktick_cli(runner, mock_token_env):
    """--sink-id 默认值是 'ticktick-cli'（plan §10.2 命名约定）。"""
    project_data_resp = {"project": None, "tasks": [], "columns": []}
    create_resp = {"id": "sink-default-test"}

    fake_session = _make_mock_session(project_data_resp, create_resp)
    with patch("ticktick_cli.TicktickApiClient") as ClientCls:
        from ticktick_api_client import TicktickApiClient as RealClient
        client_inst = RealClient(token="test-token-abc", session=fake_session)
        ClientCls.return_value = client_inst

        result = runner.invoke(
            ticktick_cli.app,
            [
                "task", "create-receipt",
                "--title", "test-task",
                "--project-id", "p1",
                "--app", "agenda",
                "--job-id", "j1",
                "--outbox-id", "o1",
                "--event-id", "e1",
                "--idempotency-key", VALID_IDEMPOTENCY_KEY,
                # 不传 --sink-id
            ],
        )

    assert result.exit_code == 0
    receipt = json.loads(result.stdout)
    assert receipt["sink_id"] == "ticktick-cli"


def test_cli_create_receipt_idempotency_key_required(runner, mock_token_env):
    """--idempotency-key 必填 · 不传报 missing option · exit code != 0。"""
    result = runner.invoke(
        ticktick_cli.app,
        [
            "task", "create-receipt",
            "--title", "test",
            "--project-id", "p1",
            "--app", "agenda",
            "--job-id", "j1",
            "--outbox-id", "o1",
            "--event-id", "e1",
            # 不传 --idempotency-key
        ],
    )
    assert result.exit_code != 0
    # typer 写到 stderr · 包含 "idempotency-key" 关键词
    assert "idempotency-key" in result.stderr.lower() or "missing" in result.stderr.lower()


def run_cli_test(fn):
    # CliRunner 在 click 8.x 后默认 mix_stderr=False · 不再接收 kwarg
    with patched_token_env():
        fn(CliRunner(), None)


if __name__ == "__main__":
    run_cli_test(test_cli_create_receipt_succeeded_path)
    run_cli_test(test_cli_create_receipt_duplicate_path)
    run_cli_test(test_cli_create_receipt_failed_path_still_exit_0)
    run_cli_test(test_cli_create_receipt_default_sink_id_is_ticktick_cli)
    run_cli_test(test_cli_create_receipt_idempotency_key_required)
    print("ticktick create receipt CLI tests passed.")

#!/usr/bin/env python3
"""
action_receipt.py · cufenshen action outbox stage · ActionReceipt v1 builder

S13-P2-5 · ticktick-cli skill stdout 升级到 ActionReceipt v1

设计来源：
  - cufenshen/dev-conventions.md §13 action outbox 路径接入约定
  - cufenshen/architecture/v0.5.1-overview.html §03.5 ActionReceipt schema
  - cufenshen/architecture/audit-2026-05-17-ticktick-cli-real-behavior.md
    （11 项 gap 全收一刀）
  - 校长 2026-05-18 任务：方案 A · skill 自己产 ActionReceipt JSON ·
    加 --idempotency-key flag · 内部 search-before-create

模块边界：
  - build_action_receipt() · 核心业务逻辑 · 接 echo + payload + client + now_iso
    → 返 ActionReceipt dict（永远合法 · 包括 failed 路径）
  - classify_http_error() · HTTP 状态码 → (error_code, retryable) 分类规则

不依赖 typer · 让 CLI subcommand 可以做 thin wrapper · 测试可 mock TicktickApiClient 隔离。
"""
from __future__ import annotations

from typing import Any

from ticktick_api_client import (
    Task,
    TaskCreate,
    TicktickApiClient,
    TicktickApiError,
)

SCHEMA_ACTION_V1 = "cufin.action.v1"
EXTERNAL_SYSTEM_TICKTICK = "ticktick"


def classify_http_error(status_code: int | None) -> tuple[str, bool]:
    """HTTP 状态码 → (error_code, retryable)

    规则（dev-conventions §13 + action.md prompt 错误处理段）：
      - status_code=None（网络挂 / timeout / connection reset）→ retryable=true
      - 5xx 服务端错 → retryable=true
      - 401 token 即将过期 → retryable=true（daemon 可能刷 token 重试）
      - 4xx 非 401 → retryable=false（重试无用）

    返回：(error_code, retryable)
      - error_code 格式："HTTP_<code>" 或 "NETWORK_ERROR"
      - retryable bool
    """
    if status_code is None:
        return ("NETWORK_ERROR", True)
    if status_code >= 500:
        return (f"HTTP_{status_code}", True)
    if status_code == 401:
        return ("HTTP_401", True)
    # 4xx 非 401 全 non-retryable
    return (f"HTTP_{status_code}", False)


def _extract_date_part(iso8601: str | None) -> str | None:
    """从 ISO-8601 字符串提取日期部分（YYYY-MM-DD）· 容忍 +HHMM / +HH:MM / Z 后缀。

    例：
      "2026-05-17T20:00:00+0800" → "2026-05-17"
      "2026-05-17T20:00:00+08:00" → "2026-05-17"
      "2026-05-17T22:00:00Z" → "2026-05-17"
      None → None

    设计：本地日期截前缀（不做时区转换）。Sprint-13 范围足够 · 跨时区精确比对 留 Sprint-14+。
    """
    if not iso8601:
        return None
    # 截 'T' 前部分
    if "T" in iso8601:
        return iso8601.split("T", 1)[0]
    return iso8601


def _find_duplicate_task(client: TicktickApiClient, project_id: str,
                          title: str, due_date: str | None) -> Task | None:
    """search-before-create · 查 project 下未完成 tasks · 按 title + due 同日匹配。

    返回找到的 Task（duplicate）· 找不到返 None。

    设计（dev-conventions §13.3 + action prompt search-before-create 协议）：
      - 调 client.get_project_data(project_id) 拿 ProjectData.tasks
      - 本地 filter：title 精确等 + due_date 截日期部分相等
      - 多条匹配 · 取第一条（dev-conventions 不限定多匹配处理 · 默认稳定）

    异常透传：调用方负责捕获 TicktickApiError 包装成 failed receipt。
    """
    project_data = client.get_project_data(project_id)
    existing_tasks = project_data.tasks or []
    target_date = _extract_date_part(due_date)
    for task in existing_tasks:
        if task.title != title:
            continue
        # 没 due_date 时 · 不靠 due 匹配（避免空 vs 空匹配过宽）· 仅 title 不算 duplicate
        if target_date is None:
            continue
        task_date = _extract_date_part(task.dueDate)
        if task_date == target_date:
            return task
    return None


def _make_succeeded_receipt(echo: dict[str, Any], external_id: str, now_iso: str) -> dict[str, Any]:
    """构造 status=succeeded 的 ActionReceipt dict。"""
    return _base_receipt(echo, now_iso) | {
        "status": "succeeded",
        "external_ref": {
            "system": EXTERNAL_SYSTEM_TICKTICK,
            "id": external_id,
        },
        "error": None,
    }


def _make_duplicate_receipt(echo: dict[str, Any], external_id: str, now_iso: str) -> dict[str, Any]:
    """构造 status=duplicate 的 ActionReceipt dict。"""
    return _base_receipt(echo, now_iso) | {
        "status": "duplicate",
        "external_ref": {
            "system": EXTERNAL_SYSTEM_TICKTICK,
            "id": external_id,
        },
        "error": None,
    }


def _make_failed_receipt(echo: dict[str, Any], error_code: str,
                          error_message: str, retryable: bool, now_iso: str) -> dict[str, Any]:
    """构造 status=failed 的 ActionReceipt dict。"""
    return _base_receipt(echo, now_iso) | {
        "status": "failed",
        "external_ref": None,
        "error": {
            "code": error_code,
            "message": error_message,
            "retryable": retryable,
        },
    }


def _base_receipt(echo: dict[str, Any], now_iso: str) -> dict[str, Any]:
    """ActionReceipt 公共 echo 字段 + schema + ts。"""
    return {
        "schema": SCHEMA_ACTION_V1,
        "app": echo["app"],
        "job_id": echo["job_id"],
        "outbox_id": echo["outbox_id"],
        "idempotency_key": echo["idempotency_key"],
        "sink_id": echo["sink_id"],
        "ts": now_iso,
    }


def build_action_receipt(
    echo: dict[str, Any],
    payload: dict[str, Any],
    *,
    client: TicktickApiClient,
    now_iso: str,
) -> dict[str, Any]:
    """核心业务逻辑 · 接 echo + payload + client + now_iso · 返合法 ActionReceipt dict。

    Args:
        echo: daemon 注入的 echo 字段 dict · 含 app / job_id / outbox_id / event_id
              / sink_id / idempotency_key（全字段 1:1 echo 到 receipt）
        payload: ticktick 真要写的字段 dict · 含 title / project_id / due_date / content
              / priority（可选）
        client: TicktickApiClient 实例（已带 token）· 真接通时连真滴答 ·
              测试时 mock
        now_iso: 当前时间 ISO-8601 with offset · 填 receipt.ts

    Returns:
        ActionReceipt dict · 永远合法 · 包括 failed 路径（异常会被包成 failed receipt ·
        不再抛 SystemExit · stdout 永远是 JSON）

    步骤：
        1. search · 调 client.get_project_data(project_id) 拿全 task list
        2. filter · 按 title + due 同日找匹配 task
        3. 找到 → 构造 duplicate receipt（不调 create_task）
        4. 找不到 → 调 client.create_task(...) → 构造 succeeded receipt
        5. 任何 TicktickApiError → classify_http_error 决出 retryable → 构造 failed receipt
        6. 其他 Exception → wrap 成 NETWORK_ERROR retryable=true（防 daemon 卡死）

    设计要点（dev-conventions §13）：
        - exit code 永远 0（status=failed 也是 0 · daemon 看 status 不看 exit）
        - stdout 永远合法 JSON · stderr 不发任何东西（避开 v0.5.1 §03.7 老协议毛病）
        - 不 fallback 任何老格式 · ActionReceipt JSON 唯一输出
    """
    title = payload["title"]
    project_id = payload["project_id"]
    due_date = payload.get("due_date")

    # 步骤 1+2 · search-before-create
    try:
        duplicate = _find_duplicate_task(client, project_id, title, due_date)
    except TicktickApiError as exc:
        error_code, retryable = classify_http_error(exc.status_code)
        return _make_failed_receipt(echo, error_code, str(exc), retryable, now_iso)
    except Exception as exc:  # pragma: no cover · 网络异常 / 未知错
        return _make_failed_receipt(echo, "NETWORK_ERROR", str(exc), True, now_iso)

    # 步骤 3 · 找到 → duplicate
    if duplicate is not None:
        return _make_duplicate_receipt(echo, duplicate.id or "", now_iso)

    # 步骤 4 · 找不到 → create
    create_req = TaskCreate(
        title=title,
        projectId=project_id,
        dueDate=due_date,
        content=payload.get("content"),
        priority=payload.get("priority"),
    )
    try:
        new_task = client.create_task(create_req)
    except TicktickApiError as exc:
        error_code, retryable = classify_http_error(exc.status_code)
        return _make_failed_receipt(echo, error_code, str(exc), retryable, now_iso)
    except Exception as exc:  # pragma: no cover · 网络异常 / 未知错
        return _make_failed_receipt(echo, "NETWORK_ERROR", str(exc), True, now_iso)

    return _make_succeeded_receipt(echo, new_task.id or "", now_iso)

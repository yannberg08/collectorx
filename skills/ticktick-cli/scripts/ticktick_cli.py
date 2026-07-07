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

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Windows 控制台默认 cp936 不能输出非 GBK 字符，会让中文 task title 变乱码 +
# 让 rich 内部写入 stdout 时崩溃产生 traceback 污染 JSON 输出。强制 utf-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

ENV_BASE_URL = "TICKTICK_BASE_URL"
ENV_TIMEOUT = "TICKTICK_TIMEOUT"
ENV_TOKEN = "TICKTICK_TOKEN"
# 该脚本主要提供给 AI Agent 调用，人类 CLI 使用只是顺带支持。
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ticktick_api_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    ChecklistItem,
    ProjectCreate,
    ProjectUpdate,
    TaskCreate,
    TaskUpdate,
    TicktickApiClient,
    TicktickApiError,
)

app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True, help="项目相关操作。")
task_app = typer.Typer(no_args_is_help=True, help="任务相关操作。")
console = Console()


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AppState(BaseModel):
    token: str | None
    base_url: str
    timeout: str
    json_output: bool


TOKEN_FILE = Path.home() / ".covo" / "ticktick.json"


def _load_token_from_file() -> str | None:
    """从 ~/.covo/ticktick.json 读 access_token。auth.py authorize 会写这个文件。
    跨平台：Path.home() 在 Windows/Mac/Linux 都对，不需要用户分平台 setx/export。"""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        return token.strip() if token else None
    except (json.JSONDecodeError, OSError):
        return None


def get_client(ctx: typer.Context) -> TicktickApiClient:
    state = ctx.obj
    if not isinstance(state, AppState):
        raise ApiError("Client config not initialized.")
    # token 取值优先级：--token 参数 > TICKTICK_TOKEN env > ~/.covo/ticktick.json
    token = state.token or _load_token_from_file()
    if not token:
        raise ApiError(
            "缺少 token。先跑 `python <skill_dir>/scripts/auth.py register <id> <sec>` "
            "保存 OAuth 应用凭证，再跑 `python <skill_dir>/scripts/auth.py authorize` "
            "完成授权（一条龙：起本地 server + 开浏览器 + 抓回调 + 落 token 到 "
            f"{TOKEN_FILE}）。授权后本 CLI 会自动从该文件读 token。"
        )
    base_url = state.base_url
    timeout_raw = state.timeout
    timeout_seconds = parse_timeout(str(timeout_raw))
    if timeout_seconds <= 0:
        raise ApiError("Timeout must be greater than 0.")
    return TicktickApiClient(
        token=token,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def render_payload(payload: Any) -> None:
    """所有 JSON 输出走 stdlib，不走 rich。
    rich.print_json 在 Windows cp936 终端上遇到中文字段会自爆 traceback，
    而且 AI 调用时 --json 一定要稳——只要 stdlib 能输出就够，不需要彩色。"""
    if isinstance(payload, list):
        data = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in payload
        ]
    elif hasattr(payload, "model_dump"):
        data = payload.model_dump()
    else:
        data = payload
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def render_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    table = Table(title=title)
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def render_kv_table(title: str, data: dict[str, Any]) -> None:
    rows = [[key, "" if value is None else str(value)] for key, value in data.items()]
    render_table(title, ["field", "value"], rows)


def render_project_list(projects: list[Any]) -> None:
    rows = []
    for project in projects:
        data = project.model_dump() if hasattr(project, "model_dump") else project
        rows.append(
            [
                str(data.get("id", "")),
                str(data.get("name", "")),
                str(data.get("color", "")),
                str(data.get("closed", "")),
                str(data.get("groupId", "")),
                str(data.get("viewMode", "")),
                str(data.get("kind", "")),
                str(data.get("sortOrder", "")),
            ]
        )
    render_table(
        "Projects",
        ["id", "name", "color", "closed", "groupId", "viewMode", "kind", "sortOrder"],
        rows,
    )


def render_task_list(tasks: list[Any]) -> None:
    rows = []
    for task in tasks:
        data = task.model_dump() if hasattr(task, "model_dump") else task
        rows.append(
            [
                str(data.get("id", "")),
                str(data.get("title", "")),
                str(data.get("status", "")),
                str(data.get("priority", "")),
                str(data.get("dueDate", "")),
                str(data.get("projectId", "")),
            ]
        )
    render_table(
        "Tasks",
        ["id", "title", "status", "priority", "dueDate", "projectId"],
        rows,
    )


def render_columns_list(columns: list[Any]) -> None:
    rows = []
    for column in columns:
        data = column.model_dump() if hasattr(column, "model_dump") else column
        rows.append(
            [
                str(data.get("id", "")),
                str(data.get("name", "")),
                str(data.get("sortOrder", "")),
            ]
        )
    render_table("Columns", ["id", "name", "sortOrder"], rows)


def parse_timeout(raw: str) -> float:
    value = raw.strip().lower()
    if not value:
        raise ApiError("Timeout cannot be empty.")
    multipliers = [
        ("seconds", 1),
        ("second", 1),
        ("secs", 1),
        ("sec", 1),
        ("s", 1),
        ("minutes", 60),
        ("minute", 60),
        ("mins", 60),
        ("min", 60),
        ("m", 60),
        ("hours", 3600),
        ("hour", 3600),
        ("hrs", 3600),
        ("hr", 3600),
        ("h", 3600),
    ]
    for unit, multiplier in multipliers:
        if value.endswith(unit):
            number = value[: -len(unit)].strip()
            try:
                return float(number) * multiplier
            except ValueError as exc:
                raise ApiError(f"Invalid timeout: {raw}") from exc
    try:
        return float(value)
    except ValueError as exc:
        raise ApiError(f"Invalid timeout: {raw}") from exc


def parse_checklist_items(
    item: list[str] | None,
    item_json: str | None,
) -> list[ChecklistItem] | None:
    if item and item_json:
        raise ApiError("Use --item or --item-json, not both.")
    if item_json:
        raw = item_json
        if raw.startswith("@"):
            path = Path(raw[1:]).expanduser()
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ApiError(f"Failed to read items JSON: {path}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError("Invalid JSON for --item-json.") from exc
        if not isinstance(payload, list):
            raise ApiError("--item-json must be a JSON array.")
        items: list[ChecklistItem] = []
        for entry in payload:
            if isinstance(entry, str):
                items.append(ChecklistItem(title=entry))
                continue
            if not isinstance(entry, dict):
                raise ApiError("Each item in --item-json must be an object or string.")
            items.append(ChecklistItem.model_validate(entry))
        return items or None
    if item:
        return [ChecklistItem(title=item_title) for item_title in item]
    return None


@app.callback()
def main(
    ctx: typer.Context,
    token: str | None = typer.Option(
        None,
        "--token",
        envvar=ENV_TOKEN,
        help="OAuth token.",
    ),
    base_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--base-url",
        envvar=ENV_BASE_URL,
        help="API base URL.",
    ),
    timeout: str = typer.Option(
        "30s",
        "--timeout",
        envvar=ENV_TIMEOUT,
        help="Request timeout (e.g. 20s, 1m).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="输出 JSON 格式。",
    ),
) -> None:
    if ctx.resilient_parsing:
        return
    # token 防御：去掉头尾空白/CR/LF（Windows 写文件容易混进 \r）
    if token:
        token = token.strip()
    ctx.obj = AppState(
        token=token,
        base_url=base_url,
        timeout=timeout,
        json_output=json_output,
    )


@project_app.command("list", help="列出当前账号的项目。")
def project_list(ctx: typer.Context) -> None:
    client = get_client(ctx)
    projects = client.list_projects()
    if ctx.obj.json_output:
        render_payload(projects)
        return
    render_project_list(projects)


@project_app.command("get", help="根据项目 ID 获取项目详情。")
def project_get(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
) -> None:
    client = get_client(ctx)
    project = client.get_project(project_id)
    if ctx.obj.json_output:
        render_payload(project)
        return
    render_kv_table("Project", project.model_dump())


@project_app.command("data", help="获取项目详情（包含未完成任务与列）。")
def project_data(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
) -> None:
    client = get_client(ctx)
    data = client.get_project_data(project_id)
    if ctx.obj.json_output:
        render_payload(data)
        return
    project = data.project.model_dump() if data.project else {}
    render_kv_table("Project", project)
    render_task_list(data.tasks or [])
    render_columns_list(data.columns or [])


@project_app.command("create", help="创建项目。")
def project_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    color: str | None = typer.Option(None, "--color"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    view_mode: str | None = typer.Option(None, "--view-mode"),
    kind: str | None = typer.Option(None, "--kind"),
) -> None:
    client = get_client(ctx)
    project = client.create_project(
        ProjectCreate(
            name=name,
            color=color,
            sortOrder=sort_order,
            viewMode=view_mode,
            kind=kind,
        )
    )
    if ctx.obj.json_output:
        render_payload(project)
        return
    render_kv_table("Project", project.model_dump())


@project_app.command("update", help="更新项目。")
def project_update(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    name: str | None = typer.Option(None, "--name"),
    color: str | None = typer.Option(None, "--color"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    view_mode: str | None = typer.Option(None, "--view-mode"),
    kind: str | None = typer.Option(None, "--kind"),
) -> None:
    if not any([name, color, sort_order, view_mode, kind]):
        raise ApiError("No update fields provided.")
    client = get_client(ctx)
    project = client.update_project(
        project_id,
        ProjectUpdate(
            name=name,
            color=color,
            sortOrder=sort_order,
            viewMode=view_mode,
            kind=kind,
        ),
    )
    if ctx.obj.json_output:
        render_payload(project)
        return
    render_kv_table("Project", project.model_dump())


@project_app.command("delete", help="删除项目。")
def project_delete(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
) -> None:
    client = get_client(ctx)
    client.delete_project(project_id)
    console.print("OK")


@task_app.command("list", help="列出项目下的未完成任务。")
def task_list(
    ctx: typer.Context,
    project_id: str = typer.Option(
        "inbox1013277052",
        "--project-id",
        help="项目 ID，默认为收集箱。",
    ),
) -> None:
    client = get_client(ctx)
    data = client.get_project_data(project_id)
    tasks = data.tasks or []
    if ctx.obj.json_output:
        render_payload(tasks)
        return
    render_task_list(tasks)


@task_app.command("list-completed", help="列出已完成任务（POST /open/v1/task/completed）。")
def task_list_completed(
    ctx: typer.Context,
    completed_from: str | None = typer.Option(
        None, "--from", help="完成时间下限 ISO8601（如 2026-04-20T00:00:00+0000）"
    ),
    completed_to: str | None = typer.Option(
        None, "--to", help="完成时间上限 ISO8601"
    ),
    limit: int | None = typer.Option(None, "--limit", help="最大数量（默认 200）"),
    keyword: str | None = typer.Option(
        None, "--keyword", "-q", help="本地按 title/content 关键词过滤（API 不支持，本地筛）"
    ),
) -> None:
    client = get_client(ctx)
    tasks = client.list_completed_tasks(
        completed_time_from=completed_from,
        completed_time_to=completed_to,
        limit=limit,
    )
    if keyword:
        kw = keyword.lower()
        tasks = [
            t for t in tasks
            if kw in (t.title or "").lower() or kw in (t.content or "").lower()
        ]
    if ctx.obj.json_output:
        render_payload(tasks)
        return
    render_task_list(tasks)


@task_app.command("filter", help="高级任务过滤（POST /open/v1/task/filter）。")
def task_filter(
    ctx: typer.Context,
    project_id: list[str] = typer.Option(
        [], "--project-id", help="限定项目（可多次传）"
    ),
    start_date: str | None = typer.Option(None, "--start-date", help="任务 startDate ≥ 此值"),
    end_date: str | None = typer.Option(None, "--end-date", help="任务 startDate ≤ 此值"),
    priority: list[int] = typer.Option(
        [], "--priority", help="按优先级筛 0/1/3/5（可多次传）"
    ),
    tag: list[str] = typer.Option([], "--tag", help="按标签筛（可多次传）"),
    status: list[int] = typer.Option(
        [], "--status", help="状态：0=未完成 / 2=已完成（可多次传）"
    ),
) -> None:
    client = get_client(ctx)
    tasks = client.filter_tasks(
        project_ids=project_id or None,
        start_date=start_date,
        end_date=end_date,
        priority=priority or None,
        tag=tag or None,
        status=status or None,
    )
    if ctx.obj.json_output:
        render_payload(tasks)
        return
    render_task_list(tasks)


@task_app.command("move", help="移动任务到别的项目（POST /open/v1/task/move）。")
def task_move(
    ctx: typer.Context,
    task_id: str = typer.Option(..., "--task-id"),
    from_project: str = typer.Option(..., "--from-project"),
    to_project: str = typer.Option(..., "--to-project"),
) -> None:
    client = get_client(ctx)
    result = client.move_tasks([{
        "taskId": task_id,
        "fromProjectId": from_project,
        "toProjectId": to_project,
    }])
    render_payload(result)


@task_app.command("get", help="根据项目 ID 与任务 ID 获取任务。")
def task_get(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    task_id: str = typer.Option(..., "--task-id"),
) -> None:
    client = get_client(ctx)
    task = client.get_task(project_id, task_id)
    if ctx.obj.json_output:
        render_payload(task)
        return
    render_kv_table("Task", task.model_dump())


@task_app.command("create", help="创建任务。")
def task_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title"),
    project_id: str = typer.Option(..., "--project-id"),
    content: str | None = typer.Option(None, "--content"),
    desc: str | None = typer.Option(None, "--desc"),
    is_all_day: bool | None = typer.Option(None, "--all-day"),
    start_date: str | None = typer.Option(None, "--start-date"),
    due_date: str | None = typer.Option(None, "--due-date"),
    time_zone: str | None = typer.Option(None, "--time-zone"),
    reminder: list[str] | None = typer.Option(None, "--reminder"),
    repeat_flag: str | None = typer.Option(None, "--repeat"),
    priority: int | None = typer.Option(None, "--priority"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    item: list[str] | None = typer.Option(None, "--item"),
    item_json: str | None = typer.Option(
        None,
        "--item-json",
        help="JSON array string or @path to JSON file for checklist items.",
    ),
) -> None:
    client = get_client(ctx)
    items = parse_checklist_items(item, item_json)
    task = client.create_task(
        TaskCreate(
            title=title,
            projectId=project_id,
            content=content,
            desc=desc,
            isAllDay=is_all_day,
            startDate=start_date,
            dueDate=due_date,
            timeZone=time_zone,
            reminders=reminder or None,
            repeatFlag=repeat_flag,
            priority=priority,
            sortOrder=sort_order,
            items=items or None,
        )
    )
    if ctx.obj.json_output:
        render_payload(task)
        return
    render_kv_table("Task", task.model_dump())


@task_app.command("update", help="更新任务。")
def task_update(
    ctx: typer.Context,
    task_id: str = typer.Option(..., "--task-id"),
    project_id: str = typer.Option(..., "--project-id"),
    title: str | None = typer.Option(None, "--title"),
    content: str | None = typer.Option(None, "--content"),
    desc: str | None = typer.Option(None, "--desc"),
    is_all_day: bool | None = typer.Option(None, "--all-day"),
    start_date: str | None = typer.Option(None, "--start-date"),
    due_date: str | None = typer.Option(None, "--due-date"),
    time_zone: str | None = typer.Option(None, "--time-zone"),
    reminder: list[str] | None = typer.Option(None, "--reminder"),
    repeat_flag: str | None = typer.Option(None, "--repeat"),
    priority: int | None = typer.Option(None, "--priority"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    item: list[str] | None = typer.Option(None, "--item"),
    item_json: str | None = typer.Option(
        None,
        "--item-json",
        help="JSON array string or @path to JSON file for checklist items.",
    ),
) -> None:
    if not any(
        [
            title,
            content,
            desc,
            is_all_day is not None,
            start_date,
            due_date,
            time_zone,
            reminder,
            repeat_flag,
            priority,
            sort_order,
            item,
            item_json,
        ]
    ):
        raise ApiError("No update fields provided.")
    client = get_client(ctx)
    items = parse_checklist_items(item, item_json)
    task = client.update_task(
        task_id,
        TaskUpdate(
            id=task_id,
            projectId=project_id,
            title=title,
            content=content,
            desc=desc,
            isAllDay=is_all_day,
            startDate=start_date,
            dueDate=due_date,
            timeZone=time_zone,
            reminders=reminder or None,
            repeatFlag=repeat_flag,
            priority=priority,
            sortOrder=sort_order,
            items=items or None,
        ),
    )
    if ctx.obj.json_output:
        render_payload(task)
        return
    render_kv_table("Task", task.model_dump())


@task_app.command("complete", help="完成指定任务。")
def task_complete(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    task_id: str = typer.Option(..., "--task-id"),
) -> None:
    client = get_client(ctx)
    client.complete_task(project_id, task_id)
    console.print("OK")


@task_app.command("delete", help="删除任务。")
def task_delete(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    task_id: str = typer.Option(..., "--task-id"),
) -> None:
    client = get_client(ctx)
    client.delete_task(project_id, task_id)
    console.print("OK")


@task_app.command(
    "create-receipt",
    help=(
        "cufenshen action outbox 专用 · 内部 search-before-create + ActionReceipt JSON stdout。\n"
        "不破坏原 `task create` 协议。给 daemon 用 · 不给人类用。"
    ),
)
def task_create_receipt(
    ctx: typer.Context,
    # === payload 字段 (ticktick 真要写的内容) ===
    title: str = typer.Option(..., "--title", help="任务标题。"),
    project_id: str = typer.Option(..., "--project-id", help="项目 ID。"),
    due_date: str | None = typer.Option(
        None, "--due-date",
        help="任务截止时间 ISO-8601 with offset · 例 '2026-05-17T20:00:00+0800'。",
    ),
    content: str | None = typer.Option(None, "--content", help="任务内容。"),
    priority: int | None = typer.Option(None, "--priority", help="优先级 0/1/3/5。"),
    # === echo 字段 (daemon 注入 · 1:1 透传到 receipt) ===
    app_name: str = typer.Option(..., "--app", help="cufenshen app 名 · 如 'agenda'。"),
    job_id: str = typer.Option(..., "--job-id", help="job 行 id。"),
    outbox_id: str = typer.Option(..., "--outbox-id", help="outbox 行 id (string)。"),
    event_id: str = typer.Option(..., "--event-id", help="触发的 event id。"),
    sink_id: str = typer.Option(
        "ticktick-cli", "--sink-id", help="sink skill_id · 默认 ticktick-cli。"
    ),
    idempotency_key: str = typer.Option(
        ..., "--idempotency-key",
        help="64-char sha256 hex · 由 daemon 计算好 · skill 只透传不算 hash。",
    ),
) -> None:
    """ticktick task create with ActionReceipt v1 stdout protocol.

    不论 success / duplicate / failed · stdout 永远是合法 ActionReceipt JSON。
    exit code 永远 0 · daemon 看 receipt.status 不看 exit code。
    """
    from datetime import datetime, timezone

    from action_receipt import build_action_receipt

    client = get_client(ctx)
    echo = {
        "app": app_name,
        "job_id": job_id,
        "outbox_id": outbox_id,
        "event_id": event_id,
        "sink_id": sink_id,
        "idempotency_key": idempotency_key,
    }
    payload = {
        "title": title,
        "project_id": project_id,
        "due_date": due_date,
        "content": content,
        "priority": priority,
    }
    # ISO-8601 with offset · 本地时间 · 例 "2026-05-18T01:00:01+08:00"
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    receipt = build_action_receipt(
        echo=echo,
        payload=payload,
        client=client,
        now_iso=now_iso,
    )

    # stdout 永远合法 JSON · 不走 rich · 不走 ANSI color · 不走 stderr
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


app.add_typer(project_app, name="project")
app.add_typer(task_app, name="task")


def run() -> None:
    try:
        app()
    except (ApiError, TicktickApiError) as exc:
        if exc.status_code:
            console.print(f"[red]Error:[/red] {exc} (status {exc.status_code})")
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    run()

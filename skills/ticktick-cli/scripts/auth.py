#!/usr/bin/env python3
"""ticktick-cli OAuth helper.

产品内普通用户路径：
  1. 产品包设置 TICKTICK_OAUTH_BROKER_URL，指向 FinClaw 自有 OAuth 服务
  2. `auth.py connect` 打开浏览器，用户只需要登录滴答清单并授权

开发者兜底路径：
  1. `auth.py register <id> <sec>`  保存自己的 OAuth 应用凭证
  2. `auth.py authorize`            起本地 server + 开浏览器 + 等 callback + 换 token + 落盘

底层命令（一般不用）：
  - `auth.py url`            只打印授权 URL（不开浏览器、不监听）
  - `auth.py callback <url>` 已有手抄回调 URL 时手动喂
  - `auth.py code <code>`    已经把 code 抠出来了
  - `auth.py status`         显示当前 OAuth 应用 + token 状态

OAuth 应用凭证（client_id/secret）和 access_token 都落在同一个文件：
`~/.covo/ticktick.json`（chmod 600），里面 oauth_app + access_token 两个字段。
CLI 主流程读 `TICKTICK_TOKEN` 环境变量；没设就从此文件 access_token 字段读。
也支持 `TICKTICK_CLIENT_ID` / `TICKTICK_CLIENT_SECRET` 环境变量覆盖 oauth_app。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Windows 控制台默认 cp936 不能输出"非 GBK 字符"——把 stdout/stderr 切成 utf-8
# 防止 print 中文 / Unicode 标点时 UnicodeEncodeError 崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

REDIRECT_URI = "http://localhost:18921/callback"
SCOPE = "tasks:write tasks:read"
AUTH_URL = "https://dida365.com/oauth/authorize"
TOKEN_URL = "https://dida365.com/oauth/token"

ENV_CLIENT_ID = "TICKTICK_CLIENT_ID"
ENV_CLIENT_SECRET = "TICKTICK_CLIENT_SECRET"
ENV_OAUTH_BROKER_URL = "TICKTICK_OAUTH_BROKER_URL"
BROKER_CALLBACK_PATH = "/broker-callback"

STATE_DIR = Path.home() / ".covo"
TOKEN_FILE = STATE_DIR / "ticktick.json"


def _load_state() -> dict:
    """读 ~/.covo/ticktick.json 全部状态（OAuth 应用凭证 + access_token）。
    文件不存在或损坏返回 {}。"""
    if not TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    """原子写回。强制 LF 行尾 + chmod 600。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(state, indent=2, ensure_ascii=False)
    with open(TOKEN_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def load_app_credentials() -> tuple[str, str]:
    """读 OAuth 应用凭证。优先级：环境变量 > ~/.covo/ticktick.json 的 oauth_app 字段。

    没找到就报错，要求开发者先到 https://developer.dida365.com/manage 注册自己的应用。
    普通用户不应该走这个函数；产品路径应使用 cmd_connect 的托管 OAuth。
    """
    cid = os.environ.get(ENV_CLIENT_ID)
    sec = os.environ.get(ENV_CLIENT_SECRET)
    if cid and sec:
        return cid, sec
    app = _load_state().get("oauth_app") or {}
    cid = cid or app.get("client_id")
    sec = sec or app.get("client_secret")
    if cid and sec:
        return cid, sec
    raise SystemExit(
        "ERROR: 没找到你的 OAuth 应用凭证。\n\n"
        "普通用户请回到 FinClaw 页面点击“连接滴答清单”。\n\n"
        "开发者兜底操作步骤：\n"
        "  1. 浏览器打开 https://developer.dida365.com/manage 登录你的滴答账号\n"
        "  2. 创建一个 OAuth 应用，名字随意（推荐 'ticktick-cli-<your-name>'）\n"
        "     redirect_uri 必须填：http://localhost:18921/callback\n"
        "  3. 拿到 Client ID 和 Client Secret 后，跑：\n\n"
        f"     python3 scripts/auth.py register <client_id> <client_secret>\n\n"
        f"     （会保存到 {TOKEN_FILE} 的 oauth_app 字段）\n\n"
        "  4. 然后跑：python3 scripts/auth.py authorize 走授权流程"
    )


def build_authorize_url(state: str = "ticktick-cli") -> str:
    cid, _ = load_app_credentials()
    params = {
        "client_id": cid,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def extract_code_from_callback(callback_url: str) -> str:
    parsed = urllib.parse.urlparse(callback_url.strip())
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("code", [None])[0]
    if not code:
        raise SystemExit(f"ERROR: 在 callback URL 里找不到 code 参数：{callback_url}")
    return code


def exchange_code_for_token(code: str) -> dict:
    cid, sec = load_app_credentials()
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cid,
            "client_secret": sec,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"ERROR: token 端点返回非 JSON：{raw}")


def save_token(token_data: dict) -> Path:
    """更新 ~/.covo/ticktick.json 的 token 字段，保留已有的 oauth_app。"""
    raw_access = token_data.get("access_token") or ""
    state = _load_state()  # 读出已有的 oauth_app + 旧 token
    state.update({
        "access_token": raw_access.strip(),  # 防御：去掉头尾空白/CR/LF
        "token_type": token_data.get("token_type"),
        "scope": token_data.get("scope"),
        "expires_in": token_data.get("expires_in"),
        "obtained_at": int(time.time()),
    })
    _save_state(state)
    return TOKEN_FILE


def managed_broker_url() -> str:
    """Return a configured first-party OAuth broker URL, if product packaging provides one."""
    return os.environ.get(ENV_OAUTH_BROKER_URL, "").strip().rstrip("/")


def _ensure_cli_deps() -> None:
    """确保 ticktick_cli.py 运行时依赖已装。register/authorize 阶段调用一次即可，
    免得用户后续跑 task list 时再去装依赖。"""
    required = ["typer", "httpx", "pydantic", "rich"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    print(f"[deps] ticktick_cli 缺依赖: {', '.join(missing)} -- 现在装上")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *missing]
        )
        print(f"[deps] OK: 装好了 {', '.join(missing)}")
    except subprocess.CalledProcessError as e:
        print(f"[deps] WARN: pip install 失败（{e}），稍后跑 task list 时可能再次报错。")
        print(f"[deps] 手动跑：pip install {' '.join(missing)}")


def cmd_register(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("用法：auth.py register <client_id> <client_secret>")
    cid, sec = argv[0].strip(), argv[1].strip()
    state = _load_state()  # 保留已有 token 字段
    state["oauth_app"] = {"client_id": cid, "client_secret": sec}
    _save_state(state)
    print(f"OK: OAuth 应用凭证已保存到 {TOKEN_FILE} 的 oauth_app 字段")
    print(f"  client_id: {cid}")
    print()
    # 顺手把后续 ticktick_cli 要的依赖装好，避免用户跑 task list 时再装
    _ensure_cli_deps()
    print()
    print("下一步：跑 auth.py authorize 一键完成授权（自动开浏览器+捕获回调+换 token）")
    return 0


def cmd_url(argv: list[str]) -> int:
    state = argv[0] if argv else "ticktick-cli"
    print(build_authorize_url(state))
    print()
    print("# 操作步骤：")
    print("# 1. 用浏览器打开上面这个 URL，登录你自己的滴答账号并授权")
    print(f"# 2. 浏览器会跳转到 {REDIRECT_URI}?code=xxx，页面打不开（没人监听）")
    print("# 3. 把整个跳转后的 URL 复制下来，喂给：")
    print("#    auth.py callback '<整个 URL>'")
    return 0


def cmd_callback(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("用法：auth.py callback <浏览器跳转的整个 URL>")
    code = extract_code_from_callback(argv[0])
    return _exchange_and_save(code)


def cmd_code(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("用法：auth.py code <code 值>")
    return _exchange_and_save(argv[0])


def _exchange_and_save(code: str) -> int:
    token_data = exchange_code_for_token(code)
    if "access_token" not in token_data:
        raise SystemExit(f"ERROR: token 交换失败：{json.dumps(token_data, ensure_ascii=False)}")
    path = save_token(token_data)
    print(f"OK: token 已保存到 {path}")
    print("CLI 主流程会自动从该文件读 token，可以直接调 ticktick_cli.py 任何命令。")
    return 0


def _open_browser(url: str) -> bool:
    """跨平台打开浏览器。返回是否触发成功；失败由调用方提示用户手动复制 URL。

    历史教训：Windows 端原本用 `os.startfile(url)`，在 QClaw/Claude Code 的 subprocess
    沙箱里偶发 silent 失败（找不到默认浏览器关联或没有 GUI session），用户看到的
    现象就是『终端没反应』。新策略三层兜底：
      1. 先用 stdlib `webbrowser.open()`——它内部会针对 Windows 试 `cmd start`，
         比裸 `os.startfile` 兼容性好
      2. 再显式 `cmd /c start "" <url>` —— `""` 是窗口标题占位，不加会把 URL 当标题
      3. 最后兜底也失败时，由 cmd_authorize 把 URL 打印得很显眼让用户手抄
    """
    try:
        import webbrowser
        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("win"):
            # 注意：start 后的 "" 是窗口标题，不加会把 URL 当成标题导致打不开
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


_callback_state: dict[str, object] = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    """一次性 server：抓到 GET /callback?code=xxx 就把 code 存到 state 并返回 HTML。"""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return  # 静音

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.endswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        code = (qs.get("code") or [None])[0]
        error = (qs.get("error") or [None])[0]
        if error:
            _callback_state["error"] = error
        if code:
            _callback_state["code"] = code

        body_html = (
            "<!doctype html><meta charset='utf-8'><title>ticktick-cli</title>"
            "<style>body{font-family:-apple-system,sans-serif;max-width:560px;"
            "margin:64px auto;padding:0 24px;line-height:1.6}h1{margin-bottom:8px}"
            ".ok{color:#2a7}.err{color:#c33}</style>"
            + (
                f"<h1 class='ok'>✓ 授权成功</h1><p>已经拿到 code，可以关闭这个页面回去看终端了。</p>"
                if code
                else f"<h1 class='err'>✗ 授权失败</h1><p>{error or '未知错误'}</p>"
            )
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body_html.encode("utf-8"))


class _BrokerCallbackHandler(BaseHTTPRequestHandler):
    """Receives an access token posted back from a first-party OAuth broker."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _finish(self, ok: bool, message: str) -> None:
        cls = "ok" if ok else "err"
        body_html = (
            "<!doctype html><meta charset='utf-8'><title>ticktick-cli</title>"
            "<style>body{font-family:-apple-system,sans-serif;max-width:560px;"
            "margin:64px auto;padding:0 24px;line-height:1.6}h1{margin-bottom:8px}"
            ".ok{color:#2a7}.err{color:#c33}</style>"
            f"<h1 class='{cls}'>{'授权成功' if ok else '授权失败'}</h1><p>{message}</p>"
        )
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body_html.encode("utf-8"))

    def _capture(self, params: dict[str, str]) -> None:
        error = params.get("error")
        token = params.get("access_token")
        if error:
            _callback_state["error"] = error
            self._finish(False, error)
            return
        if not token:
            _callback_state["error"] = "missing_access_token"
            self._finish(False, "没有收到 access_token。")
            return
        _callback_state["token_data"] = {
            "access_token": token,
            "token_type": params.get("token_type") or "Bearer",
            "scope": params.get("scope") or SCOPE,
            "expires_in": int(params["expires_in"]) if str(params.get("expires_in") or "").isdigit() else None,
        }
        self._finish(True, "已经写入本机，可以关闭这个页面。")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != BROKER_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.parse_qs(parsed.query)
        self._capture({key: values[0] for key, values in query.items() if values})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != BROKER_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = json.loads(raw or "{}")
            except json.JSONDecodeError:
                payload = {"error": "invalid_json_callback"}
        else:
            parsed_body = urllib.parse.parse_qs(raw)
            payload = {key: values[0] for key, values in parsed_body.items() if values}
        self._capture(payload)


def cmd_authorize(argv: list[str]) -> int:
    """一条龙：起本地 18921 server → 开浏览器到授权页 → 等 callback → 换 token → 落盘。"""
    timeout_seconds = 300
    for i, a in enumerate(argv):
        if a in ("--timeout", "-t") and i + 1 < len(argv):
            timeout_seconds = int(argv[i + 1])

    cid, _ = load_app_credentials()  # 缺凭证时直接报错
    auth_url = build_authorize_url()

    # 顺手装 ticktick_cli 依赖，免得用户跑 task list 时再装
    _ensure_cli_deps()
    print()

    _callback_state.clear()
    server = HTTPServer(("127.0.0.1", 18921), _CallbackHandler)
    server.timeout = 1.0  # handle_request 单次超时

    print(f"OAuth 应用 client_id: {cid}")
    print()
    print("=" * 70)
    print("如果浏览器没自动打开，请复制下面这一整行 URL 到浏览器：")
    print()
    print(auth_url)
    print()
    print("=" * 70)
    print()
    print(f"监听 http://localhost:18921/callback ... ({timeout_seconds}s 超时)")
    print("请在浏览器里：1) 用你的滴答账号登录  2) 点'授权'")
    print("收到回调后这里会自动完成换 token、落盘。")
    print()

    opened = _open_browser(auth_url)
    if opened:
        print("[browser] 已尝试自动打开浏览器；如果没弹窗请用上面的 URL 手动打开。")
    else:
        print("[browser] 自动打开失败——请用上面的 URL 在浏览器里手动打开。")

    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline and "code" not in _callback_state and "error" not in _callback_state:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in _callback_state:
        raise SystemExit(f"ERROR: 授权页返回 error={_callback_state['error']}")
    if "code" not in _callback_state:
        raise SystemExit(f"ERROR: {timeout_seconds}s 内没收到回调。重新跑一次试试。")

    code = str(_callback_state["code"])
    print(f"OK: 拿到 code（前 6 位 {code[:6]}...），正在换 token...")
    return _exchange_and_save(code)


def cmd_connect(argv: list[str]) -> int:
    """First-party managed OAuth: user only signs in and grants access in the browser.

    Product packaging should set TICKTICK_OAUTH_BROKER_URL to a FinClaw-owned broker
    that holds the OAuth client secret server-side. Without that broker, fall back to
    `register` + `authorize` for developers.
    """
    timeout_seconds = 300
    broker = managed_broker_url()
    for i, a in enumerate(argv):
        if a in ("--timeout", "-t") and i + 1 < len(argv):
            timeout_seconds = int(argv[i + 1])
        if a == "--broker-url" and i + 1 < len(argv):
            broker = argv[i + 1].strip().rstrip("/")
    if not broker:
        raise SystemExit(
            "ERROR: 未配置托管 OAuth 服务。\n\n"
            "面向普通用户的产品包应设置 TICKTICK_OAUTH_BROKER_URL，"
            "让用户只需在浏览器里登录滴答并点授权。\n\n"
            "开发者兜底路径仍可使用：auth.py register <client_id> <client_secret>，"
            "然后 auth.py authorize。"
        )

    _callback_state.clear()
    server = HTTPServer(("127.0.0.1", 18921), _BrokerCallbackHandler)
    server.timeout = 1.0

    return_to = f"http://127.0.0.1:18921{BROKER_CALLBACK_PATH}"
    authorize_url = (
        f"{broker}/authorize?"
        + urllib.parse.urlencode(
            {
                "scope": SCOPE,
                "state": "ticktick-cli",
                "return_to": return_to,
            }
        )
    )

    print("=" * 70)
    print("正在连接滴答清单。浏览器打开后，请登录你的滴答账号并点授权。")
    print("如果浏览器没自动打开，请复制下面这一整行 URL 到浏览器：")
    print()
    print(authorize_url)
    print()
    print("=" * 70)
    print()
    print(f"监听 {return_to} ... ({timeout_seconds}s 超时)")

    opened = _open_browser(authorize_url)
    if opened:
        print("[browser] 已尝试自动打开浏览器。")
    else:
        print("[browser] 自动打开失败——请用上面的 URL 在浏览器里手动打开。")

    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline and "token_data" not in _callback_state and "error" not in _callback_state:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in _callback_state:
        raise SystemExit(f"ERROR: 托管授权失败：{_callback_state['error']}")
    token_data = _callback_state.get("token_data")
    if not isinstance(token_data, dict):
        raise SystemExit(f"ERROR: {timeout_seconds}s 内没收到授权结果。重新点连接试试。")

    state = _load_state()
    state["oauth_app"] = {
        "managed_broker": broker,
        "client_id": "managed",
    }
    _save_state(state)
    path = save_token(token_data)
    print(f"OK: token 已保存到 {path}")
    print("滴答清单已经连接，可以重新采集。")
    return 0


def cmd_status(argv: list[str]) -> int:
    as_json = "--json" in argv
    state = _load_state()
    app = state.get("oauth_app") or {}
    token = state.get("access_token")
    broker = managed_broker_url()
    payload = {
        "ok": bool(token),
        "token_file": str(TOKEN_FILE),
        "has_token": bool(token),
        "has_oauth_app": bool(app.get("client_id") or os.environ.get(ENV_CLIENT_ID)),
        "oauth_app_source": "managed_broker"
        if app.get("managed_broker")
        else "file"
        if app.get("client_id")
        else "env"
        if os.environ.get(ENV_CLIENT_ID)
        else None,
        "managed_connect_available": bool(broker),
        "managed_broker_url": broker or None,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 1
    if app.get("client_id"):
        print(f"OAuth 应用       : {TOKEN_FILE} 的 oauth_app  (client_id: {app['client_id']})")
    elif os.environ.get(ENV_CLIENT_ID):
        print(f"OAuth 应用       : 走环境变量 (client_id: {os.environ[ENV_CLIENT_ID]})")
    else:
        print("OAuth 应用       : 普通用户请使用 auth.py connect；开发者才需要 register")
    print()
    if not state.get("access_token"):
        print(f"未找到 token：{TOKEN_FILE}")
        if broker:
            print("先跑 auth.py connect 完成授权流程")
        else:
            print("产品 OAuth 服务未配置；开发者兜底可用 auth.py register + auth.py authorize")
        return 1
    record = state
    obtained = record.get("obtained_at", 0)
    expires_in = record.get("expires_in", 0)
    print(f"Token 文件   : {TOKEN_FILE}")
    print(f"Scope        : {record.get('scope')}")
    print(f"Token type   : {record.get('token_type')}")
    print(f"Obtained at  : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(obtained))}")
    if expires_in:
        expires_at = obtained + expires_in
        remaining = expires_at - int(time.time())
        days = remaining // 86400
        print(
            f"Expires at   : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}"
            f"  ({'剩 ' + str(days) + ' 天' if remaining > 0 else '已过期'})"
        )
    if os.environ.get("TICKTICK_TOKEN"):
        match = os.environ["TICKTICK_TOKEN"] == record.get("access_token")
        print(f"环境变量     : 已设置（{'与文件匹配' if match else '与文件不一致'}）")
    else:
        print("环境变量     : 未设置 TICKTICK_TOKEN")
    return 0


COMMANDS = {
    "register": cmd_register,
    "authorize": cmd_authorize,
    "connect": cmd_connect,
    "url": cmd_url,
    "callback": cmd_callback,
    "code": cmd_code,
    "status": cmd_status,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print(f"  redirect_uri : {REDIRECT_URI}")
        print(f"  状态文件     : {TOKEN_FILE}  (含 oauth_app + access_token)")
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        raise SystemExit(f"未知命令：{cmd}。可用：{', '.join(COMMANDS)}")
    return COMMANDS[cmd](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

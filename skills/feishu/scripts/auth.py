#!/usr/bin/env python3
"""feishu OAuth helper.

⚠️ 每个用户必须用自己的飞书应用——不要共用别人的，否则后台数据会混。

正常用户路径——一条龙（推荐）：
  `auth.py setup`  自动启动 Chrome → 用户扫码登录飞书 → CDP 自动建应用、配回调、勾权限、发版 → 完成 OAuth

正常用户路径——分步（如果 setup 失败回退到手动）：
  1. `auth.py register <app_id> <app_secret>`  保存用户的飞书应用凭证
  2. `auth.py authorize`                       一条龙：起本地 server + 开浏览器 + 等 callback + 换 token + 落盘

底层命令（一般不用）：
  - `auth.py url`            只打印授权 URL（不开浏览器、不监听）
  - `auth.py callback <url>` 已有手抄回调 URL 时手动喂
  - `auth.py code <code>`    已经把 code 抠出来了
  - `auth.py refresh`        手动用 refresh_token 刷一次 user_token（一般 feishu_api 内自动）
  - `auth.py status`         显示当前应用 + token 状态

应用凭证（app_id/app_secret）和 access_token 都落在同一个文件：
`~/.cufin/skills-config/feishu.json`（chmod 600），里面 oauth_app + user_token + refresh_token 三个字段。
feishu_api.py 主流程会自动从该文件读 token；过期时会自动用 refresh_token 续。
也支持 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 环境变量覆盖 oauth_app。

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
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

REDIRECT_URI = "http://localhost:18921/callback"
# 默认 scope 列表——只放**无数据权限范围要求**的 scope，保证 setup 全自动发版。
# 录音豆（妙记）现有功能已覆盖：list 走 search:docs:read，get/transcript 走 docx:document
# （飞书把妙记产物存成 docx），不需要 minutes:minutes.transcript:export / artifacts:read
# 这两个特殊 scope。后两者只在直接调 minutes 专属 API（如批量导出原始 .opus）时才需要，
# 且要在飞书后台手动配"数据权限范围"才能开通。
SCOPE = " ".join([
    "im:message:readonly",
    "im:message",
    "im:chat:readonly",
    "im:resource",
    "drive:drive",
    "search:docs:read",
    "docx:document",
    "minutes:minutes:readonly",
])

FEISHU_API = "https://open.feishu.cn/open-apis"
AUTH_URL = f"{FEISHU_API}/authen/v1/authorize"
APP_TOKEN_URL = f"{FEISHU_API}/auth/v3/app_access_token/internal"
TOKEN_URL = f"{FEISHU_API}/authen/v1/oidc/access_token"
REFRESH_URL = f"{FEISHU_API}/authen/v1/oidc/refresh_access_token"

ENV_APP_ID = "FEISHU_APP_ID"
ENV_APP_SECRET = "FEISHU_APP_SECRET"

STATE_DIR = Path.home() / ".cufin" / "skills-config"
TOKEN_FILE = STATE_DIR / "feishu.json"


def _load_state() -> dict:
    """读 ~/.cufin/skills-config/feishu.json 全部状态（应用凭证 + user_token + refresh_token）。"""
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
    """读应用凭证。优先级：环境变量 > ~/.cufin/skills-config/feishu.json 的 oauth_app 字段。"""
    aid = os.environ.get(ENV_APP_ID)
    sec = os.environ.get(ENV_APP_SECRET)
    if aid and sec:
        return aid, sec
    app = _load_state().get("oauth_app") or {}
    aid = aid or app.get("app_id")
    sec = sec or app.get("app_secret")
    if aid and sec:
        return aid, sec
    raise SystemExit(
        "ERROR: 没找到你的飞书应用凭证。\n\n"
        "每个用户必须用自己的飞书应用——不要共用别人的，否则后台和配额会混。\n\n"
        "操作步骤：\n"
        "  1. 浏览器打开 https://open.feishu.cn/app 登录你的飞书账号\n"
        "  2. 创建一个『企业自建应用』，应用名随意（推荐 'feishu-cli-<your-name>'）\n"
        "  3. 在『安全设置』里把 redirect URL 加上：http://localhost:18921/callback ⚠️ 一字不差\n"
        "  4. 在『权限管理』里勾选你需要的 scope（doc / chat / minutes 等）并发布版本\n"
        "  5. 拿到『应用凭证』里的 App ID 和 App Secret 后，跑：\n\n"
        f"     python3 scripts/auth.py register <app_id> <app_secret>\n\n"
        f"     （会保存到 {TOKEN_FILE} 的 oauth_app 字段）\n\n"
        "  6. 然后跑：python3 scripts/auth.py authorize 走授权流程"
    )


def _http_post_json(url: str, body: dict, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method="POST", headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"ERROR: 端点 {url} 返回非 JSON：{raw[:200]}")


def get_app_access_token() -> str:
    """飞书 user OAuth 流程多一层：先用 app_id+secret 拿 app_access_token，再拿 user_token。"""
    aid, sec = load_app_credentials()
    resp = _http_post_json(APP_TOKEN_URL, {"app_id": aid, "app_secret": sec})
    tok = resp.get("app_access_token")
    if not tok:
        raise SystemExit(f"ERROR: 获取 app_access_token 失败：{json.dumps(resp, ensure_ascii=False)}")
    return tok


def build_authorize_url(state: str = "feishu-cli", scope: str | None = None) -> str:
    """构造飞书 OAuth 授权页 URL。

    scope 默认走模块 SCOPE 全集——这跟 setup 时勾的应用 enabled scope 一致，飞书校验
    『请求 ⊆ 应用 enabled』通过，token 拿到完整 scope 集，feishu_api 所有命令可用。

    ⚠️ 历史踩坑：
    - 不传 scope → 飞书只给默认 `auth:user.id:read`，im:chat:readonly / docx:document 等都没，
      cmd_chats / cmd_create_doc 全部 Unauthorized。
    - 传比 enabled 多的 scope（比如应用只开了 2 个但 URL 写 10 个）→ 报『当前应用权限不足』
      (20027)。所以默认 SCOPE 集必须严格等于 setup 实际勾上的 scope。
    - scope 显式传 None 跳过参数，给特殊场景（add-scopes 后等）用。
    """
    aid, _ = load_app_credentials()
    params = {
        "app_id": aid,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": scope if scope is not None else SCOPE,
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
    """用 code 换 user_token。需要先拿 app_access_token 当 Authorization。"""
    app_token = get_app_access_token()
    resp = _http_post_json(
        TOKEN_URL,
        {"grant_type": "authorization_code", "code": code},
        headers={"Authorization": f"Bearer {app_token}"},
    )
    if resp.get("code") != 0:
        raise SystemExit(f"ERROR: token 交换失败：{json.dumps(resp, ensure_ascii=False)}")
    return resp.get("data", {})


def refresh_user_token(refresh_token: str) -> dict:
    """用 refresh_token 续 user_token。飞书每次 refresh 会换新的 refresh_token + 重置 30 天有效期，
    所以只要每月用一次 skill 就永远不需要重新走 OAuth。"""
    app_token = get_app_access_token()
    resp = _http_post_json(
        REFRESH_URL,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {app_token}"},
    )
    if resp.get("code") != 0:
        raise SystemExit(f"ERROR: refresh 失败：{json.dumps(resp, ensure_ascii=False)}")
    return resp.get("data", {})


def save_token(token_data: dict) -> Path:
    """更新 ~/.cufin/skills-config/feishu.json 的 token 字段，保留已有的 oauth_app。"""
    user_token = (token_data.get("access_token") or "").strip()
    refresh_token = (token_data.get("refresh_token") or "").strip()
    expires_in = token_data.get("expires_in", 7200)
    state = _load_state()  # 保留 oauth_app
    state.update({
        "user_token": user_token,
        "refresh_token": refresh_token,
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type"),
        "expires_in": expires_in,
        # user_token 过期时间（提前 60s 当作过期，避免边界）
        "expires_at": int(time.time()) + int(expires_in) - 60,
        "obtained_at": int(time.time()),
    })
    _save_state(state)
    return TOKEN_FILE


def _ensure_cli_deps() -> None:
    """feishu_api.py 用 requests，预先装上免得用户跑命令时报缺依赖。"""
    required = ["requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    print(f"[deps] feishu_api 缺依赖: {', '.join(missing)} -- 现在装上")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *missing]
        )
        print(f"[deps] OK: 装好了 {', '.join(missing)}")
    except subprocess.CalledProcessError as e:
        print(f"[deps] WARN: pip install 失败（{e}），稍后跑命令时可能再次报错。")
        print(f"[deps] 手动跑：pip install {' '.join(missing)}")


def cmd_register(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("用法：auth.py register <app_id> <app_secret>")
    aid, sec = argv[0].strip(), argv[1].strip()
    state = _load_state()
    state["oauth_app"] = {"app_id": aid, "app_secret": sec}
    _save_state(state)
    _ensure_cli_deps()

    console_url = f"https://open.feishu.cn/app/{aid}"
    scopes = SCOPE.split()

    print(f"OK: 飞书应用凭证已保存到 {TOKEN_FILE} 的 oauth_app 字段")
    print(f"  app_id: {aid}")
    print()
    print("=" * 70)
    print("⚠️  在跑 authorize 之前，必须先在飞书开放平台后台配好这个应用")
    print("=" * 70)
    print()
    print("应用后台直跳链接（AI 用 open/start/xdg-open 帮用户打开）：")
    print()
    print(f"  {console_url}")
    print()
    print("打开后在左侧导航点 3 个菜单，按顺序完成：")
    print()
    print("  ① 安全设置 → 重定向 URL → 添加（一字不差，可直接复制）：")
    print()
    print(f"     {REDIRECT_URI}")
    print()
    print("  ② 权限管理 → 勾选下面这些 scope（搜索 + 勾上 + 申请发布）：")
    for sc in scopes:
        print(f"     - {sc}")
    print()
    print("  ③ 版本管理与发布 → 创建版本并发布上线（自建应用必须发布才能用）")
    print()
    print("=" * 70)
    print("3 件事都配好后，再跑：auth.py authorize")
    print("（authorize 会自动开浏览器 + 监听回调 + 换 token + 落盘）")
    print("=" * 70)
    return 0


def cmd_url(argv: list[str]) -> int:
    state = argv[0] if argv else "feishu-cli"
    print(build_authorize_url(state))
    print()
    print("# 操作步骤：")
    print("# 1. 用浏览器打开上面这个 URL，登录你自己的飞书账号并授权")
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
        raise SystemExit(f"ERROR: token 交换返回缺 access_token：{json.dumps(token_data, ensure_ascii=False)}")
    path = save_token(token_data)
    print(f"OK: token 已保存到 {path}")
    print(f"     scope: {token_data.get('scope')}")
    print("feishu_api 主流程会自动从该文件读 token，可以直接调任何命令。")
    return 0


def cmd_refresh(argv: list[str]) -> int:
    """手动刷 token（一般 feishu_api.py 自动调，不需要用户管）。"""
    state = _load_state()
    rt = state.get("refresh_token")
    if not rt:
        raise SystemExit("ERROR: 没有 refresh_token，先跑 auth.py authorize 完整授权一次")
    token_data = refresh_user_token(rt)
    save_token(token_data)
    print(f"OK: token 已刷新并保存到 {TOKEN_FILE}")
    return 0


def _open_browser(url: str) -> bool:
    """跨平台打开浏览器。返回是否触发成功；失败由调用方提示用户手动复制 URL。

    历史教训：Windows 端原本用 `os.startfile(url)`，在 QClaw/Claude Code 的 subprocess
    沙箱里偶发 silent 失败（找不到默认浏览器关联或没有 GUI session），用户看到的
    现象就是『终端没反应』。新策略三层兜底：
      1. 先用 stdlib `webbrowser.open()`——它内部针对 Windows 试 `cmd start`，
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
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

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
            "<!doctype html><meta charset='utf-8'><title>feishu</title>"
            "<style>body{font-family:-apple-system,sans-serif;max-width:560px;"
            "margin:64px auto;padding:0 24px;line-height:1.6}h1{margin-bottom:8px}"
            ".ok{color:#2a7}.err{color:#c33}</style>"
            + (
                "<h1 class='ok'>✓ 授权成功</h1><p>已经拿到 code，可以关闭这个页面回去看终端了。</p>"
                if code
                else f"<h1 class='err'>✗ 授权失败</h1><p>{error or '未知错误'}</p>"
            )
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body_html.encode("utf-8"))


def cmd_authorize(argv: list[str]) -> int:
    """一条龙：起本地 18921 server → 开浏览器到授权页 → 等 callback → 换 token → 落盘。"""
    timeout_seconds = 300
    for i, a in enumerate(argv):
        if a in ("--timeout", "-t") and i + 1 < len(argv):
            timeout_seconds = int(argv[i + 1])

    aid, _ = load_app_credentials()
    auth_url = build_authorize_url()

    _ensure_cli_deps()
    print()

    _callback_state.clear()
    server = HTTPServer(("127.0.0.1", 18921), _CallbackHandler)
    server.timeout = 1.0

    print(f"飞书应用 app_id: {aid}")
    print()
    print("=" * 70)
    print("如果下面的自动化失败，可手动复制 URL 到浏览器：")
    print()
    print(auth_url)
    print()
    print("=" * 70)
    print()
    print(f"监听 http://localhost:18921/callback ... ({timeout_seconds}s 超时)")
    print()

    # 优先：chrome-auto profile（已登录飞书）走 CDP 全自动 navigate + 点击『授权』。
    # 兜底：webbrowser.open + 等用户手动点击。
    auto_clicked = False
    try:
        chrome_setup = _import_chrome_setup()
        if chrome_setup.is_chrome_running():
            print("[auth] 检测到 chrome-auto profile 在跑，走 CDP 全自动模式")
            import threading
            def _click_in_thread():
                try:
                    ok = chrome_setup.click_authorize_button(auth_url, timeout=20)
                    print(f"[auth] CDP 自动点击『授权』{'成功' if ok else '失败——按钮没找到，可手动点击'}")
                except Exception as e:
                    print(f"[auth] CDP 自动点击异常: {e}（可手动点击或等 webbrowser fallback）")
            threading.Thread(target=_click_in_thread, daemon=True).start()
            auto_clicked = True
    except Exception as e:
        print(f"[auth] CDP 不可用，fallback 到 webbrowser: {e}")

    if not auto_clicked:
        opened = _open_browser(auth_url)
        if opened:
            print("[browser] 已尝试自动打开浏览器；请在浏览器里点『授权』")
        else:
            print("[browser] 自动打开失败——请用上面的 URL 在浏览器里手动打开 + 点『授权』")

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


def _import_chrome_setup():
    _ensure_cli_deps()
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("[setup] 装 websockets ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "websockets"])
    try:
        import chrome_setup
    except ImportError:
        here = Path(__file__).resolve().parent
        sys.path.insert(0, str(here))
        import chrome_setup
    return chrome_setup


def cmd_setup(argv: list[str]) -> int:
    """一条龙自动化：启动 Chrome → 用户扫码登录飞书 → CDP 自动建应用、配回调、勾权限、发版 → 完成 OAuth。

    用法：
      auth.py setup                                              # 自动新建一个企业自建应用，默认 10 个 scope
      auth.py setup --app-name <name>                            # 指定新建应用名
      auth.py setup --app-id cli_xxx --app-secret xxx            # 用已有应用，仅自动配置
      auth.py setup --scopes im:resource,docx:document           # 自定义 scope（逗号分隔），不传用默认 10 个
    """
    app_name = None
    app_id = None
    app_secret = None
    scopes = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--app-name" and i + 1 < len(argv):
            app_name = argv[i + 1]; i += 2
        elif a == "--app-id" and i + 1 < len(argv):
            app_id = argv[i + 1]; i += 2
        elif a == "--app-secret" and i + 1 < len(argv):
            app_secret = argv[i + 1]; i += 2
        elif a == "--scopes" and i + 1 < len(argv):
            scopes = [s.strip() for s in argv[i + 1].split(",") if s.strip()]
            i += 2
        else:
            i += 1

    chrome_setup = _import_chrome_setup()

    if app_id and app_secret:
        # 用户传了完整凭证——只跑 CDP 自动化（配回调/勾权限/发版）+ OAuth
        state = _load_state()
        state["oauth_app"] = {"app_id": app_id, "app_secret": app_secret}
        _save_state(state)
        # secret 已知，跳过 _grab_credentials 避免触发原生 prompt 弹窗
        result = chrome_setup.run_setup(app_id=app_id, app_secret=app_secret, scopes=scopes)
    else:
        # 全自动新建
        result = chrome_setup.run_setup(app_name=app_name, app_id=app_id, scopes=scopes)
        # 把抓到的凭证落盘
        state = _load_state()
        state["oauth_app"] = {"app_id": result["app_id"], "app_secret": result["app_secret"]}
        _save_state(state)
        print(f"[setup] 凭证已落 {TOKEN_FILE}（app_id={result['app_id']}）")

    print()
    print("=" * 70)
    print("Chrome 自动化完成。下一步走 OAuth 拿 user_token...")
    print("=" * 70)
    print()
    return cmd_authorize([])


def cmd_add_scopes(argv: list[str]) -> int:
    """给已有飞书应用追加 scope + 自动发新版本（不建应用，不动 secret）。

    飞书自建应用的 scope 状态绑在版本上——改了 scope 必须发新版本号才对线上生效。
    本命令做的事：找到应用 → 在 /auth 抽屉勾上传入的 scope → 创建新版本（自动用唯一时间戳号）→ 发布上线。

    用法：
      auth.py add-scopes <app_id> <scope1> [<scope2>...]   # 显式传 app_id
      auth.py add-scopes <scope1> [<scope2>...]            # 用 ~/.cufin/skills-config/feishu.json 已注册的 app_id

    示例：
      auth.py add-scopes cli_a979xxx im:message:write
      auth.py add-scopes im:resource docx:document
    """
    if not argv:
        raise SystemExit("用法：auth.py add-scopes [<app_id>] <scope1> [<scope2>...]")

    # 第 1 个参数是 cli_xxx 就当 app_id，否则从 state 读
    if argv[0].startswith("cli_"):
        app_id = argv[0]
        scopes = argv[1:]
    else:
        state = _load_state()
        app_id = (state.get("oauth_app") or {}).get("app_id")
        if not app_id:
            raise SystemExit("ERROR: 没传 app_id 也没在 ~/.cufin/skills-config/feishu.json 找到注册过的应用——请显式传 cli_xxx")
        scopes = list(argv)

    if not scopes:
        raise SystemExit("ERROR: 至少传一个 scope")

    chrome_setup = _import_chrome_setup()
    chrome_setup.run_enable_scopes(app_id, scopes)
    print(f"OK: 已追加 {len(scopes)} 个 scope 到 {app_id}（已发新版本）：")
    for s in scopes:
        print(f"     - {s}")
    print()
    print("⚠️ 飞书 scope 生效需要 1-2 分钟同步。如果立刻调 API 报权限不足，等会儿再试。")
    return 0


def cmd_delete(argv: list[str]) -> int:
    """删除指定的飞书应用（先停用再删除）。

    用法：auth.py delete <app_id>
    """
    if not argv:
        raise SystemExit("用法：auth.py delete <app_id>")
    app_id = argv[0].strip()

    chrome_setup = _import_chrome_setup()
    chrome_setup.run_delete(app_id)
    print(f"OK: 应用 {app_id} 已删除")
    return 0


def cmd_status(argv: list[str]) -> int:
    state = _load_state()
    app = state.get("oauth_app") or {}
    if app.get("app_id"):
        print(f"飞书应用       : {TOKEN_FILE} 的 oauth_app  (app_id: {app['app_id']})")
    elif os.environ.get(ENV_APP_ID):
        print(f"飞书应用       : 走环境变量 (app_id: {os.environ[ENV_APP_ID]})")
    else:
        print("飞书应用       : 未注册——跑 auth.py register <app_id> <app_secret> 先注册")
    print()
    if not state.get("user_token"):
        print(f"未找到 user_token：{TOKEN_FILE}")
        print("先跑 auth.py authorize 完成授权流程")
        return 1
    obtained = state.get("obtained_at", 0)
    expires_at = state.get("expires_at", 0)
    print(f"Token 文件     : {TOKEN_FILE}")
    print(f"Scope          : {state.get('scope')}")
    print(f"Token type     : {state.get('token_type')}")
    print(f"Obtained at    : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(obtained))}")
    if expires_at:
        remaining = expires_at - int(time.time())
        if remaining > 0:
            mins = remaining // 60
            print(f"User_token     : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}  (剩 {mins} 分钟)")
        else:
            print(f"User_token     : 已过期 {-remaining // 60} 分钟（feishu_api 调用时会自动用 refresh_token 续）")
    rt = state.get("refresh_token")
    if rt:
        print(f"Refresh_token  : 有（长度 {len(rt)}），飞书 30 天滑窗——每月用一次就永远不过期")
    else:
        print("Refresh_token  : 无——下次 user_token 过期需要重新走 OAuth")
    return 0


COMMANDS = {
    "setup": cmd_setup,
    "add-scopes": cmd_add_scopes,
    "delete": cmd_delete,
    "register": cmd_register,
    "authorize": cmd_authorize,
    "url": cmd_url,
    "callback": cmd_callback,
    "code": cmd_code,
    "refresh": cmd_refresh,
    "status": cmd_status,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print(f"  redirect_uri : {REDIRECT_URI}")
        print(f"  状态文件     : {TOKEN_FILE}  (含 oauth_app + user_token + refresh_token)")
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        raise SystemExit(f"未知命令：{cmd}。可用：{', '.join(COMMANDS)}")
    return COMMANDS[cmd](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Chrome CDP 自动化：在飞书开放平台一条龙建应用、配回调、勾权限、发版。

公开入口：
  run_setup(app_name=None, app_id=None) -> dict
    返回 {"app_id": ..., "app_secret": ...}

设计原则：
- 用户的飞书登录态保留在 ~/.cufin/skills-config/chrome-auto profile 里（CUFIN_CHROME_PROFILE 可覆盖）
- 调试端口默认 9222（CUFIN_CHROME_PORT 可覆盖）
- Chrome 没启动会自动启动；端口已被占用就直接复用
- 没登录的话，会把 Chrome 窗口前置 + 在终端 wait 用户扫码
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[setup] 缺依赖 websockets，正在安装...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "websockets"])
    import websockets  # noqa: F401

CHROME_PORT = int(os.environ.get("CUFIN_CHROME_PORT") or "9222")
CHROME_PROFILE = Path(
    os.environ.get("CUFIN_CHROME_PROFILE")
    or str(Path.home() / ".cufin" / "skills-config" / "chrome-auto")
)
FEISHU_BASE = "https://open.feishu.cn"
REDIRECT_URI = "http://localhost:18921/callback"

# 与 auth.py 的 SCOPE 保持一致——但这里是 list 形式，方便拼 URL ?q=
#
# ⚠️ 这 10 个 scope 已覆盖文档读写、聊天列表、录音豆 list+get（妙记产物存成 docx，
# 走 search:docs:read + docx:document 即可），不需要那两个带"数据权限范围"要求的
# minutes:minutes.transcript:export / artifacts:read（要在飞书后台手动配数据范围才能发版）。
# 只有要直接调 minutes 专属 API（批量导出 .opus 原始音频等）才需要补那两个。
SCOPES = [
    "im:message:readonly",       # 读消息
    "im:message",                # cmd_send_msg 发消息（不带 readonly 后缀=读+写）
    "im:chat:readonly",          # cmd_chats 列聊天
    "im:resource",               # cmd_upload_file 上传 IM 素材
    "drive:drive",               # cmd_folders 云空间读写
    "search:docs:read",          # cmd_search / cmd_recordings_list
    "docx:document",             # cmd_doc / cmd_create_doc / cmd_recordings_get
    "minutes:minutes:readonly",  # 妙记列表/查看（无数据范围要求）
]
# 已剔：vc:meeting / vc:meeting.meetingevent:read / wiki:wiki（feishu_api 没用，且飞书后台
# 2026-04-30 起这些被过滤，传进 ?q= 抽屉里直接不显示——不知是数据范围要求新加还是改名）。
# 已踩坑：im:message:send_as_user 不是真实 scope 名（被飞书过滤），改 im:message。


# ============================================================ #
# Chrome 进程管理
# ============================================================ #

def _chrome_binary() -> str:
    """找一个 Chromium 内核浏览器的可执行路径，跨平台。

    探测顺序：Chrome → Edge → Brave → Chromium。Edge 是 Windows 预装（覆盖率近 100%），
    Brave / Chromium 也都基于 Chromium 内核，CDP `--remote-debugging-port` 全兼容。
    """
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
    elif sys.platform.startswith("win"):
        # Windows 探测按浏览器分组（Chrome 全部探测方式 → Edge 全部 → Brave 全部），
        # 让 Chrome 优先级最高——校长偏好 Chrome，且 Edge/Brave 在 Win 上预装率高，
        # 否则 Edge 会在固定路径阶段先命中、压过校长真正想用的 Chrome。
        # 单浏览器内的探测顺序：注册表 App Paths → 固定标准路径 → 递归扫安装根目录。
        try:
            import winreg
        except ImportError:
            winreg = None

        BROWSERS = [
            ("chrome.exe", [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ], [
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome"),
                r"C:\Program Files\Google\Chrome",
                r"C:\Program Files (x86)\Google\Chrome",
            ]),
            ("msedge.exe", [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ], [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge"),
            ]),
            ("brave.exe", [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ], [
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware"),
            ]),
        ]
        for exe_name, fixed_paths, search_roots in BROWSERS:
            # 1. 注册表 App Paths——标准安装会注册到这
            if winreg is not None:
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}") as k:
                            path, _ = winreg.QueryValueEx(k, "")
                            if path and Path(path).exists():
                                return path
                    except OSError:
                        continue
            # 2. 固定标准路径
            for p in fixed_paths:
                if Path(p).exists():
                    return p
            # 3. 递归扫安装根目录——覆盖绿色版/便携版/非标准子目录
            #    （Chrome 109 等装在 %LOCALAPPDATA%\Google\Chrome\Bin\chrome.exe，
            #    没注册到 App Paths/Uninstall/PATH，标准路径全 miss，只有递归才能找到）
            for root in search_roots:
                if not Path(root).exists():
                    continue
                for f in Path(root).rglob(exe_name):
                    # 跳过 chrome_proxy.exe / chrome_pwa_launcher.exe 等同名 helper
                    if f.name == exe_name and f.is_file():
                        return str(f)
    else:  # linux
        for name in [
            "google-chrome", "google-chrome-stable",
            "microsoft-edge", "microsoft-edge-stable",
            "brave-browser", "brave",
            "chromium", "chromium-browser",
        ]:
            path = shutil.which(name)
            if path:
                return path
    raise SystemExit(
        "ERROR: 找不到 Chromium 内核浏览器。\n"
        "请安装下面任一并重试：\n"
        "  - Google Chrome:   https://www.google.com/chrome/\n"
        "  - Microsoft Edge:  https://www.microsoft.com/edge\n"
        "  - Brave:           https://brave.com/\n"
        "或设环境变量 CUFIN_CHROME_BIN 指向已安装的 Chromium 系浏览器路径。"
    )


def _is_chrome_running() -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{CHROME_PORT}/json/list", timeout=1.5)
        return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def _launch_chrome() -> None:
    """以调试模式启动 Chrome。如果已有实例在 CHROME_PORT 上跑，直接复用。"""
    if _is_chrome_running():
        print(f"[setup] 已有 Chrome 调试实例在端口 {CHROME_PORT}，直接复用")
        return

    bin_override = os.environ.get("CUFIN_CHROME_BIN")
    chrome_bin = bin_override or _chrome_binary()
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

    print(f"[setup] 启动 Chrome（调试模式）")
    print(f"        binary  : {chrome_bin}")
    print(f"        profile : {CHROME_PROFILE}")
    print(f"        port    : {CHROME_PORT}")

    args = [
        chrome_bin,
        f"--remote-debugging-port={CHROME_PORT}",
        f"--user-data-dir={CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--lang=zh-CN",
        f"{FEISHU_BASE}/app",
    ]
    if sys.platform.startswith("win"):
        # Windows 上用 DETACHED_PROCESS 避免 Chrome 跟 Python 进程绑定
        DETACHED = 0x00000008
        subprocess.Popen(args, creationflags=DETACHED, close_fds=True)
    else:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    # 等启动
    for _ in range(20):
        time.sleep(0.5)
        if _is_chrome_running():
            print(f"[setup] Chrome 启动成功")
            return
    raise SystemExit(f"ERROR: Chrome 没在 10s 内起来（端口 {CHROME_PORT}）。请手动启动后重试。")


# ============================================================ #
# CDP 工具函数（参考 feishu-bot-creator）
# ============================================================ #

def _list_tabs() -> list[dict]:
    raw = urllib.request.urlopen(f"http://localhost:{CHROME_PORT}/json/list", timeout=3).read()
    return json.loads(raw)


def _new_tab(url: str) -> str:
    """新开 tab。返回 ws_url。"""
    raw = urllib.request.urlopen(
        f"http://localhost:{CHROME_PORT}/json/new?{urllib.parse.quote(url, safe='')}",
        method="PUT", timeout=3,
    ).read() if False else urllib.request.urlopen(
        # /json/new 在新版 Chrome 里需 PUT；老版 GET 也行——用 PUT 兼容
        urllib.request.Request(
            f"http://localhost:{CHROME_PORT}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT",
        ),
        timeout=3,
    ).read()
    return json.loads(raw)["webSocketDebuggerUrl"]


def _get_feishu_ws() -> str:
    """找到飞书的 tab 的 ws_url。没有就新建一个。"""
    for tab in _list_tabs():
        url = tab.get("url", "")
        if "open.feishu.cn" in url and tab.get("type") == "page":
            return tab["webSocketDebuggerUrl"]
    # 没有飞书 tab，找一个空白 page tab 复用
    for tab in _list_tabs():
        if tab.get("type") == "page":
            return tab["webSocketDebuggerUrl"]
    # 实在没有就新开一个
    return _new_tab(f"{FEISHU_BASE}/app")


_msg_id = 0


def _next_id() -> int:
    global _msg_id
    _msg_id += 1
    return _msg_id


async def _eval(ws, js: str, wait: float = 0):
    """跑 JS，返回 result.value（可能是 None / str / number / bool）。"""
    mid = _next_id()
    await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                              "params": {"expression": js, "awaitPromise": False, "returnByValue": True}}))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == mid:
            break
    if wait:
        await asyncio.sleep(wait)
    res = msg.get("result", {}).get("result", {})
    return res.get("value")


async def _click_xy(ws, x: int, y: int) -> None:
    for ev in ("mousePressed", "mouseReleased"):
        mid = _next_id()
        await ws.send(json.dumps({"id": mid, "method": "Input.dispatchMouseEvent",
                                  "params": {"type": ev, "x": x, "y": y, "button": "left", "clickCount": 1}}))
        # drain
        while True:
            raw = await ws.recv()
            if json.loads(raw).get("id") == mid:
                break


async def _click_by_js(ws, js_finder: str, retry_seconds: float = 10) -> bool:
    """js_finder 是一段 JS 表达式返回一个 element。

    ⚠️ 优先用 JS `el.click()`——不依赖屏幕坐标，元素在视口外（小屏要滚动才看到）也能触发
    React onClick。CDP 的 Input.dispatchMouseEvent 按 (x, y) 派发，元素滚出视口时坐标处
    渲染的不是目标按钮，click 静默失效（校长 2026-04-30 拔掉扩展屏后实测复现）。

    例外：飞书的 input checkbox 必须走真实 mouse event——cb.click() 飞书 React 不接，
    框架会假装一片 .checked=true 但实际状态没绑（cycle test 已踩坑）。所以 input checkbox/radio
    回退 mouse 路径。

    内置 retry：找不到时每 0.5s 重试。
    """
    end = time.time() + retry_seconds
    while True:
        result = await _eval(ws, f"""
            (() => {{
                const el = {js_finder};
                if (!el) return null;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return null;
                // input checkbox/radio：飞书 React 不接 .click()，回退 mouse event
                if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {{
                    el.scrollIntoView({{block: 'center', inline: 'center'}});
                    const r2 = el.getBoundingClientRect();
                    return {{mode: 'mouse', x: Math.round(r2.x + r2.width/2), y: Math.round(r2.y + r2.height/2)}};
                }}
                // 其他所有元素：滚到视口内（保险）+ JS .click() 触发 React handler
                el.scrollIntoView({{block: 'center', inline: 'center'}});
                el.click();
                return {{mode: 'js'}};
            }})()
        """)
        if isinstance(result, dict):
            if result.get("mode") == "js":
                return True
            if result.get("mode") == "mouse":
                await _click_xy(ws, result["x"], result["y"])
                return True
        if time.time() > end:
            return False
        await asyncio.sleep(0.5)


async def _type_into(ws, js_finder: str, text: str) -> None:
    """聚焦元素，清空已有内容，再用 Input.insertText 输入（兼容 React）。"""
    await _eval(ws, f"(() => {{ const el = {js_finder}; if (el) {{ el.focus(); el.value=''; }} }})()")
    await asyncio.sleep(0.2)
    await _click_by_js(ws, js_finder)
    await asyncio.sleep(0.2)
    # Cmd+A / Ctrl+A 全选
    mod = 4 if sys.platform == "darwin" else 2  # 4=Meta, 2=Control
    for evt in ("keyDown", "keyUp"):
        mid = _next_id()
        await ws.send(json.dumps({"id": mid, "method": "Input.dispatchKeyEvent",
                                  "params": {"type": evt, "key": "a", "code": "KeyA", "modifiers": mod}}))
        while True:
            r = await ws.recv()
            if json.loads(r).get("id") == mid:
                break
    mid = _next_id()
    await ws.send(json.dumps({"id": mid, "method": "Input.insertText", "params": {"text": text}}))
    while True:
        r = await ws.recv()
        if json.loads(r).get("id") == mid:
            break
    await asyncio.sleep(0.3)


async def _navigate(ws, url: str, wait: float = 3) -> None:
    mid = _next_id()
    await ws.send(json.dumps({"id": mid, "method": "Page.navigate", "params": {"url": url}}))
    while True:
        r = await ws.recv()
        if json.loads(r).get("id") == mid:
            break
    await asyncio.sleep(wait)


async def _wait_for(ws, js_cond: str, timeout: float = 15, interval: float = 1) -> bool:
    """轮询 js_cond，truthy 时返回 True。"""
    end = time.time() + timeout
    while time.time() < end:
        v = await _eval(ws, js_cond)
        if v:
            return True
        await asyncio.sleep(interval)
    return False


# ============================================================ #
# 飞书后台业务流程
# ============================================================ #

async def _ensure_logged_in(ws) -> None:
    """跳到 /app，检查登录态。没登录就提示用户扫码，等回来。"""
    await _navigate(ws, f"{FEISHU_BASE}/app", wait=3)
    title = await _eval(ws, "document.title")
    if title and "登录" not in str(title) and "Login" not in str(title):
        # 二次验证：URL 不应含 passport
        url = await _eval(ws, "window.location.href")
        if url and "passport" not in str(url) and "/login" not in str(url):
            print(f"[setup] 飞书已登录（{title}）")
            return

    print()
    print("=" * 70)
    print("⚠️  飞书没登录")
    print("=" * 70)
    print()
    print("请在弹出的 Chrome 窗口里**用手机飞书扫码登录**。")
    print("登录完成后 → 终端会自动检测到 → 继续执行。")
    print()

    # 轮询登录态：等到 URL 跳回 /app 或不包含 login/passport
    end = time.time() + 300
    while time.time() < end:
        await asyncio.sleep(2)
        url = await _eval(ws, "window.location.href")
        if not url:
            continue
        if "passport" not in str(url) and "/login" not in str(url) and "open.feishu.cn/app" in str(url):
            print(f"[setup] 检测到登录完成（{url}）")
            return
    raise SystemExit("ERROR: 5 分钟内没检测到登录完成。重新跑 setup 试试。")


async def _create_app(ws, name: str) -> str:
    """在 /app 列表页点"创建企业自建应用"，填表 → 拿 app_id。"""
    await _navigate(ws, f"{FEISHU_BASE}/app", wait=2)

    print(f"[setup] 创建应用 '{name}'")
    clicked = await _click_by_js(ws, """
        (() => {
            const btns = document.querySelectorAll('button, [role="button"], a');
            for (const b of btns) {
                if (b.textContent && b.textContent.includes('创建企业自建应用')
                    && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """)
    if not clicked:
        raise SystemExit("ERROR: 没找到 '创建企业自建应用' 按钮——飞书后台 UI 可能改了")
    await asyncio.sleep(2)

    # 名称输入框（弹窗里第一个 input width > 200）
    name_finder = """
        (() => {
            const dlg = document.querySelector('[class*="modal"], [class*="Modal"], [role="dialog"]') || document.body;
            const ins = dlg.querySelectorAll('input');
            for (const i of ins) { if (i.getBoundingClientRect().width > 200) return i; }
            return null;
        })()
    """
    await _type_into(ws, name_finder, name)
    desc_finder = """
        (() => {
            const dlg = document.querySelector('[class*="modal"], [class*="Modal"], [role="dialog"]') || document.body;
            return dlg.querySelector('textarea');
        })()
    """
    await _type_into(ws, desc_finder, f"{name} - feishu CLI（用户 OAuth）")

    # 点 "创建" 按钮
    await _eval(ws, """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                if (b.textContent && b.textContent.trim() === '创建' && b.offsetWidth > 0) { b.click(); return; }
            }
        })()
    """)
    await asyncio.sleep(3)

    app_id = await _eval(ws, """
        (() => { const m = window.location.href.match(/\\/app\\/(cli_[a-z0-9]+)/i); return m ? m[1] : ''; })()
    """)
    if not app_id:
        raise SystemExit("ERROR: 没拿到 app_id——可能创建失败，去 Chrome 看下报错")
    print(f"[setup] 应用创建成功 app_id={app_id}")
    return str(app_id)


async def _add_redirect_uri(ws, app_id: str) -> None:
    """跳到安全设置，添加 redirect URL。

    飞书 /safe 页是 inline 编辑模式（不是弹窗）：
      1. 点"添加"按钮 → 页面新增一行带 input 的编辑行
      2. 在 input 里填 URL（用 Input.insertText 兼容 React）
      3. 再点一次"添加"按钮 → 提交保存

    DOM 顺序：重定向 URL 块在 IP 白名单块之前，所以页面上第一个可见的"添加"按钮
    就是重定向 URL 的添加按钮。
    """
    print(f"[setup] 配置回调地址 {REDIRECT_URI}")
    await _navigate(ws, f"{FEISHU_BASE}/app/{app_id}/safe", wait=4)

    # 已经存在就跳过
    has = await _eval(ws, f"""
        (() => document.body.innerText.includes('{REDIRECT_URI}'))()
    """)
    if has:
        print("[setup] 回调地址已存在，跳过")
        return

    add_btn_finder = """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '添加'
                    && b.offsetWidth > 0 && b.offsetHeight > 0 && !b.disabled) return b;
            }
            return null;
        })()
    """

    # 第 1 步：点"添加"打开 inline 输入行
    if not await _click_by_js(ws, add_btn_finder, retry_seconds=15):
        raise SystemExit("ERROR: 安全设置页没找到 '添加' 按钮")
    await asyncio.sleep(1.5)

    # 第 2 步：在 inline input（placeholder 含 'URL'）里填 URL
    url_input_finder = """
        (() => {
            for (const i of document.querySelectorAll('input')) {
                if (i.placeholder && i.placeholder.includes('URL') && i.offsetWidth > 0
                    && i.type !== 'hidden') return i;
            }
            return null;
        })()
    """
    if not await _click_by_js(ws, url_input_finder, retry_seconds=8):
        raise SystemExit("ERROR: inline URL 输入框没出现")
    await _type_into(ws, url_input_finder, REDIRECT_URI)

    # 第 3 步：再点一次"添加"按钮 → 提交
    if not await _click_by_js(ws, add_btn_finder, retry_seconds=5):
        raise SystemExit("ERROR: 提交时第二次找不到 '添加' 按钮")
    await asyncio.sleep(2)

    # 验证（最多等 5 秒让保存生效）
    for _ in range(10):
        has = await _eval(ws, f"""
            (() => document.body.innerText.includes('{REDIRECT_URI}'))()
        """)
        if has:
            print("[setup] 回调地址添加成功")
            return
        await asyncio.sleep(0.5)
    raise SystemExit("ERROR: 回调地址添加后没在页面上看到")


async def _enable_scopes(ws, app_id: str, scopes: list[str] | None = None) -> None:
    """跳到 /auth?q=<scopes>...：飞书自动打开抽屉并把这些 scope 列出来（不预选），
    我们再 CDP 一个个点 checkbox + 点"确认开通权限"。

    抽屉打开慢，必须等 visible checkbox 出现再开始勾。

    scopes 不传时用模块默认 SCOPES（首次 setup 用）；add-scopes 场景显式传需要追加的。
    """
    scopes = scopes if scopes is not None else SCOPES
    print(f"[setup] 开通 {len(scopes)} 个 scope（用户身份 user_access_token）")
    q = ",".join(scopes)
    # token_type=user 让抽屉默认展开"用户身份"tab——OAuth user token 需要这个，
    # 不是 tenant_access_token（那个是应用身份，给 server-to-server 用）
    url = f"{FEISHU_BASE}/app/{app_id}/auth?q={urllib.parse.quote(q)}&op_from=openapi&token_type=user"
    await _navigate(ws, url, wait=2)

    # 等抽屉打开 + N 个 visible checkbox 就绪
    print("[setup] 等抽屉打开...")
    ready = await _wait_for(ws, f"""
        (() => Array.from(document.querySelectorAll('input.ud__checkbox__input'))
            .filter(cb => cb.getBoundingClientRect().width > 0).length >= {len(scopes)})()
    """, timeout=20, interval=1)
    if not ready:
        raise SystemExit(f"ERROR: 20s 内 scope 抽屉没出现 {len(scopes)} 个 checkbox——飞书可能改 UI 了")

    # 🔍 诊断 dump：每个 visible checkbox 的 idx / checked / 邻近 scope code 文本
    async def dump_state(stage: str):
        snap = await _eval(ws, """
            JSON.stringify((() => {
                const cbs = Array.from(document.querySelectorAll('input.ud__checkbox__input'));
                const out = [];
                cbs.forEach((cb, idx) => {
                    const r = cb.getBoundingClientRect();
                    if (r.width === 0) return;
                    // 找邻近 scope code（im:resource 等模式）—— 抽屉里通常每行 checkbox 旁有 scope 文本
                    const row = cb.closest('tr, [class*="row"], [class*="item"], li, div');
                    let scopeCode = '';
                    if (row) {
                        const m = (row.textContent || '').match(/[a-z]+(?::[a-z][a-z0-9._:\\-]*){1,3}/);
                        if (m) scopeCode = m[0];
                    }
                    out.push({idx, checked: cb.checked, w: Math.round(r.width), y: Math.round(r.y), scope: scopeCode.slice(0, 50)});
                });
                return out;
            })())
        """)
        try:
            arr = json.loads(snap) if isinstance(snap, str) else snap
        except Exception:
            arr = []
        n_checked = sum(1 for x in arr if x.get('checked'))
        print(f"[diag {stage}] visible={len(arr)} checked={n_checked}")
        for x in arr[:20]:
            print(f"  [{x['idx']:2d}] checked={x['checked']} y={x['y']:4d} {x['scope']}")

    await dump_state("init")

    # 勾 visible 未勾的 checkboxes
    for attempt in range(5):
        unchecked = await _eval(ws, """
            (() => Array.from(document.querySelectorAll('input.ud__checkbox__input'))
                .filter(cb => !cb.checked && cb.getBoundingClientRect().width > 0).length)()
        """)
        if not unchecked or int(unchecked) == 0:
            break
        print(f"[setup]   还剩 {unchecked} 个未勾，第 {attempt+1} 轮点击")
        for i in range(int(unchecked)):
            ok = await _click_by_js(ws, """
                (() => {
                    for (const cb of document.querySelectorAll('input.ud__checkbox__input')) {
                        if (!cb.checked && cb.getBoundingClientRect().width > 0) return cb;
                    }
                    return null;
                })()
            """, retry_seconds=0.5)
            if not ok:
                break
            # ⚠️ 每次 click 后必须 sleep——飞书 React 提交 state 同步比 DOM 渲染慢，
            # 不等就连 click 时下一次拿到的 element 可能还在旧 DOM tree（已被 React detach）
            # mouse click 落到 stale 节点失效。
            await asyncio.sleep(0.25)
        await dump_state(f"after-attempt-{attempt+1}")
        await asyncio.sleep(0.5)

    # ⚠️⚠️ 关键修复：勾完后**必须等 2 秒**让 React 内部 state 完全 propagate 到提交载荷。
    # 校长 Win 实测：肉眼看 checkbox 都勾上了（DOM checked=true），但立刻点"确认开通权限"，
    # 飞书后端收到 0 scope——React internal submit state 比 DOM 渲染慢一拍，提交时 state
    # 还是空的。dump_state 只能看到 DOM 状态，看不到 React 内部 state，所以 dump OK 不代表
    # 真的 OK。这 2 秒是经验值，足够 React 跑完 batch update 把 checked 同步进 form state。
    await asyncio.sleep(2)
    await dump_state("before-confirm")

    # 点"确认开通权限"——按钮就在抽屉底部，已经 visible
    print("[setup] 点确认开通权限")
    clicked = await _click_by_js(ws, """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                const t = (b.textContent || '').trim();
                if ((t === '确认开通权限' || t.startsWith('确认开通')) && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """, retry_seconds=2)
    if not clicked:
        raise SystemExit("ERROR: 没找到 '确认开通权限' 按钮")
    # 二次确认弹窗——飞书 ud__dialog__wrap，弹出有动画，0.4s 足够
    await asyncio.sleep(0.4)
    await _click_by_js(ws, """
        (() => {
            const dlgs = document.querySelectorAll('[class*="ud__dialog__wrap"], [class*="ud__confirm"], [role="dialog"]');
            for (const m of dlgs) {
                if (m.offsetWidth === 0) continue;
                for (const b of m.querySelectorAll('button')) {
                    const t = (b.textContent || '').trim();
                    if ((t === '确认' || t === '确定' || t === '确认开通') && b.offsetWidth > 0) return b;
                }
            }
            return null;
        })()
    """, retry_seconds=2)
    print("[setup] scope 开通完成")


async def _publish_version(ws, app_id: str, version: str | None = None, force: bool = False) -> None:
    """跳到 /version，创建版本 + 发布。

    version=None 时自动生成（首次=1.0.0，已有版本=按 unix 时间戳衍生新号）。
    force=False（默认）：列表里已有"已发布"版本就跳过——首次 setup 后再跑 setup 是幂等的。
    force=True：即使有已发布版本也建新版（add-scopes 场景，scope 改了必须发新版才生效）。

    飞书表单的关键坑（2026-04-30 实测）：
    1. 版本号 input 的 placeholder + defaultValue 都是 1.0.0，但 React state 是空的——
       必须用真实键盘输入（CDP Input.dispatchKeyEvent，带 text）让 React onChange 接住，
       否则点保存按钮 enabled 但 click 没反应（校验失败）。
    2. 失败的保存会留下"草稿"在版本列表里——下次再跑，新建版本号跟草稿冲突，
       保存按钮仍 enabled 但 click 不响应。所以**有未发布草稿就跳过创建**。
    """
    await _navigate(ws, f"{FEISHU_BASE}/app/{app_id}/version", wait=4)

    # 检查列表里有无版本（已发布或草稿都算）——精确判断比文字 match 稳
    has_existing = await _eval(ws, """
        (() => {
            const text = document.body.innerText;
            if (text.includes('已上线') || text.includes('已发布')) return 'published';
            if (text.includes('暂无数据')) return 'empty';
            return 'unknown';
        })()
    """)
    if has_existing == 'published' and not force:
        print("[setup] 应用已发布版本，跳过")
        return
    if has_existing != 'empty' and has_existing != 'published':
        print(f"[setup] WARN: 版本列表状态={has_existing}，可能有未发布草稿——请手动到飞书后台 /version 清理后重跑")
        return

    # 版本号：首次用 1.0.0，否则按 unix 时间戳生成（绝不会撞，单调递增）
    if version is None:
        version = "1.0.0" if has_existing == 'empty' else f"1.0.{int(time.time()) % 100000}"

    print(f"[setup] 创建版本 {version} 并发布")

    # 点页面上"创建版本"按钮（顶部 banner + 列表里都有，第一个就行）
    clicked = await _click_by_js(ws, """
        (() => {
            for (const b of document.querySelectorAll('button, a')) {
                if ((b.textContent || '').trim() === '创建版本' && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """, retry_seconds=10)
    if not clicked:
        raise SystemExit("ERROR: 没找到 '创建版本' 按钮")
    await asyncio.sleep(4)

    # 用真实键盘输入填版本号——这才能让飞书 React state 接住
    # （单纯设 input.value 或 _type_into 的 select-all+insertText 在飞书 ud__native-input 上不可靠）
    if not await _click_by_js(ws, """
        Array.from(document.querySelectorAll('input')).find(i =>
            i.placeholder && i.placeholder.includes('版本号') && i.offsetWidth > 0)
    """, retry_seconds=8):
        raise SystemExit("ERROR: 版本号输入框没找到")
    await asyncio.sleep(0.3)

    # 三连点选中已有内容（如果有 default value）+ Backspace 清掉
    pos = await _eval(ws, """
        (() => {
            const i = Array.from(document.querySelectorAll('input')).find(x => x.placeholder && x.placeholder.includes('版本号'));
            if (!i) return null;
            const r = i.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        })()
    """)
    for ev in ("mousePressed", "mouseReleased"):
        mid = _next_id()
        await ws.send(json.dumps({"id": mid, "method": "Input.dispatchMouseEvent",
                                  "params": {"type": ev, "x": pos["x"], "y": pos["y"],
                                             "button": "left", "clickCount": 3}}))
        while True:
            r = await ws.recv()
            if json.loads(r).get("id") == mid:
                break
    await asyncio.sleep(0.2)
    for ev in ("keyDown", "keyUp"):
        mid = _next_id()
        await ws.send(json.dumps({"id": mid, "method": "Input.dispatchKeyEvent",
                                  "params": {"type": ev, "key": "Backspace",
                                             "code": "Backspace", "windowsVirtualKeyCode": 8}}))
        while True:
            r = await ws.recv()
            if json.loads(r).get("id") == mid:
                break
    await asyncio.sleep(0.2)

    # 一字一字真实键盘输入（带 text，触发 React onChange）
    for ch in version:
        for evt_type in ("keyDown", "keyUp"):
            mid = _next_id()
            params = {"type": evt_type, "key": ch}
            if evt_type == "keyDown":
                params["text"] = ch
                params["unmodifiedText"] = ch
            await ws.send(json.dumps({"id": mid, "method": "Input.dispatchKeyEvent", "params": params}))
            while True:
                r = await ws.recv()
                if json.loads(r).get("id") == mid:
                    break
        await asyncio.sleep(0.08)
    await asyncio.sleep(0.5)

    # 描述 textarea：飞书可能预填了"更新应用版本"，沿用
    desc_value = await _eval(ws, """
        (() => {
            const t = Array.from(document.querySelectorAll('textarea')).find(x =>
                x.placeholder && (x.placeholder.includes('更新') || x.placeholder.includes('说明')));
            return t ? t.value : '';
        })()
    """)
    if not desc_value:
        # 默认值都没有——必须填一个非空才能保存
        desc_finder = """
            Array.from(document.querySelectorAll('textarea')).find(t =>
                t.placeholder && (t.placeholder.includes('更新') || t.placeholder.includes('说明')))
        """
        await _type_into(ws, desc_finder, "feishu CLI 自动发布")

    # 点保存——_click_by_js 内部会先 scrollIntoView 再 JS .click()，不依赖视口坐标
    save_clicked = await _click_by_js(ws, """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '保存' && b.offsetWidth > 0 && !b.disabled) return b;
            }
            return null;
        })()
    """, retry_seconds=5)
    if not save_clicked:
        raise SystemExit("ERROR: 没找到可点击的 '保存' 按钮")

    # 等保存生效——成功的话 URL 会从 /version/create 跳走
    saved = await _wait_for(ws, """
        (() => !window.location.href.includes('/version/create'))()
    """, timeout=15, interval=1)
    if not saved:
        raise SystemExit(
            "ERROR: 保存按钮点了但页面没跳转。\n"
            f"可能版本号 {version} 跟现有草稿冲突——到飞书后台 /app/{app_id}/version 删掉旧版本后重跑。"
        )
    await asyncio.sleep(2)

    # 跳到 /version 页后弹出"确认提交发布申请？"对话框（class: ud__dialog__wrap / ud__confirm）
    # 飞书的主按钮 class 是 ud__button--filled（不是 primary！别按 primary 过滤）
    print("[setup]   等确认发布弹窗...")
    confirm_clicked = await _click_by_js(ws, """
        (() => {
            // 飞书 confirm dialog 的容器
            const dlgs = document.querySelectorAll('[class*="ud__dialog__wrap"], [class*="ud__confirm"], [role="dialog"], [class*="modal"]');
            for (const m of dlgs) {
                if (m.offsetWidth === 0) continue;
                for (const b of m.querySelectorAll('button')) {
                    if ((b.textContent || '').trim() === '确认发布' && b.offsetWidth > 0) return b;
                }
            }
            // fallback：页面上任意 visible 按钮文字 = "确认发布"
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '确认发布' && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """, retry_seconds=12)
    if not confirm_clicked:
        print("[setup]   WARN: 没找到确认发布按钮——可能飞书直接发布了，或需要手动确认")
    else:
        await asyncio.sleep(3)

    # 验证：版本列表里出现"已上线"或"已发布"
    is_live = await _wait_for(ws, """
        (() => document.body.innerText.includes('已上线') || document.body.innerText.includes('已发布'))()
    """, timeout=10, interval=1)
    if is_live:
        print("[setup] 版本已发布上线")
    else:
        print("[setup] WARN: 没看到'已上线'状态，可能还在审核中——后续 OAuth 仍可工作")


async def _grab_credentials(ws, app_id: str) -> tuple[str, str]:
    """跳到 /baseinfo，点 App Secret 旁的"眼睛"按钮显示明文，从 .secret-code__code 读 secret。

    飞书 /baseinfo App Secret 行（class 含 `auth-info__secret`）DOM 结构（2026-05 实测）：
        <div class="auth-info__secret">
          <label>App Secret</label>
          <span class="secret-code__code">∗∗∗∗∗...</span>  ← secret 显示位置
          <div class="secret-code__btns">
            <span class="secret-code__btn"><svg data-icon="CopyOutlined"/></span>   ← [0] 复制
            <span class="secret-code__btn"><svg data-icon=".../眼睛"/></span>       ← [1] 眼睛
          </div>
          <button><svg/></button>  ← 刷新（重置 secret，别点）
        </div>

    踩坑：原代码用模糊 selector + 全行 textContent 正则匹配 30-40 alnum，遇到不同应用的
    页面可能匹配到 Verification Token / Encrypt Key 等其他 32 位 alnum，导致 OAuth
    换 token 报『app secret invalid』(10014)。新代码用精确 selector .secret-code__code
    直接读，不搞正则，绝对不会抓错。
    """
    print(f"[setup] 抓取 app_secret")
    await _navigate(ws, f"{FEISHU_BASE}/app/{app_id}/baseinfo", wait=3)

    # 1. JS click 第 2 个 .secret-code__btn（眼睛——idx 0 是复制，idx 1 是眼睛）
    clicked = await _eval(ws, """
        (() => {
            const row = document.querySelector('.auth-info__secret');
            if (!row) return 'no_row';
            const btns = row.querySelectorAll('.secret-code__btn');
            if (btns.length < 2) return 'no_eye';  // 没有眼睛按钮
            btns[1].click();
            return 'clicked';
        })()
    """)
    if clicked != "clicked":
        raise SystemExit(f"ERROR: /baseinfo 找不到 App Secret 眼睛按钮（{clicked}）——飞书 UI 可能改了")
    await asyncio.sleep(1.5)

    # 2. 从 .secret-code__code 读 secret 明文（不走正则，直接 textContent）
    secret = await _eval(ws, """
        (() => {
            const row = document.querySelector('.auth-info__secret');
            if (!row) return '';
            const code = row.querySelector('.secret-code__code');
            if (!code) return '';
            const txt = (code.textContent || '').trim();
            // 如果还是显示星号（明文没切换成功），返回空让上层重试/报错
            if (txt.includes('∗') || txt.includes('*')) return '';
            return txt;
        })()
    """)

    if not secret or len(secret) < 16:
        raise SystemExit(
            f"ERROR: 没拿到合法的 app_secret（拿到 {len(secret) if secret else 0} 字符）。\n"
            f"请到飞书后台 → /app/{app_id}/baseinfo 手动复制 App Secret，然后跑：\n"
            f"  python3 scripts/auth.py register {app_id} <app_secret>"
        )

    print(f"[setup] app_secret 已抓到（长度 {len(secret)}）")
    return app_id, secret


# ============================================================ #
# 删除应用（先在管理后台停用，再到开发者后台删除）
# ============================================================ #

async def _disable_app(ws, app_id: str) -> None:
    """在飞书管理后台停用应用——已发布的应用必须先停用才能删除。"""
    print(f"[delete] 停用应用 {app_id}")
    # www.feishu.cn 会自动重定向到当前用户租户的子域
    await _navigate(ws, f"https://www.feishu.cn/admin/appCenter/manage/{app_id}", wait=5)

    # 找"已启用"开关（飞书 ud__switch.ud__switch-checked），点了变停用
    toggled = await _eval(ws, """
        (() => {
            const btn = document.querySelector('button.ud__switch.ud__switch-checked');
            if (btn) { btn.click(); return 'clicked'; }
            return 'not_found';
        })()
    """)
    if toggled == "not_found":
        print("[delete]   应用可能已经是停用状态，跳过")
        return
    await asyncio.sleep(2)

    # 弹出确认对话框：点"停用"
    await _click_by_js(ws, """
        (() => {
            const dlgs = document.querySelectorAll('[class*="ud__dialog__wrap"], [class*="ud__confirm"], [role="dialog"]');
            for (const m of dlgs) {
                if (m.offsetWidth === 0) continue;
                for (const b of m.querySelectorAll('button')) {
                    if ((b.textContent || '').trim() === '停用' && b.offsetWidth > 0) return b;
                }
            }
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '停用' && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """, retry_seconds=3)
    await asyncio.sleep(2)
    print("[delete]   应用已停用")


async def _delete_app_in_dev_console(ws, app_id: str) -> None:
    """在开发者后台 /baseinfo 页面点'删除应用'按钮。"""
    print(f"[delete] 删除应用 {app_id}")
    await _navigate(ws, f"{FEISHU_BASE}/app/{app_id}/baseinfo", wait=3)
    await _eval(ws, "window.scrollTo(0, document.body.scrollHeight)", wait=1)

    clicked = await _click_by_js(ws, """
        (() => {
            for (const el of document.querySelectorAll('button, a, span')) {
                if ((el.textContent || '').trim() === '删除应用' && el.offsetWidth > 0) return el;
            }
            return null;
        })()
    """, retry_seconds=5)
    if not clicked:
        raise SystemExit("ERROR: /baseinfo 没找到 '删除应用' 按钮")
    await asyncio.sleep(2)

    # 确认对话框点"删除"
    await _click_by_js(ws, """
        (() => {
            const dlgs = document.querySelectorAll('[class*="ud__dialog__wrap"], [class*="ud__confirm"], [role="dialog"]');
            for (const m of dlgs) {
                if (m.offsetWidth === 0) continue;
                for (const b of m.querySelectorAll('button')) {
                    if ((b.textContent || '').trim() === '删除' && b.offsetWidth > 0) return b;
                }
            }
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '删除' && b.offsetWidth > 0) return b;
            }
            return null;
        })()
    """, retry_seconds=5)
    await asyncio.sleep(3)

    # 验证：URL 应该跳走或者页面变空
    final_url = await _eval(ws, "window.location.href")
    if app_id in str(final_url):
        print(f"[delete]   WARN: 删除后 URL 仍含 app_id，可能删除失败")
    else:
        print(f"[delete]   应用已删除")


async def _async_delete(app_id: str) -> None:
    _launch_chrome()
    ws_url = _get_feishu_ws()
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": _next_id(), "method": "Page.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": _next_id(), "method": "Runtime.enable"}))
        await ws.recv()
        await _ensure_logged_in(ws)
        # 先在管理后台停用（已发布的应用必须先停用）
        try:
            await _disable_app(ws, app_id)
        except Exception as e:
            print(f"[delete]   停用阶段出错（继续尝试删除）: {e}")
        # 再到开发者后台删除
        await _delete_app_in_dev_console(ws, app_id)


def run_delete(app_id: str) -> None:
    """同步入口：删除应用。"""
    asyncio.run(_async_delete(app_id))


async def _async_click_authorize(auth_url: str, timeout: float = 30) -> bool:
    """在 chrome-auto profile（已登录态）navigate 到飞书 OAuth 授权 URL 并自动点"授权"按钮。

    返回 True/False（是否点到按钮）。点击后飞书会 302 redirect 到 redirect_uri
    （http://localhost:18921/callback?code=...），由调用方的 HTTP server 接住——
    本函数不等 callback。
    """
    _launch_chrome()
    ws_url = _get_feishu_ws()
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": _next_id(), "method": "Page.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": _next_id(), "method": "Runtime.enable"}))
        await ws.recv()
        await _navigate(ws, auth_url, wait=3)
        return await _click_by_js(ws, """
            (() => {
                for (const b of document.querySelectorAll('button, [role="button"]')) {
                    const t = (b.textContent || '').trim();
                    // 飞书 OAuth 授权页主按钮文本是『授权』；某些场景可能是『同意』『允许』
                    if ((t === '授权' || t === '同意' || t === '允许') && b.offsetWidth > 0) return b;
                }
                return null;
            })()
        """, retry_seconds=timeout)


def click_authorize_button(auth_url: str, timeout: float = 30) -> bool:
    """同步入口：在 chrome-auto profile 自动点击飞书 OAuth 授权页的『授权』按钮。

    前提：Chrome 调试端口（默认 9222）已在跑，profile 里已登录飞书。
    返回 True/False（是否点到按钮）。
    """
    return asyncio.run(_async_click_authorize(auth_url, timeout))


def is_chrome_running() -> bool:
    """暴露给 auth.py 用——让 cmd_authorize 自动判断走 CDP 还是 webbrowser。"""
    return _is_chrome_running()


# ============================================================ #
# 公开入口
# ============================================================ #

async def _async_run(app_name: str | None, app_id: str | None,
                     app_secret: str | None = None,
                     scopes: list[str] | None = None) -> dict:
    _launch_chrome()
    ws_url = _get_feishu_ws()
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        # Page domain 必须开（很多操作要等 navigation）
        await ws.send(json.dumps({"id": _next_id(), "method": "Page.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": _next_id(), "method": "Runtime.enable"}))
        await ws.recv()

        await _ensure_logged_in(ws)

        if not app_id:
            # 飞书应用名上限 32 字符——`platform.node()` 在长机器名（含 .local 后缀）
            # 下能撑到 40+，必须截断；从 hostname 末尾向前保留 21 字符，前面拼 `fs-cli-`（7）= 28
            host = platform.node().replace(".local", "")
            name = app_name or f"fs-cli-{host[-21:]}"
            name = name[:32]
            app_id = await _create_app(ws, name)
        else:
            print(f"[setup] 使用已有应用 app_id={app_id}")

        await _add_redirect_uri(ws, app_id)
        await _enable_scopes(ws, app_id, scopes)
        await _publish_version(ws, app_id)

        # secret 已经传进来（用户用 --app-secret 模式）就别重抓——
        # 飞书"复制 App Secret"按钮触发原生 prompt 弹窗，CDP handler 偶发抓不到
        if app_secret:
            print(f"[setup] app_secret 已传入（长度 {len(app_secret)}），跳过抓取")
            return {"app_id": app_id, "app_secret": app_secret}

        aid, secret = await _grab_credentials(ws, app_id)
        return {"app_id": aid, "app_secret": secret}


def run_setup(app_name: str | None = None, app_id: str | None = None,
              app_secret: str | None = None,
              scopes: list[str] | None = None) -> dict:
    """同步入口：从零建应用 → 配回调 → 勾权限 → 发版 → 抓 secret。

    scopes 不传时用模块默认 SCOPES（10 个：im/drive/docx/wiki/vc/minutes:readonly）。
    返回 {'app_id': ..., 'app_secret': ...}。
    """
    return asyncio.run(_async_run(app_name, app_id, app_secret, scopes))


async def _async_enable_scopes(app_id: str, scopes: list[str]) -> None:
    _launch_chrome()
    ws_url = _get_feishu_ws()
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": _next_id(), "method": "Page.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": _next_id(), "method": "Runtime.enable"}))
        await ws.recv()
        await _ensure_logged_in(ws)
        await _enable_scopes(ws, app_id, scopes)
        # 已发布的应用必须重新发新版本号才能让新 scope 生效（force=True）
        await _publish_version(ws, app_id, force=True)


def run_enable_scopes(app_id: str, scopes: list[str]) -> None:
    """给已有应用追加 scope + 自动发新版本（不建应用，不动 secret）。

    scope 改了必须发新版才生效——飞书自建应用的 scope 状态绑在版本上，
    旧版本是已勾的旧 scope 集合，新 scope 只有发新版本号后才对线上生效。
    """
    if not scopes:
        raise ValueError("scopes 不能为空")
    asyncio.run(_async_enable_scopes(app_id, scopes))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="飞书自建应用 CDP 一条龙配置")
    sub = p.add_subparsers(dest="cmd")

    p_setup = sub.add_parser("setup", help="建应用 + 配回调 + 勾权限 + 发版（默认子命令）")
    p_setup.add_argument("--app-name", help="应用名称（仅当不传 --app-id 时新建）")
    p_setup.add_argument("--app-id", help="已有应用 ID（cli_xxx）；不传时新建")
    p_setup.add_argument("--scopes", help="逗号分隔的 scope 列表；不传用默认 10 个")

    p_add = sub.add_parser("add-scopes", help="给已有应用追加 scope + 发新版")
    p_add.add_argument("app_id", help="应用 ID（cli_xxx）")
    p_add.add_argument("scopes", nargs="+", help="要追加的 scope（多个空格分隔）")

    # 兼容旧用法：直接 chrome_setup.py --app-name xxx 当 setup 处理
    args, unknown = p.parse_known_args()
    if args.cmd is None:
        args = p_setup.parse_args(unknown)
        args.cmd = "setup"

    if args.cmd == "add-scopes":
        run_enable_scopes(args.app_id, args.scopes)
        print(f"OK: 已追加 {len(args.scopes)} 个 scope 到 {args.app_id}（已发新版）")
    else:
        scopes_list = [s.strip() for s in args.scopes.split(",") if s.strip()] if getattr(args, "scopes", None) else None
        res = run_setup(app_name=args.app_name, app_id=args.app_id, scopes=scopes_list)
        print()
        print(f"app_id     = {res['app_id']}")
        print(f"app_secret = {res['app_secret']}")

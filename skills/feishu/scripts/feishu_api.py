#!/usr/bin/env python3
"""
飞书API工具 - 完整版
支持：文档读取、文档创建、聊天消息搜索、文件上传、消息发送、录音豆转写
"""

import argparse
import json
import os
import re
import sys
import time
import subprocess
from pathlib import Path

# Windows 控制台默认 cp936 不能输出非 GBK 字符——把 stdout/stderr 切成 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# 自动装 requests 依赖（首次跑 skill 时不让用户卡在 ModuleNotFoundError）
try:
    import requests
except ImportError:
    print("[deps] feishu_api 缺 requests，现在装上", file=sys.stderr)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "requests"]
    )
    import requests

FEISHU_API = "https://open.feishu.cn/open-apis"

# 状态文件统一在 ~/.cufin/skills-config/feishu.json，结构：
#   {"oauth_app": {"app_id": ..., "app_secret": ...},
#    "user_token": ..., "refresh_token": ..., "expires_at": ...}
# auth.py 写、feishu_api.py 读+自动 refresh。
STATE_DIR = Path.home() / ".cufin" / "skills-config"
TOKEN_FILE = STATE_DIR / "feishu.json"

# 旧路径兼容：~/.feishu_tokens.json（feishu skill 0.1.0 之前的位置）
LEGACY_TOKEN_FILE = Path.home() / ".feishu_tokens.json"


# ==================== Token管理 ====================

def _load_state() -> dict:
    """读 ~/.cufin/skills-config/feishu.json。文件不存在时若有老 ~/.feishu_tokens.json 会自动迁移。"""
    if not TOKEN_FILE.exists():
        if LEGACY_TOKEN_FILE.exists():
            try:
                legacy = json.loads(LEGACY_TOKEN_FILE.read_text(encoding="utf-8"))
                migrated = {
                    "user_token": legacy.get("user_token", ""),
                    "refresh_token": legacy.get("refresh_token", ""),
                    "expires_at": legacy.get("expires_at", 0),
                }
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                with open(TOKEN_FILE, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(migrated, f, indent=2, ensure_ascii=False)
                try:
                    os.chmod(TOKEN_FILE, 0o600)
                except OSError:
                    pass
                print(f"[migrate] 已迁移 {LEGACY_TOKEN_FILE} → {TOKEN_FILE}（仍要 register 应用凭证）",
                      file=sys.stderr)
                return migrated
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(state, indent=2, ensure_ascii=False)
    with open(TOKEN_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def _load_app_credentials():
    """app_id/app_secret 优先级：环境变量 > ~/.cufin/skills-config/feishu.json oauth_app 字段"""
    aid = os.environ.get("FEISHU_APP_ID")
    sec = os.environ.get("FEISHU_APP_SECRET")
    if aid and sec:
        return aid, sec
    app = _load_state().get("oauth_app") or {}
    aid = aid or app.get("app_id")
    sec = sec or app.get("app_secret")
    if aid and sec:
        return aid, sec
    print(
        "ERROR: 没找到飞书应用凭证。每个用户必须用自己的飞书应用。\n"
        "  跑 `python3 scripts/auth.py register <app_id> <app_secret>` 注册一次，\n"
        "  详见 SKILL.md 的『首次授权 SOP』。",
        file=sys.stderr,
    )
    sys.exit(1)


def get_app_token():
    """飞书 user OAuth 流程多一层：先用 app_id+secret 拿 app_access_token。"""
    aid, sec = _load_app_credentials()
    resp = requests.post(f"{FEISHU_API}/auth/v3/app_access_token/internal",
                         json={"app_id": aid, "app_secret": sec})
    return resp.json().get("app_access_token", "")


def _save_tokens(user_token, refresh_token, expires_in=7200):
    """保留 oauth_app + 其他字段，只更新 token。expires_at 提前 60s 当过期。"""
    state = _load_state()
    state.update({
        "user_token": (user_token or "").strip(),
        "refresh_token": (refresh_token or "").strip(),
        "expires_in": expires_in,
        "expires_at": time.time() + expires_in - 60,
        "obtained_at": int(time.time()),
    })
    _save_state(state)


def get_user_token():
    """获取 user_access_token，过期则自动用 refresh_token 续。
    飞书 refresh_token 30 天滑窗——每次刷新返回新的，所以每月用一次就永远不重新 OAuth。"""
    state = _load_state()
    user_token = state.get("user_token")
    expires_at = state.get("expires_at", 0)

    if user_token and expires_at > time.time():
        return user_token.strip()

    # 过期了用 refresh_token 续——这里和老版的关键差异：
    # 老版打到 /authen/v1/oidc/access_token（错），新版打 /authen/v1/oidc/refresh_access_token
    rt = state.get("refresh_token")
    if rt:
        app_token = get_app_token()
        resp = requests.post(
            f"{FEISHU_API}/authen/v1/oidc/refresh_access_token",
            headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
            json={"grant_type": "refresh_token", "refresh_token": rt},
        )
        if resp.status_code == 200 and resp.json().get("code") == 0:
            d = resp.json()["data"]
            # 重要：每次 refresh 返回新的 refresh_token，必须存下来；老的会失效
            _save_tokens(d["access_token"], d["refresh_token"], d.get("expires_in", 7200))
            print("[token] user_token 已自动刷新", file=sys.stderr)
            return d["access_token"].strip()
        else:
            print(f"[token] refresh 失败: {resp.json()}", file=sys.stderr)

    print("需要重新授权。跑：", file=sys.stderr)
    print("  python3 scripts/auth.py authorize", file=sys.stderr)
    print("（首次还要先 `auth.py register <app_id> <app_secret>`，详见 SKILL.md）",
          file=sys.stderr)
    sys.exit(1)


# ==================== 读取功能 ====================

def cmd_auth(code):
    """[已废弃] 用授权码换取 token——保留兼容性，建议改用 auth.py authorize 一条龙。"""
    app_token = get_app_token()
    resp = requests.post(f"{FEISHU_API}/authen/v1/oidc/access_token",
                         headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
                         json={"grant_type": "authorization_code", "code": code})
    if resp.json().get("code") != 0:
        print(f"授权失败: {resp.json()}")
        sys.exit(1)
    d = resp.json()["data"]
    _save_tokens(d["access_token"], d["refresh_token"], d.get("expires_in", 7200))
    print(f"授权成功! scope: {d.get('scope')}")
    print("（推荐改用 auth.py authorize 一条龙完成授权，下次免手抄 code）")


def cmd_read_doc(doc_token):
    """读取飞书文档内容"""
    token = get_user_token()

    url = f"{FEISHU_API}/docx/v1/documents/{doc_token}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code == 200 and resp.json().get("code") == 0:
        doc = resp.json()["data"]["document"]
        print(f"标题: {doc.get('title', '')}")
        print(f"修改时间: {doc.get('revision_id', '')}")

    url = f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params={"page_size": 500})

    if resp.status_code == 200 and resp.json().get("code") == 0:
        blocks = resp.json()["data"].get("items", [])
        print(f"\n--- 文档内容 ({len(blocks)} blocks) ---\n")
        for block in blocks:
            text = extract_block_text(block)
            if text.strip():
                print(text)
    else:
        print(f"读取失败(code={resp.json().get('code')}): {resp.json().get('msg')}")


def extract_block_text(block):
    """从文档块中提取纯文本"""
    block_type = block.get("block_type")
    text = ""

    for key in ["text", "heading1", "heading2", "heading3", "heading4",
                 "heading5", "heading6", "heading7", "heading8", "heading9"]:
        content = block.get(key, {})
        if content and "elements" in content:
            for elem in content["elements"]:
                tc = elem.get("text_run", {}).get("content", "")
                if tc:
                    text += tc

    for key in ["bullet", "ordered", "todo"]:
        content = block.get(key, {})
        if content and "elements" in content:
            prefix = "• " if key == "bullet" else "  "
            for elem in content["elements"]:
                tc = elem.get("text_run", {}).get("content", "")
                if tc:
                    text += prefix + tc

    return text


def cmd_search_docs(keyword):
    """搜索飞书文档"""
    token = get_user_token()
    resp = requests.post(f"{FEISHU_API}/suite/docs-api/search/object",
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                         json={"search_key": keyword, "count": 20, "offset": 0})
    if resp.json().get("code") == 0:
        docs = resp.json()["data"].get("docs_entities", [])
        if not docs:
            print("未找到文档")
            return
        for d in docs:
            print(f"  {d['docs_type']:10} | {d['docs_token']} | {d['title']}")
    else:
        print(f"搜索失败: {resp.json().get('msg')}")


def cmd_chats():
    """列出聊天列表"""
    token = get_user_token()
    resp = requests.get(f"{FEISHU_API}/im/v1/chats", params={"page_size": 50},
                        headers={"Authorization": f"Bearer {token}"})
    if resp.json().get("code") == 0:
        for c in resp.json()["data"].get("items", []):
            name = c.get("name", "") or "(无名)"
            print(f"  {c['chat_id']} | {name} | {c.get('chat_type', '')}")
    else:
        print(f"失败: {resp.json().get('msg')}")


def cmd_chat_links(chat_name=None):
    """通过Chrome CDP提取飞书聊天中的文档链接"""
    try:
        from playwright.async_api import async_playwright
        import asyncio
    except ImportError:
        print("需要 playwright: pip install playwright")
        sys.exit(1)

    async def extract():
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]

            feishu_page = None
            for pg in context.pages:
                if 'feishu' in pg.url and 'messenger' in pg.url and 'degraded' not in pg.url:
                    feishu_page = pg
                    break

            if not feishu_page:
                feishu_page = await context.new_page()
                await feishu_page.goto("https://www.feishu.cn/messenger/", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)

            if chat_name:
                el = await feishu_page.query_selector(f'xpath=//span[contains(text(),"{chat_name}")]')
                if el:
                    await el.click()
                    await asyncio.sleep(3)

            links = await feishu_page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('a[href*="feishu.cn/docx"], a[href*="feishu.cn/docs"], a[href*="feishu.cn/wiki"], a[href*="feishu.cn/minutes"]').forEach(el => {
                    results.push({title: (el.textContent||'').trim().substring(0,100), url: el.href});
                });
                return results;
            }""")
            return links

    links = asyncio.run(extract())
    for l in links:
        print(json.dumps(l, ensure_ascii=False))


# ==================== 创建文档功能 ====================

def md_to_feishu_blocks(md_text):
    """将Markdown文本转换为飞书文档块列表"""
    blocks = []
    lines = md_text.split('\n')
    i = 0
    in_code_block = False
    code_lines = []
    in_table = False
    table_rows = []

    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.strip().startswith('```'):
            if in_code_block:
                # 结束代码块
                code_text = '\n'.join(code_lines)
                blocks.append(_make_code_block(code_text))
                code_lines = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 表格
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                table_rows = []
            # 跳过分隔行
            stripped = line.strip().strip('|')
            if all(c in '-| ' for c in stripped):
                i += 1
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            table_rows.append(cells)
            # 检查下一行是否还是表格
            if i + 1 >= len(lines) or not lines[i+1].strip().startswith('|'):
                # 表格结束，转为文本（飞书API创建表格较复杂，先用格式化文本）
                blocks.extend(_table_to_blocks(table_rows))
                in_table = False
                table_rows = []
            i += 1
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 分隔线
        if line.strip() in ('---', '***', '___'):
            blocks.append({"block_type": 22})  # divider
            i += 1
            continue

        # 标题
        heading_match = re.match(r'^(#{1,9})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            # block_type: 3=heading1, 4=heading2, ..., 11=heading9
            block_type = 2 + level
            blocks.append(_make_text_block(text, block_type))
            i += 1
            continue

        # 无序列表
        bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if bullet_match:
            text = bullet_match.group(2)
            blocks.append(_make_text_block(text, 12))  # 12 = bullet
            i += 1
            continue

        # 有序列表
        ordered_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        if ordered_match:
            text = ordered_match.group(2)
            blocks.append(_make_text_block(text, 13))  # 13 = ordered
            i += 1
            continue

        # 引用
        quote_match = re.match(r'^>\s*(.*)$', line)
        if quote_match:
            text = quote_match.group(1)
            blocks.append(_make_text_block(text, 14))  # 14 = quote
            i += 1
            continue

        # 普通段落
        blocks.append(_make_text_block(line, 2))  # 2 = text
        i += 1

    return blocks


def _make_text_block(text, block_type):
    """创建文本块"""
    # 解析内联格式
    elements = _parse_inline(text)

    # 根据block_type确定key
    type_key_map = {
        2: "text",
        3: "heading1", 4: "heading2", 5: "heading3",
        6: "heading4", 7: "heading5", 8: "heading6",
        9: "heading7", 10: "heading8", 11: "heading9",
        12: "bullet", 13: "ordered", 14: "quote",
    }
    key = type_key_map.get(block_type, "text")

    return {
        "block_type": block_type,
        key: {
            "elements": elements
        }
    }


def _parse_inline(text):
    """解析内联Markdown格式（加粗、斜体、行内代码、链接）"""
    elements = []
    # 简化处理：去掉Markdown格式标记，保留纯文本
    # 飞书API的text_run支持style，但创建时较复杂，先用纯文本

    # 去掉加粗/斜体标记但保留文本
    clean = text
    clean = re.sub(r'\*\*(.+?)\*\*', r'\1', clean)
    clean = re.sub(r'\*(.+?)\*', r'\1', clean)
    clean = re.sub(r'`(.+?)`', r'\1', clean)
    clean = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', clean)

    if clean.strip():
        elements.append({
            "text_run": {
                "content": clean
            }
        })
    return elements


def _make_code_block(code_text):
    """创建代码块"""
    return {
        "block_type": 15,  # code
        "code": {
            "elements": [{
                "text_run": {
                    "content": code_text
                }
            }]
        }
    }


def _table_to_blocks(rows):
    """将表格转为格式化的文本块（飞书创建表格API较复杂）"""
    blocks = []
    if not rows:
        return blocks

    # 表头用加粗
    if rows:
        header = " | ".join(rows[0])
        blocks.append(_make_text_block(header, 2))

    # 数据行
    for row in rows[1:]:
        row_text = " | ".join(row)
        blocks.append(_make_text_block(row_text, 2))

    return blocks


def cmd_create_doc(title, md_file=None, folder_token=None):
    """创建飞书文档"""
    token = get_user_token()

    # 1. 创建空文档
    create_url = f"{FEISHU_API}/docx/v1/documents"
    body = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token

    resp = requests.post(create_url,
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                         json=body)

    if resp.json().get("code") != 0:
        print(f"创建文档失败: {resp.json()}")
        # 如果是权限问题，提示
        if resp.json().get("code") == 99991672:
            print("\n权限不足。请到飞书开放平台添加以下权限：")
            print("  - docx:document (读写文档)")
            print("  - drive:drive (访问云空间)")
            print("然后重新授权。")
        sys.exit(1)

    doc = resp.json()["data"]["document"]
    doc_id = doc["document_id"]
    print(f"文档已创建: {doc_id}")
    print(f"URL: https://feishu.cn/docx/{doc_id}")

    # 2. 如果有md文件，读取并添加内容
    if md_file:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_text = f.read()

        # 跳过第一行标题（已用于文档title）
        lines = md_text.split('\n')
        if lines and lines[0].startswith('# '):
            md_text = '\n'.join(lines[1:])

        blocks = md_to_feishu_blocks(md_text)
        print(f"解析到 {len(blocks)} 个内容块")

        # 3. 获取文档的根block_id
        doc_resp = requests.get(f"{FEISHU_API}/docx/v1/documents/{doc_id}",
                                headers={"Authorization": f"Bearer {token}"})
        if doc_resp.json().get("code") != 0:
            print(f"获取文档信息失败: {doc_resp.json()}")
            return

        # 根block就是document_id
        root_block_id = doc_id

        # 4. 批量添加块（每次最多50个）
        batch_size = 50
        total_added = 0
        for batch_start in range(0, len(blocks), batch_size):
            batch = blocks[batch_start:batch_start + batch_size]
            add_url = f"{FEISHU_API}/docx/v1/documents/{doc_id}/blocks/{root_block_id}/children"

            add_resp = requests.post(add_url,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                     json={"children": batch, "index": -1})

            if add_resp.json().get("code") == 0:
                added = len(add_resp.json().get("data", {}).get("children", []))
                total_added += added
            else:
                print(f"添加第{batch_start+1}-{batch_start+len(batch)}块失败: {add_resp.json().get('msg')}")
                # 尝试逐个添加以跳过有问题的块
                for j, block in enumerate(batch):
                    single_resp = requests.post(add_url,
                                                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                                json={"children": [block], "index": -1})
                    if single_resp.json().get("code") == 0:
                        total_added += 1
                    else:
                        print(f"  跳过第{batch_start+j+1}块: {single_resp.json().get('msg')}")

        print(f"成功添加 {total_added}/{len(blocks)} 个内容块")

    print(f"\n文档地址: https://feishu.cn/docx/{doc_id}")
    return doc_id


# ==================== 消息发送 ====================

def cmd_send_msg(chat_id, msg_type, content):
    """发送消息到聊天"""
    token = get_user_token()

    if msg_type == "text":
        msg_content = json.dumps({"text": content})
    elif msg_type == "post":
        # content应该是一个JSON字符串
        msg_content = content
    else:
        msg_content = content

    resp = requests.post(f"{FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                         json={
                             "receive_id": chat_id,
                             "msg_type": msg_type,
                             "content": msg_content
                         })
    result = resp.json()
    if result.get("code") == 0:
        msg_id = result["data"]["message_id"]
        print(f"消息发送成功: {msg_id}")
    else:
        print(f"发送失败: {result.get('msg')} (code={result.get('code')})")


# ==================== 文件上传 ====================

def cmd_upload_file(file_path, file_type="doc"):
    """上传文件到飞书（获取file_key用于消息发送）"""
    token = get_user_token()

    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)

    # 上传为消息附件
    resp = requests.post(f"{FEISHU_API}/im/v1/files",
                         headers={"Authorization": f"Bearer {token}"},
                         data={"file_type": file_type, "file_name": filename},
                         files={"file": open(file_path, "rb")})
    result = resp.json()
    if result.get("code") == 0:
        file_key = result["data"]["file_key"]
        print(f"上传成功: {file_key}")
        print(f"可以用 send 命令发送到聊天")
        return file_key
    else:
        print(f"上传失败: {result.get('msg')} (code={result.get('code')})")


# ==================== 云空间 ====================

def cmd_list_folders(folder_token=None):
    """列出云空间文件夹"""
    token = get_user_token()

    if folder_token:
        url = f"{FEISHU_API}/drive/v1/files"
        params = {"folder_token": folder_token, "page_size": 50}
    else:
        # 根目录
        url = f"{FEISHU_API}/drive/explorer/v2/root_folder/meta"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.json().get("code") == 0:
            root_token = resp.json()["data"]["token"]
            print(f"根目录token: {root_token}")
            url = f"{FEISHU_API}/drive/v1/files"
            params = {"folder_token": root_token, "page_size": 50}
        else:
            print(f"获取根目录失败: {resp.json().get('msg')}")
            return

    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
    if resp.json().get("code") == 0:
        files = resp.json()["data"].get("files", [])
        for f in files:
            print(f"  {f.get('type', '?'):8} | {f.get('token', ''):20} | {f.get('name', '')}")
    else:
        print(f"列出失败: {resp.json().get('msg')}")


# ==================== 录音豆转写 ====================

def _get_doc_blocks(token, doc_token):
    """获取文档的所有block文本"""
    url = f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params={"page_size": 500})
    if resp.status_code == 200 and resp.json().get("code") == 0:
        blocks = resp.json()["data"].get("items", [])
        lines = []
        for block in blocks:
            text = extract_block_text(block)
            if text.strip():
                lines.append(text)
        return lines
    return []


# 录音豆产物标题的严格模式：
# - 新版妙记（AI 智能命名）: "文字记录：<主题> 2026年4月24日" / "智能纪要：<主题> 2026年4月24日"
# - 老版未智能命名: "soundcore Work_04-20 16:46"
# 严格模式保证只命中"安克录音豆"产物，排除他人写的会议纪要文档。
_RECORDING_TITLE_PATTERNS = [
    re.compile(r'^文字记录：.+\d{4}年\d{1,2}月\d{1,2}日$'),
    re.compile(r'^智能纪要：.+\d{4}年\d{1,2}月\d{1,2}日$'),
    re.compile(r'^soundcore\s+Work_\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}$', re.IGNORECASE),
]


def _is_recording_title(title: str) -> bool:
    """严格判断是否为录音豆自动产出的文档。排除人工写的会议纪要。"""
    return any(p.match(title or "") for p in _RECORDING_TITLE_PATTERNS)


def _search_docs(token, keyword, page_size=50, max_pages=20):
    """分页搜到底（飞书单次最多 50）。"""
    results = []
    for page in range(max_pages):
        resp = requests.post(
            f"{FEISHU_API}/suite/docs-api/search/object",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"search_key": keyword, "count": page_size, "offset": page * page_size},
        )
        if resp.json().get("code") != 0:
            break
        docs = resp.json()["data"].get("docs_entities", [])
        if not docs:
            break
        results.extend(docs)
        if len(docs) < page_size:
            break
    return results


def cmd_recordings_list(limit=10, show_all=False):
    """
    列出安克录音豆产物（文字记录 + 智能纪要）。

    严格只匹配录音豆自动产出的文档标题模式，不会混入他人写的"会议纪要"文档。
    搜三个关键词覆盖全部场景：
      - "文字记录"  -> 新版 AI 智能命名的逐字稿
      - "智能纪要"  -> 新版 AI 智能命名的摘要
      - "soundcore Work" -> 老版未被 AI 命名的（内容太少或太碎）
    """
    token = get_user_token()

    # 三轮搜索，合并去重
    all_docs = {}
    for key in ["文字记录", "智能纪要", "soundcore Work"]:
        for d in _search_docs(token, key):
            title = d.get("title", "")
            if _is_recording_title(title):
                all_docs[d["docs_token"]] = {
                    "token": d["docs_token"],
                    "type": d["docs_type"],
                    "title": title,
                    "url": d.get("url", f"https://feishu.cn/docx/{d['docs_token']}"),
                }

    # 按标题里的日期倒序排列（新的在前）
    def sort_key(r):
        m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', r["title"])
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        # soundcore Work_MM-DD HH:MM
        m = re.search(r'soundcore\s+Work_(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})', r["title"], re.IGNORECASE)
        if m:
            return (2026, int(m.group(1)), int(m.group(2)))
        return (0, 0, 0)

    recordings = sorted(all_docs.values(), key=sort_key, reverse=True)

    # limit=0 或 show_all=True 时返回全部
    display = recordings if (show_all or limit == 0) else recordings[:limit]

    for i, r in enumerate(display, 1):
        print(f"  {i}. [{r['type']}] {r['title']}")
        print(f"     token: {r['token']}")
        print(f"     url: {r['url']}")

    return display


def cmd_recordings_get(doc_token):
    """获取某条录音的转写全文"""
    token = get_user_token()

    # 获取文档标题
    url = f"{FEISHU_API}/docx/v1/documents/{doc_token}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 200 and resp.json().get("code") == 0:
        doc = resp.json()["data"]["document"]
        print(f"标题: {doc.get('title', '')}\n")

    # 获取内容
    lines = _get_doc_blocks(token, doc_token)
    for line in lines:
        print(line)

    return lines


def cmd_recordings_latest():
    """拉取最新一条录音的转写"""
    recordings = cmd_recordings_list(limit=5)
    # 优先找"文字记录"类型的
    text_docs = [r for r in recordings if "文字记录" in r["title"]]
    if text_docs:
        print(f"\n--- 最新转写 ---\n")
        cmd_recordings_get(text_docs[0]["token"])
    elif recordings:
        print(f"\n--- 最新记录 ---\n")
        cmd_recordings_get(recordings[0]["token"])
    else:
        print("未找到录音记录")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description="飞书API工具（完整版）")
    sub = parser.add_subparsers(dest="command")

    # 认证
    sub.add_parser("auth").add_argument("code", help="OAuth授权码")

    # 文档读取
    sub.add_parser("doc").add_argument("token", help="文档token（从URL中提取）")

    # 文档创建
    p_create = sub.add_parser("create-doc", help="创建飞书文档")
    p_create.add_argument("title", help="文档标题")
    p_create.add_argument("--file", help="Markdown文件路径", default=None)
    p_create.add_argument("--folder", help="目标文件夹token", default=None)

    # 搜索
    sub.add_parser("search").add_argument("keyword", help="搜索关键词")

    # 聊天
    sub.add_parser("chats")

    # 聊天链接
    p_links = sub.add_parser("links", help="从Chrome提取飞书聊天中的文档链接")
    p_links.add_argument("--chat", help="聊天名称", default=None)

    # 发消息
    p_send = sub.add_parser("send", help="发送消息到聊天")
    p_send.add_argument("chat_id", help="聊天ID")
    p_send.add_argument("--type", help="消息类型", default="text", choices=["text", "post", "interactive", "file"])
    p_send.add_argument("content", help="消息内容")

    # 上传文件
    p_upload = sub.add_parser("upload", help="上传文件")
    p_upload.add_argument("file_path", help="文件路径")
    p_upload.add_argument("--type", help="文件类型", default="doc", choices=["opus", "mp4", "pdf", "doc", "xls", "ppt", "stream"])

    # 云空间
    p_folders = sub.add_parser("folders", help="列出云空间文件")
    p_folders.add_argument("--token", help="文件夹token（默认根目录）", default=None)

    # 录音豆
    p_rec = sub.add_parser("recordings", help="录音豆转写记录")
    rec_sub = p_rec.add_subparsers(dest="rec_action")
    rec_sub.add_parser("list", help="列出最近录音").add_argument("--limit", type=int, default=10)
    rec_sub.add_parser("get", help="获取转写全文").add_argument("token", help="文档token")
    rec_sub.add_parser("latest", help="拉取最新一条转写")

    args = parser.parse_args()

    if args.command == "auth":
        cmd_auth(args.code)
    elif args.command == "doc":
        cmd_read_doc(args.token)
    elif args.command == "create-doc":
        cmd_create_doc(args.title, md_file=args.file, folder_token=args.folder)
    elif args.command == "search":
        cmd_search_docs(args.keyword)
    elif args.command == "chats":
        cmd_chats()
    elif args.command == "links":
        cmd_chat_links(args.chat)
    elif args.command == "send":
        cmd_send_msg(args.chat_id, args.type, args.content)
    elif args.command == "upload":
        cmd_upload_file(args.file_path, args.type)
    elif args.command == "folders":
        cmd_list_folders(args.token)
    elif args.command == "recordings":
        if args.rec_action == "list":
            cmd_recordings_list(limit=args.limit)
        elif args.rec_action == "get":
            cmd_recordings_get(args.token)
        elif args.rec_action == "latest":
            cmd_recordings_latest()
        else:
            p_rec.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

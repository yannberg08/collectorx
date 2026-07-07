#!/usr/bin/env python3
"""
邮箱采集器 - 支持IMAP协议的邮箱邮件采集
"""
import imaplib
import email
import json
import os
import sys
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

STATE_DIR = Path.home() / ".collectorx"
TOKEN_FILE = STATE_DIR / "email.json"


def _load_state() -> dict:
    if not TOKEN_FILE.exists():
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


def decode_mime_header(header):
    """解码MIME头部"""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_email_body(msg):
    """提取邮件正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body


def cmd_register(host: str, email_addr: str, password: str):
    """注册邮箱账户"""
    state = _load_state()
    state["account"] = {
        "host": host,
        "email": email_addr,
        "password": password
    }
    _save_state(state)
    print(f"邮箱账户已注册: {email_addr}")


def cmd_collect(days: int = 30, folder: str = "INBOX", fmt: str = "json", limit: int = None):
    """采集邮件"""
    state = _load_state()
    account = state.get("account")
    if not account:
        print("ERROR: 未找到邮箱账户，请先运行 register")
        sys.exit(1)
    
    try:
        # 连接IMAP服务器
        mail = imaplib.IMAP4_SSL(account["host"])
        mail.login(account["email"], account["password"])
        mail.select(folder)
        
        # 计算日期范围
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date}")')
        
        if status != "OK":
            print(f"搜索失败: {status}")
            return
        
        msg_ids = messages[0].split()
        if limit:
            msg_ids = msg_ids[-limit:]
        
        emails = []
        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            
            msg = email.message_from_bytes(msg_data[0][1])
            
            email_obj = {
                "id": msg_id.decode(),
                "from": decode_mime_header(msg["From"]),
                "to": decode_mime_header(msg["To"]),
                "subject": decode_mime_header(msg["Subject"]),
                "date": msg["Date"],
                "body": get_email_body(msg)[:5000]  # 限制正文长度
            }
            emails.append(email_obj)
        
        mail.logout()
        
        # 输出
        if fmt == "json":
            print(json.dumps(emails, ensure_ascii=False, indent=2))
        else:
            for e in emails:
                print(f"[{e['date']}] From: {e['from']}")
                print(f"Subject: {e['subject']}")
                print(f"Body: {e['body'][:200]}...")
                print("---")
        
        print(f"采集完成: {len(emails)} 封邮件")
        
    except Exception as e:
        print(f"采集失败: {e}")
        sys.exit(1)


def cmd_status():
    """显示状态"""
    state = _load_state()
    account = state.get("account")
    if account:
        print(f"邮箱账户: {account['email']}")
        print(f"IMAP服务器: {account['host']}")
    else:
        print("未注册邮箱账户")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="邮箱采集器")
    subparsers = parser.add_subparsers(dest="command")
    
    # register命令
    reg_parser = subparsers.add_parser("register", help="注册邮箱账户")
    reg_parser.add_argument("--host", required=True, help="IMAP服务器")
    reg_parser.add_argument("--email", required=True, help="邮箱地址")
    reg_parser.add_argument("--password", required=True, help="密码")
    
    # collect命令
    col_parser = subparsers.add_parser("collect", help="采集邮件")
    col_parser.add_argument("--days", type=int, default=30, help="采集最近N天")
    col_parser.add_argument("--folder", default="INBOX", help="邮箱文件夹")
    col_parser.add_argument("--format", choices=["json", "txt"], default="json")
    col_parser.add_argument("--limit", type=int, help="限制数量")
    
    # status命令
    subparsers.add_parser("status", help="显示状态")
    
    args = parser.parse_args()
    
    if args.command == "register":
        cmd_register(args.host, args.email, args.password)
    elif args.command == "collect":
        cmd_collect(args.days, args.folder, args.format, args.limit)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

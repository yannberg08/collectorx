"""
email.parser — 邮件解析
"""
import email
from email.header import decode_header
from typing import Dict, Any


def parse_email_message(msg) -> Dict[str, Any]:
    """解析邮件消息"""
    return {
        "id": msg.get("Message-ID", ""),
        "from": decode_mime_header(msg["From"]),
        "to": decode_mime_header(msg["To"]),
        "subject": decode_mime_header(msg["Subject"]),
        "date": msg["Date"],
        "body": get_email_body(msg)
    }


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
            if part.get_content_type() == "text/plain":
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

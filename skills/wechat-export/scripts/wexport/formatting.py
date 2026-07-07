"""wexport.formatting — 消息格式化 / 导出清洗 / 采集过滤。

从单体 wechat_query.py 原样抽出，函数体逐字未改。
"""
import re
import json as _json
from datetime import datetime


def format_message(msg: dict) -> str:
    time_str = datetime.fromtimestamp(msg['time']).strftime('%Y-%m-%d %H:%M:%S')
    direction = "recv" if msg['is_received'] else "sent"
    is_call = msg.get('kind') == 'call'
    header_tag = 'call' if is_call else direction
    content = str(msg.get('message', '')).replace('\n', ' ')

    lines = [f"[{time_str}] ({header_tag})"]
    if msg.get('is_group'):
        group_name = msg.get('chat_name') or '(group)'
        sender = msg.get('sender') or ''
        lines.append(f"  group: {group_name}")
        if sender:
            lines.append(f"  sender: {sender}")
    else:
        contact_name = msg.get('chat_name') or '(dm)'
        lines.append(f"  dm: {contact_name}")

    if is_call:
        lines.append(f"  type: {msg.get('call_type', '通话')}")
        lines.append(f"  duration: {msg.get('call_duration_str', '')}")
        lines.append(f"  status: {msg.get('call_status_cn', '')}")
        initiator = msg.get('call_initiator') or direction
        who = '我发起' if initiator == 'sent' else '对方发起'
        lines.append(f"  initiator: {initiator}   # {who}")
    else:
        lines.append(f"  content: {content}")
    return '\n'.join(lines)


def _xml_text(pattern: str, content: str) -> str:
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        return ''
    return re.sub(r'\s+', ' ', match.group(1)).strip()


def _clean_export_content(content, max_chars: int = 500) -> str:
    text = str(content or '').strip()
    if not text:
        return ''

    lower = text.lower()
    if lower.startswith('<') or '<msg' in lower or '<appmsg' in lower:
        title = _xml_text(r'<title><!\[CDATA\[(.*?)\]\]></title>', text) or _xml_text(r'<title>(.*?)</title>', text)
        desc = _xml_text(r'<des><!\[CDATA\[(.*?)\]\]></des>', text) or _xml_text(r'<des>(.*?)</des>', text)
        fileext = (_xml_text(r'<fileext><!\[CDATA\[(.*?)\]\]></fileext>', text) or _xml_text(r'<fileext>(.*?)</fileext>', text)).lower()
        if '<voipinvitemsg' in lower or '<voipmsg' in lower:
            text = '[通话]'
        elif '<emoji' in lower or 'cdnurl=' in lower:
            text = '[表情/图片]'
        elif '<videomsg' in lower or 'cdnvideourl' in lower:
            text = '[视频]'
        elif fileext in ('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar'):
            text = f"[文件] {title or fileext}"
        elif title:
            text = f"[链接] {title}"
            if desc:
                text += f" - {desc}"
        else:
            # Compact export is for humans/agents to scan. Unknown XML cards
            # carry no readable signal after scrubbing, so omit them instead of
            # emitting thousands of "[卡片消息]" placeholder lines.
            text = ''

    text = re.sub(r'\s+', ' ', text.replace('\r', ' ').replace('\n', ' ')).strip()
    if max_chars and max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + '...'
    return text


def format_export_message(msg: dict, max_chars: int = 500) -> str:
    time_str = datetime.fromtimestamp(msg['time']).strftime('%Y-%m-%d %H:%M:%S')
    direction = "recv" if msg['is_received'] else "sent"
    if msg.get('kind') == 'call':
        direction = 'call'

    chat_name = msg.get('chat_name') or ('(group)' if msg.get('is_group') else '(dm)')
    sender = msg.get('sender') or ('我' if not msg.get('is_received') else chat_name)
    if msg.get('is_group'):
        who = f"{chat_name}·{sender}"
    else:
        who = chat_name

    if msg.get('kind') == 'call':
        content = msg.get('message') or msg.get('call_type') or '通话'
    else:
        content = _clean_export_content(msg.get('message'), max_chars=max_chars)
        if not content:
            return ''
    return f"[{time_str}] ({direction}) {who}: {content}"


def _split_csv(s):
    if not s:
        return set()
    return {x.strip() for x in s.split(',') if x.strip()}


def _is_noise_for_owner_relevance(msg: dict) -> bool:
    if msg.get('kind') == 'call':
        return True
    content = str(msg.get('message') or '').strip()
    if not content:
        return True
    if content.startswith('<'):
        return True
    if '撤回了一条消息' in content:
        return True
    return False


def _detect_active_groups(messages, all_groups):
    """Return group names where the owner sent at least one substantive message."""
    active_groups = set()
    for msg in messages:
        chat = msg.get('chat_name')
        if chat not in all_groups:
            continue
        if msg.get('is_received'):
            continue
        if _is_noise_for_owner_relevance(msg):
            continue
        active_groups.add(chat)
    return active_groups


def _detect_active_private(messages, all_groups):
    """Return private-chat names where the owner sent at least one substantive message."""
    active = set()
    for msg in messages:
        chat = msg.get('chat_name')
        if not chat or chat in all_groups:
            continue
        if msg.get('is_received'):
            continue
        if _is_noise_for_owner_relevance(msg):
            continue
        active.add(chat)
    return active


def _filter_owner_relevant_messages(messages, all_groups, exclude_set=None, group_whitelist=None, private_whitelist=None):
    """Keep private chats plus explicitly/actively relevant groups.
    private_whitelist is not None -> private chats must be in it too (--participated-only:
    没回过的私聊不要,省 token)."""
    exclude_set = exclude_set or set()
    group_whitelist = group_whitelist or set()
    kept = []
    for msg in messages:
        chat = msg.get('chat_name') or ''
        if chat in exclude_set:
            continue
        if chat in all_groups:
            if chat not in group_whitelist:
                continue
        else:
            if private_whitelist is not None and chat not in private_whitelist:
                continue
        kept.append(msg)
    return kept


def _dump_collect_payload(records, pretty: bool = False) -> str:
    if pretty:
        return _json.dumps(records, ensure_ascii=False, indent=2)
    return _json.dumps(records, ensure_ascii=False, separators=(',', ':'))


def _format_collect_source(chat: str, is_group: bool, time_str: str) -> str:
    date = (time_str or '')[:10]
    chat = chat or '(unknown)'
    if is_group:
        return f"微信群「{chat}」· {date} 的聊天" if date else f"微信群「{chat}」的聊天"
    return f"跟{chat}在 {date} 的微信聊天" if date else f"跟{chat}的微信聊天"


__all__ = [
    'format_message', '_xml_text', '_clean_export_content', 'format_export_message',
    '_split_csv', '_is_noise_for_owner_relevance', '_detect_active_groups',
    '_detect_active_private', '_filter_owner_relevant_messages',
    '_dump_collect_payload', '_format_collect_source',
]

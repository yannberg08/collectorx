"""wexport.codec — 底层解码与常量（zstd 解压 / VoIP 解析 / 标签 / protobuf varint）。

从单体 wechat_query.py 原样抽出，函数体逐字未改。
"""
import re


class LabelNotSupportedError(RuntimeError):
    """Raised when label query is requested on a platform without local label storage."""
    pass


_LABEL_NOT_SUPPORTED_MAC = (
    "Mac WeChat 3.x 不在本地数据库存储联系人标签（标签由服务端托管，仅 Windows 4.x 下发）。\n"
    "        可用 `--contact \"<姓名>\"` 按姓名直查；标签查询请在 Windows 上运行此 skill。\n"
    "        如有新需求，请反馈给 skill 官方（@Kevin）补充，不要自己写 SQL。"
)


def _decompress_content(data):
    """Decompress zstd compressed message content (Windows 4.x)"""
    if isinstance(data, bytes) and len(data) > 4:
        # zstd magic: 28 b5 2f fd
        if data[:4] == b'\x28\xb5\x2f\xfd':
            try:
                import zstandard
                dctx = zstandard.ZstdDecompressor()
                return dctx.decompress(data).decode('utf-8', errors='replace')
            except Exception:
                pass
    if isinstance(data, str):
        return data
    return ''


# ── VoIP (通话) 解析 ───────────────────────────────────────────
# Mac/Windows 微信的通话记录存在 messageType=50 的行里，msgContent 是 XML：
#
#   <voipinvitemsg>
#     <status>4</status>
#     <invitetype>1</invitetype>   <!-- 1=语音 0=视频 -->
#   </voipinvitemsg>
#   <voiplocalinfo>
#     <wordingtype>4</wordingtype>  <!-- 结束原因，详见 _VOIP_WORDING -->
#     <duration>217</duration>      <!-- 秒，0=未接通 -->
#   </voiplocalinfo>
#
# wordingtype 观测到的取值（结合 duration 与 is_sent 推断）：
#   1  我方取消（未接通）
#   2  对方未接 / 已取消
#   3  通话结束（双方挂断）
#   4  通话结束（正常，有 duration）
#   5  对方拒绝
#   6  超时未接 / 接通失败
#   7  我方拒绝
#   8  无人接听
#   10 线路繁忙 / 我正忙
#   11 对方已取消
#   12 对方已取消（未接通，另一种分支）
#
# 重要：不要试图把 wordingtype 完全语义化——版本间会变。核心逻辑是
#   duration > 0  → 通话成功（主要信息）
#   duration == 0 → 未接通，用 wordingtype + 方向给出大致原因

_VOIP_WORDING = {
    1: ('canceled', '已取消'),
    2: ('no_answer', '未接听'),
    3: ('ended', '已结束'),
    4: ('answered', '已接通'),
    5: ('rejected', '已拒绝'),
    6: ('timeout', '超时未接'),
    7: ('rejected', '已拒绝'),
    8: ('no_answer', '无人接听'),
    10: ('busy', '线路繁忙'),
    11: ('canceled', '对方已取消'),
    12: ('canceled', '对方已取消'),
}


def _format_duration(seconds: int) -> str:
    """Format seconds as `Xh Ym Zs` / `Xm Ys` / `Xs`."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return '0秒'
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f'{h}小时')
    if m:
        parts.append(f'{m}分')
    if s or not parts:
        parts.append(f'{s}秒')
    return ''.join(parts)


def _parse_voip_content(content: str, is_sent: bool):
    """Parse a <voipinvitemsg>...</voiplocalinfo> XML blob.

    Returns a dict with keys:
        call_type      '语音通话' | '视频通话'
        duration_sec   int (0 if not answered)
        duration_str   human readable (e.g. '3分25秒' / '未接通')
        status_code    machine readable ('answered' | 'no_answer' | 'canceled' | 'rejected' | 'busy' | 'ended' | 'unknown')
        status_cn      Chinese label
        initiator      'sent' (我发起) | 'recv' (对方发起)
        summary        one-line text for display

    Returns None if the content doesn't look like a VoIP invite.
    """
    if not isinstance(content, str) or '<voipinvitemsg' not in content:
        return None

    invitetype_m = re.search(r'<invitetype>(\d+)</invitetype>', content)
    wordingtype_m = re.search(r'<wordingtype>(\d+)</wordingtype>', content)
    duration_m = re.search(r'<duration>(\d+)</duration>', content)

    invitetype = int(invitetype_m.group(1)) if invitetype_m else 1
    wordingtype = int(wordingtype_m.group(1)) if wordingtype_m else 0
    duration = int(duration_m.group(1)) if duration_m else 0

    call_type = '视频通话' if invitetype == 0 else '语音通话'

    if duration > 0:
        status_code = 'answered'
        status_cn = '已接通'
        duration_str = _format_duration(duration)
    else:
        status_code, status_cn = _VOIP_WORDING.get(wordingtype, ('unknown', f'未接通(code={wordingtype})'))
        # 结合方向细化"canceled"语义：sent+canceled = 我方取消，recv+canceled = 对方取消
        if status_code == 'canceled' and is_sent and wordingtype == 1:
            status_cn = '我已取消'
        elif status_code == 'canceled' and not is_sent and wordingtype in (11, 12):
            status_cn = '对方已取消'
        duration_str = status_cn

    initiator = 'sent' if is_sent else 'recv'
    who = '我发起' if is_sent else '对方发起'
    if status_code == 'answered':
        summary = f'[{call_type}] {who}，通话{duration_str}'
    else:
        summary = f'[{call_type}] {who}，{status_cn}'

    return {
        'call_type': call_type,
        'duration_sec': duration,
        'duration_str': duration_str,
        'status_code': status_code,
        'status_cn': status_cn,
        'initiator': initiator,
        'summary': summary,
    }


def _parse_label_id_list(raw):
    """Parse Contact.LabelIDList -> list[int].

    Seen formats:
      ',1,2,5,'      (camelCase schema, comma-wrapped, may have empty fields)
      '1,2,5'        (plain)
      '[1,2,5]'      (JSON array in some 4.x variants)
      b'...'         (already bytes)
    """
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode('utf-8', errors='replace')
        except Exception:
            return []
    s = str(raw).strip()
    if not s:
        return []
    # Trim JSON brackets
    if s.startswith('[') and s.endswith(']'):
        s = s[1:-1]
    # Strip wrapping commas/whitespace
    s = s.strip(',').strip()
    if not s:
        return []
    out = []
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out


def _extract_protobuf_field30(data: bytes) -> str:
    """Extract field 30 (label_list) from contact extra_buffer protobuf.

    The extra_buffer is a protobuf-encoded blob.  Field 30 is a
    length-delimited (wire type 2) string containing comma-separated
    label IDs, e.g. "41,67,68".

    Returns the decoded string, or empty string on failure.
    """
    if not data or len(data) < 2:
        return ""
    pos = 0
    while pos < len(data):
        # decode tag varint
        tag, pos = _decode_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:  # varint
            _, pos = _decode_varint(data, pos)
        elif wire_type == 2:  # length-delimited
            length, pos = _decode_varint(data, pos)
            if pos + length > len(data):
                break
            if field_num == 30:
                try:
                    return data[pos:pos + length].decode('utf-8', errors='replace')
                except Exception:
                    return ""
            pos += length
        elif wire_type == 1:  # 64-bit fixed
            pos += 8
        elif wire_type == 5:  # 32-bit fixed
            pos += 4
        else:
            break
    return ""


def _decode_varint(data: bytes, pos: int):
    """Decode a protobuf varint starting at *pos*. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if not (byte & 0x80):
            break
        shift += 7
    return result, pos


__all__ = [
    'LabelNotSupportedError', '_LABEL_NOT_SUPPORTED_MAC',
    '_decompress_content', '_VOIP_WORDING', '_format_duration',
    '_parse_voip_content', '_parse_label_id_list',
    '_extract_protobuf_field30', '_decode_varint',
]

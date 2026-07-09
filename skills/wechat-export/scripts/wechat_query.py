#!/usr/bin/env python3
"""
WeChat chat record query tool.
Supports Mac 4.x (SQLCipher4) and Windows 4.x (decrypted SQLite).
（微信 3.x / SQLCipher3 自 v0.9.1 起下线，仅保留 4.x 通路。）

架构（两条正交的轴，别按操作系统一刀切）
============================================
一次查询拆成三段，各自的「变化维度」不同：

  1) 拿 key   —— 按【操作系统】变（提取器，独立脚本）
       Mac 4.x  : wechat_extract_mac.py     lldb hook CCKeyDerivationPBKDF → 每库一把 key
       Windows  : wechat_extract_windows.py 扫进程内存 x'<96hex>'          → 每库一把 key
  2) 解密     —— SQLCipher4：page4096 / kdf256000 / HMAC-SHA512
  3) 读库     —— 微信 4.x，Mac4 与 Win4 **完全相同**
       Msg_ + Name2Id + contact + 标签（zstd/protobuf）

查询类层次（generation-based，不是 OS-based）：
       V4QueryBase           4.x 读库引擎（公用：读联系人/消息/标签）
        ├ WindowsV4Query     内存扫描 key + 手动 AES 逐页解密
        └ MacV4Query         lldb hook per-DB key + SQLCipher4 解密到明文缓存

  「公用的部分」= V4QueryBase 的读库方法（只依赖已解密的明文目录 self._work_dir）；
  「不一样的部分」= 各子类的 _prepare/decrypt（怎么拿 key、按哪代加密解密）。
兼容旧名：WindowsWeChatQuery / MacV4WeChatQuery 仍作别名保留。
"""
import os
if os.name == 'nt':
    os.system('chcp 65001 >nul 2>&1')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import argparse
import hashlib
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
import json as _json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wexport.keycrypto import resolve_keys_file  # noqa: E402  统一 all_keys.json 定位（兼容旧平台名）


def _load_version():
    """读 skill 根目录的 VERSION 文件（由 covo-hub 发版时注入 / 仓库内也带一份）。"""
    try:
        import pathlib
        vf = pathlib.Path(__file__).resolve().parent.parent / 'VERSION'
        if vf.exists():
            return vf.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return '0.0.0-dev'

__version__ = _load_version()


# ── 标签（Tag / Label）相关（v0.5.0+） ───────────────────────
#
# 【只支持 4.x】Mac WeChat 4.x 与 Windows WeChat 4.x 同源，本地都有标签：
#   contact.db 里有 contact_label 表（标签字典）+ contact.extra_buffer protobuf field 30
#   存每个联系人的标签 ID 列表（适配 camelCase / snake_case / snake_underscore 三种 schema；
#   extra_buffer 解析作为 fallback，当 contact 表无 LabelIDList 列时启用）。
#   标签方法在共享基类 V4QueryBase 上，Mac4/Win4 都能本地查标签。
#
# ⚠️ 下游 Agent 注意：禁止自行写 SQL 查询标签/分组！用 skill 提供的 CLI 命令：
#     --list-tags / --tag "NAME" / --contact-tags "NAME"
# 如有命令覆盖不到的场景，反馈给 skill 官方（@Kevin），不要 workaround。

class LabelNotSupportedError(RuntimeError):
    """Raised when label query is requested on a platform without local label storage."""
    pass

_LABEL_NOT_SUPPORTED_MAC = (
    "本地未找到标签数据（4.x 正常都有本地标签）。\n"
    "        可用 `--contact \"<姓名>\"` 按姓名直查；若确认微信里设了标签仍查不到，反馈给 skill 官方（@Kevin）。"
)


# ── 日志配置 ────────────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, 'wechat_export.log')

logger = logging.getLogger('wechat_query')

DATA_QUALITY_TARGET = 'collectorx.data_quality.collection_gaps'
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _fh = logging.FileHandler(_log_file, encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(_fh)


def _get_decrypt_cache_dir(db_dir: str) -> str:
    """Return a stable cache directory for decrypted DBs, keyed by source db_dir.

    Multiple wxid accounts get separate cache subdirs via md5(db_dir)[:8].
    Stored under data/decrypted_cache/ (survives skill upgrades).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    key = hashlib.md5(os.path.abspath(db_dir).encode('utf-8')).hexdigest()[:8]
    cache_root = os.path.join(data_dir, 'decrypted_cache', key)
    os.makedirs(cache_root, exist_ok=True)
    return cache_root


def _cleanup_legacy_temp():
    """Remove leaked wechat_q_* temp dirs from prior versions.

    Older code used tempfile.mkdtemp(prefix='wechat_q_') and only cleaned up on
    the happy path in main(), which leaked ~1.5GB per invocation on Windows.
    """
    import tempfile
    import shutil
    tmp_root = tempfile.gettempdir()
    if not os.path.isdir(tmp_root):
        return
    cleaned = 0
    freed = 0
    for name in os.listdir(tmp_root):
        if not name.startswith('wechat_q_'):
            continue
        path = os.path.join(tmp_root, name)
        if not os.path.isdir(path):
            continue
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        freed += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                cleaned += 1
        except Exception as e:
            logger.debug(f"Failed to clean legacy temp {path}: {e}")
    if cleaned:
        logger.info(f"Cleaned {cleaned} legacy wechat_q_* temp dirs, freed ~{freed/1024/1024:.1f} MB")
        print(f"[cleanup] Removed {cleaned} legacy temp dirs (~{freed/1024/1024:.1f} MB)")


def _migrate_legacy_decrypted():
    """Move scripts/decrypted_cache/ → data/decrypted_cache/ (one-time migration).

    Before v0.5.5 the cache lived under scripts/ which gets wiped on skill upgrade.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    old_cache = os.path.join(script_dir, 'decrypted_cache')
    new_cache = os.path.join(data_dir, 'decrypted_cache')
    if not os.path.isdir(old_cache):
        return
    if os.path.isdir(new_cache):
        # new already exists; just remove old
        import shutil
        shutil.rmtree(old_cache, ignore_errors=True)
        logger.info("Removed legacy scripts/decrypted_cache (data/decrypted_cache already exists)")
        return
    os.makedirs(data_dir, exist_ok=True)
    import shutil
    shutil.move(old_cache, new_cache)
    logger.info(f"Migrated decrypted_cache: {old_cache} → {new_cache}")


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


class V4QueryBase:
    """微信 4.x 读库引擎（Mac 4.x 与 Windows 4.x 共享）。

    职责 = 「读库」这一公用层：吃一个已解密的明文目录 self._work_dir，负责
    联系人 / 消息（Msg_ + Name2Id 跨分片）/ 标签的全部读取与 zstd/protobuf 解码。
    这些方法只依赖 self._work_dir，与操作系统无关，Mac4 和 Win4 一字不差。

    「拿 key + 解密」是各子类不同的部分：
      - WindowsV4Query：key 走内存扫描（all_keys.json），本类自带的
        _decrypt_to_temp / _decrypt_with_keys_file 用手动 AES 逐页解密（参考实现）。
      - MacV4Query    ：key 走 lldb hook（all_keys.json），用 SQLCipher4
        解密到明文缓存后，以 key=None 复用本类的全部读库逻辑。

    构造约定：给了 key/keys_file 就地解密；否则把 db_dir 当作已是明文目录直接读
    （Mac4 正是走这条——自己先解密好，再把明文目录传进来）。
    """

    def __init__(self, db_dir: str, key: str = None, keys_file: str = None):
        import sqlite3
        import tempfile
        self.sqlite3 = sqlite3
        self.db_dir = db_dir
        self.contacts = {}
        self.group_names = {}
        self._temp_dir = None
        self.labels = {}             # label_id (int) -> label_name (str)
        self.label_name_to_id = {}   # label_name (lower) -> label_id (int)
        self.contact_labels = {}     # username (str) -> list[int] (label_ids)
        self._labels_schema = None   # 'camel' | 'snake' | None
        self._work_dir = db_dir  # default fallback
        # Windows WeChat 4.x scatters messages across message_0.db .. message_N.db.
        # The SAME Msg_<md5> table can appear in several shards (one chat's
        # history spills across shards over time), and each shard carries its
        # own Name2Id (sender rowids are shard-local). _build_message_index()
        # fills these so query_messages reaches every shard, not just message_0.db.
        self._msg_dbs = []          # all message_*.db shard paths
        self._table_to_db = {}      # 'Msg_<md5>' -> [shard paths that hold it]
        self._db_sender_maps = {}   # shard path -> {Name2Id rowid: display name}
        self._md5_to_username = {}  # md5(username) -> username

        if key:
            self._decrypt_to_temp(key)
        elif keys_file:
            self._decrypt_with_keys_file(keys_file)

        self._load_contacts()
        self._build_message_index()
        self._load_labels()

    def _decrypt_to_temp(self, key_hex: str):
        """Decrypt encrypted databases to a stable cache directory for querying.

        Uses a persistent cache keyed by db_dir path; per-file mtime check
        skips re-decryption when the source DB hasn't changed since last run.
        """
        import hmac as hmac_mod
        import struct

        key_hex = key_hex.replace("0x", "")
        enc_key_bytes = bytes.fromhex(key_hex)

        PAGE_SZ = 4096
        SALT_SZ = 16
        IV_SZ = 16
        HMAC_SZ = 64
        RESERVE_SZ = 80
        SQLITE_HDR = b'SQLite format 3\x00'

        # Collect .db files from the live encrypted directory
        db_files = []
        for root, _, files in os.walk(self.db_dir):
            for f in files:
                if f.endswith('.db') and not f.endswith('-wal') and not f.endswith('-shm'):
                    db_files.append(os.path.join(root, f))

        if not db_files:
            print("Error: No .db files found in db_dir")
            self._work_dir = self.db_dir
            return

        # Use stable cache dir instead of a fresh tempfile.mkdtemp every run —
        # that leaked ~1.5GB per invocation (see wechat_q_* temp dir pileup).
        self._temp_dir = _get_decrypt_cache_dir(self.db_dir)
        self._work_dir = self._temp_dir

        matched = 0
        reused = 0
        for db_path in db_files:
            file_size = os.path.getsize(db_path)
            if file_size == 0 or file_size % PAGE_SZ != 0:
                continue

            rel = os.path.relpath(db_path, self.db_dir)
            out_path = os.path.join(self._temp_dir, rel)

            # Reuse cached decryption if the source DB hasn't changed
            if os.path.exists(out_path):
                try:
                    if os.path.getmtime(out_path) >= os.path.getmtime(db_path):
                        reused += 1
                        matched += 1
                        continue
                except OSError:
                    pass

            with open(db_path, 'rb') as f:
                page1 = f.read(PAGE_SZ)

            salt = page1[:SALT_SZ]
            mac_salt = bytes(b ^ 0x3a for b in salt)
            mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=32)

            # Verify HMAC
            p1_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
            p1_hmac = page1[PAGE_SZ - HMAC_SZ:]
            hm = hmac_mod.new(mac_key, p1_data, hashlib.sha512)
            hm.update(struct.pack('<I', 1))

            if hm.digest() != p1_hmac:
                continue

            total_pages = file_size // PAGE_SZ
            try:
                from Crypto.Cipher import AES
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(db_path, 'rb') as fin, open(out_path, 'wb') as fout:
                    for pgno in range(1, total_pages + 1):
                        page = fin.read(PAGE_SZ)
                        if len(page) < PAGE_SZ:
                            break
                        iv = page[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
                        if pgno == 1:
                            encrypted = page[SALT_SZ: PAGE_SZ - RESERVE_SZ]
                            cipher = AES.new(enc_key_bytes, AES.MODE_CBC, iv)
                            decrypted = cipher.decrypt(encrypted)
                            fout.write(SQLITE_HDR + decrypted + b'\x00' * RESERVE_SZ)
                        else:
                            encrypted = page[:PAGE_SZ - RESERVE_SZ]
                            cipher = AES.new(enc_key_bytes, AES.MODE_CBC, iv)
                            decrypted = cipher.decrypt(encrypted)
                            fout.write(decrypted + b'\x00' * RESERVE_SZ)
                matched += 1
            except Exception:
                pass

        print(f"Decrypted {matched}/{len(db_files)} databases (reused {reused} from cache)")

    def _decrypt_with_keys_file(self, keys_file: str):
        """Decrypt using per-DB keys from all_keys.json (produced by wechat_extract_windows.py).

        Uses a global timestamp (.last_decrypt) to skip files that haven't
        changed since the last successful decryption run.
        """
        import json
        _t0 = time.time()

        if not os.path.exists(keys_file):
            print(f"Error: keys file not found: {keys_file}")
            self._work_dir = self.db_dir
            return

        with open(keys_file, 'r', encoding='utf-8') as f:
            key_map = json.load(f)
        logger.info(f"[decrypt] keys file loaded: {len(key_map)} entries from {keys_file}")

        PAGE_SZ = 4096
        SALT_SZ = 16
        IV_SZ = 16
        RESERVE_SZ = 80
        SQLITE_HDR = b'SQLite format 3\x00'

        self._temp_dir = _get_decrypt_cache_dir(self.db_dir)
        self._work_dir = self._temp_dir
        logger.info(f"[decrypt] cache dir: {self._temp_dir}")

        # 读取上次解密完成的时间戳
        stamp_file = os.path.join(self._temp_dir, '.last_decrypt')
        last_decrypt_time = 0.0
        if os.path.exists(stamp_file):
            try:
                with open(stamp_file, 'r') as f:
                    last_decrypt_time = float(f.read().strip())
                from datetime import datetime
                ts_str = datetime.fromtimestamp(last_decrypt_time).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"[decrypt] last decrypt stamp: {ts_str} ({last_decrypt_time:.0f})")
            except Exception as e:
                logger.warning(f"[decrypt] failed to read stamp file: {e}")
        else:
            logger.info(f"[decrypt] no .last_decrypt stamp found (first run or cache cleared)")

        # 只解密查询需要的目录
        _needed_prefixes = ('contact', 'message', 'session', 'label')
        filtered_out = 0
        matched = 0
        skipped = 0
        decrypted_count = 0
        for rel, info in key_map.items():
            # 按目录过滤：不在 needed 列表里的跳过
            if not any(rel.startswith(p) for p in _needed_prefixes):
                filtered_out += 1
                continue

            db_path = os.path.join(self.db_dir, rel)
            if not os.path.exists(db_path):
                logger.debug(f"[decrypt] skip (file not found): {rel}")
                continue

            enc_key_bytes = bytes.fromhex(info['enc_key'])
            file_size = os.path.getsize(db_path)
            if file_size == 0 or file_size % PAGE_SZ != 0:
                logger.debug(f"[decrypt] skip (bad size {file_size}): {rel}")
                continue

            out_path = os.path.join(self._temp_dir, rel)

            # 如果缓存存在且源文件在上次解密后没被修改 → 跳过
            if os.path.exists(out_path) and last_decrypt_time > 0:
                try:
                    src_mtime = os.path.getmtime(db_path)
                    if src_mtime <= last_decrypt_time:
                        matched += 1
                        skipped += 1
                        logger.debug(f"[decrypt] cached (src_mtime={src_mtime:.0f} <= stamp={last_decrypt_time:.0f}): {rel}")
                        continue
                    else:
                        logger.debug(f"[decrypt] stale (src_mtime={src_mtime:.0f} > stamp={last_decrypt_time:.0f}): {rel} ({file_size/1024/1024:.1f}MB)")
                except OSError:
                    pass

            total_pages = file_size // PAGE_SZ
            _td = time.time()
            logger.info(f"[decrypt] decrypting {rel}: {total_pages} pages, {file_size/1024/1024:.1f}MB ...")

            try:
                from Crypto.Cipher import AES
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(db_path, 'rb') as fin, open(out_path, 'wb') as fout:
                    for pgno in range(1, total_pages + 1):
                        page = fin.read(PAGE_SZ)
                        if len(page) < PAGE_SZ:
                            break
                        iv = page[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
                        if pgno == 1:
                            encrypted = page[SALT_SZ: PAGE_SZ - RESERVE_SZ]
                            cipher = AES.new(enc_key_bytes, AES.MODE_CBC, iv)
                            decrypted = cipher.decrypt(encrypted)
                            fout.write(SQLITE_HDR + decrypted + b'\x00' * RESERVE_SZ)
                        else:
                            encrypted = page[:PAGE_SZ - RESERVE_SZ]
                            cipher = AES.new(enc_key_bytes, AES.MODE_CBC, iv)
                            decrypted = cipher.decrypt(encrypted)
                            fout.write(decrypted + b'\x00' * RESERVE_SZ)
                matched += 1
                decrypted_count += 1
                _elapsed = time.time() - _td
                logger.info(f"[decrypt] done {rel}: {total_pages} pages, {file_size/1024/1024:.1f}MB, took {_elapsed:.3f}s")
            except Exception as _e:
                logger.warning(f"[decrypt] FAILED {rel}: {_e}")

        logger.info(f"[decrypt] filtered {filtered_out} unneeded DBs (media/sns/emoticon etc.)")

        # 解密完成后更新全局时间戳
        now = time.time()
        try:
            with open(stamp_file, 'w') as f:
                f.write(str(now))
            from datetime import datetime
            logger.info(f"[decrypt] stamp updated: {datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            logger.warning(f"[decrypt] failed to write stamp: {e}")

        _total = time.time() - _t0
        logger.info(f"[decrypt] TOTAL: {matched} matched ({skipped} cached + {decrypted_count} re-decrypted), {_total:.3f}s")
        if skipped:
            print(f"Decryption: {skipped} cached, {decrypted_count} re-decrypted, {_total:.1f}s")
        else:
            print(f"Decrypted {matched} databases, {_total:.1f}s")

    def cleanup(self):
        """No-op by default: _temp_dir is now a persistent cache we want to reuse.

        Use clear_cache() to wipe the decrypted cache explicitly.
        """
        return

    def clear_cache(self):
        """Remove the persistent decrypted cache for this db_dir."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _load_contacts(self):
        _t0 = time.time()
        contact_db = os.path.join(self._work_dir, "contact", "contact.db")
        if not os.path.exists(contact_db):
            logger.info(f"[contacts] contact.db not found at {contact_db}")
            return
        try:
            conn = self.sqlite3.connect(contact_db)
            cursor = conn.cursor()
            cursor.execute("SELECT username, remark, nick_name FROM contact")
            rows = cursor.fetchall()
            logger.info(f"[contacts] contact table: {len(rows)} rows")
            for row in rows:
                name = row[1] if row[1] else row[2]
                if name:
                    self.contacts[row[0]] = name
                    if '@chatroom' in row[0]:
                        self.group_names[row[0]] = name
            # 群成员昵称（群里的非好友）
            try:
                cursor.execute("SELECT username, nickname FROM chatroom_member")
                cm_rows = cursor.fetchall()
                cm_added = 0
                for row in cm_rows:
                    if row[1] and row[0] not in self.contacts:
                        self.contacts[row[0]] = row[1]
                        cm_added += 1
                logger.info(f"[contacts] chatroom_member: {len(cm_rows)} rows, {cm_added} new nicknames added")
            except Exception as e:
                logger.debug(f"[contacts] chatroom_member table not found or query failed: {e}")
            conn.close()
            logger.info(f"[contacts] loaded {len(self.contacts)} contacts ({len(self.group_names)} groups), took {time.time()-_t0:.3f}s")
        except Exception as e:
            print(f"Warning: load contacts failed - {e}")
            logger.warning(f"[contacts] load failed: {e}")

    def _build_message_index(self):
        """Index every message_*.db shard.

        Windows WeChat 4.x scatters Msg_ tables across message_0.db .. message_N.db,
        and each shard carries its own Name2Id (sender rowids are shard-local).
        This one global index is what lets query_messages route a table to the
        right shard instead of only ever opening message_0.db.
        """
        _t0 = time.time()
        msg_dir = os.path.join(self._work_dir, "message")
        if not os.path.isdir(msg_dir):
            logger.info(f"[msg-index] message dir not found: {msg_dir}")
            return

        # md5(username) -> username, so a Msg_<md5> table name can be reversed
        for uid in list(self.contacts.keys()) + list(self.group_names.keys()):
            self._md5_to_username[hashlib.md5(uid.encode()).hexdigest()] = uid

        for fname in sorted(os.listdir(msg_dir)):
            if not (fname.startswith("message_") and fname.endswith(".db")):
                continue
            if any(x in fname for x in ("fts", "resource", "biz", "media")):
                continue
            dbf = os.path.join(msg_dir, fname)
            try:
                conn = self.sqlite3.connect(dbf)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")
                for (tname,) in cur.fetchall():
                    self._table_to_db.setdefault(tname, []).append(dbf)
                smap = {}
                try:
                    cur.execute("SELECT rowid, user_name FROM Name2Id")
                    for rowid, username in cur.fetchall():
                        smap[rowid] = self.contacts.get(username, username)
                        self._md5_to_username.setdefault(
                            hashlib.md5(username.encode()).hexdigest(), username)
                except Exception:
                    pass  # shard without Name2Id — sender names just stay unresolved
                self._db_sender_maps[dbf] = smap
                conn.close()
                self._msg_dbs.append(dbf)
            except Exception as e:
                logger.warning(f"[msg-index] error reading {fname}: {e}")

        logger.info(f"[msg-index] {len(self._msg_dbs)} shards, {len(self._table_to_db)} Msg_ tables, "
                    f"took {time.time()-_t0:.3f}s")

    def _resolve_contact_to_tables(self, contact):
        """Given a contact/group name, find matching usernames → Msg_ tables.
        Each table is verified against the cross-shard index (_table_to_db).
        Returns list of (tname, username, is_group, chat_name) or empty list."""
        _t0 = time.time()
        matches = []
        contact_lower = contact.lower()

        # Search in contacts
        for uid, name in self.contacts.items():
            if contact_lower in name.lower():
                tname = f'Msg_{hashlib.md5(uid.encode()).hexdigest()}'
                is_group = '@chatroom' in uid
                chat_name = self.group_names.get(uid, name) if is_group else name
                matches.append((tname, uid, is_group, chat_name))

        # Also search group names directly
        for gid, gname in self.group_names.items():
            if contact_lower in gname.lower():
                tname = f'Msg_{hashlib.md5(gid.encode()).hexdigest()}'
                if not any(m[1] == gid for m in matches):
                    matches.append((tname, gid, True, gname))

        # Verify against the cross-shard table index
        verified = [m for m in matches if m[0] in self._table_to_db]

        logger.info(f"Contact lookup '{contact}': {len(matches)} name matches, {len(verified)} tables verified, took {time.time()-_t0:.3f}s")
        self._last_contact_matched = bool(verified)
        return verified

    def _parse_row(self, row, is_group, sender_map=None):
        """Parse a single DB row into a message dict, returns (msg_dict or None, content_str).

        sender_map is the Name2Id mapping of the SHARD this row came from —
        sender rowids are shard-local, so it must not be a global map.
        """
        create_time = row[0]
        raw_content = row[1]
        sender_id = row[2]

        content = _decompress_content(raw_content)
        if not content:
            return None, None

        sender_name = None
        if is_group and not content.startswith('<'):
            match = re.match(r'^([^\n:]+):\n?', content)
            if match:
                sender_id_raw = match.group(1)
                sender_name = self.contacts.get(sender_id_raw, sender_id_raw)
                content = content[match.end():]
        elif not is_group and sender_id:
            sender_name = (sender_map or {}).get(sender_id)

        # ---------- VoIP 通话记录（Windows 4.x 也是同一套 XML） ----------
        if '<voipinvitemsg' in content:
            is_sent = not bool(sender_id and sender_id != 1)
            call_info = _parse_voip_content(content, is_sent)
            if call_info:
                summary = call_info['summary']
                return {
                    'time': create_time,
                    'kind': 'call',
                    'message': summary,
                    'is_received': bool(sender_id and sender_id != 1),
                    'sender': sender_name,
                    'call_type': call_info['call_type'],
                    'call_duration_sec': call_info['duration_sec'],
                    'call_duration_str': call_info['duration_str'],
                    'call_status_code': call_info['status_code'],
                    'call_status_cn': call_info['status_cn'],
                    'call_initiator': call_info['initiator'],
                }, summary

        if content.startswith('<?xml') or '<msg>' in content or '<voipmsg' in content:
            # 老版 voipmsg 包裹格式，兜底保留（极少见）
            voip_match = re.search(r'<voipmsg[^>]*>.*?<msg><!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
            if voip_match:
                content = f"[通话] {voip_match.group(1)}"
            else:
                title_match = re.search(r'<title>([^<]+)</title>', content)
                fileext_match = re.search(r'<fileext>([^<]+)</fileext>', content)
                if title_match:
                    title = title_match.group(1)
                    ext = fileext_match.group(1) if fileext_match else ''
                    if ext in ('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar'):
                        content = f"[file] {title}"
                    else:
                        content = f"[link] {title}"
                else:
                    content = "[card]"

        return {
            'time': create_time,
            'message': content,
            'is_received': bool(sender_id and sender_id != 1),
            'sender': sender_name,
        }, content

    def query_messages(self, limit=10, search=None, contact=None, days=None):
        """Query messages across ALL message_*.db shards.

        A Msg_ table can be split across several shards; this routes each
        (table, shard) pair via _table_to_db and resolves senders with that
        shard's Name2Id. The old code only ever opened message_0.db and
        silently dropped every contact whose table sat in another shard.
        """
        _t_total = time.time()
        all_messages = []
        min_time = int((datetime.now() - timedelta(days=days)).timestamp()) if days else None

        if not self._table_to_db:
            logger.warning("No message_*.db tables indexed — nothing to query")
            return []

        # ---- resolve working set: list of (tname, username, is_group, chat_name) ----
        if contact:
            targets = self._resolve_contact_to_tables(contact)
            if not targets:
                logger.info(f"No matching contact found for '{contact}'")
                return []
        else:
            targets = []
            for tname in self._table_to_db:
                username = self._md5_to_username.get(tname[len("Msg_"):])
                if not username:
                    continue
                is_group = '@chatroom' in username
                chat_name = self.group_names.get(username) or self.contacts.get(username, username)
                targets.append((tname, username, is_group, chat_name))

        # expand to per-shard work items — one Msg_ table may live in many shards
        work = []
        for tname, username, is_group, chat_name in targets:
            for dbf in self._table_to_db.get(tname, []):
                work.append((tname, dbf, username, is_group, chat_name))

        # Smart --recent mode: no contact, no search, has limit → rank by recency
        smart = bool(limit) and not search and not contact

        conns = {}

        def _conn(dbf):
            if dbf not in conns:
                conns[dbf] = self.sqlite3.connect(dbf)
            return conns[dbf]

        scanned = 0
        with_data = 0
        try:
            if smart:
                ranked = []
                for tname, dbf, username, is_group, chat_name in work:
                    try:
                        cur = _conn(dbf).cursor()
                        cur.execute(f"SELECT MAX(create_time) FROM {tname}")
                        r = cur.fetchone()
                    except Exception:
                        continue
                    if r and r[0]:
                        if min_time and r[0] < min_time:
                            continue
                        ranked.append((r[0], tname, dbf, username, is_group, chat_name))
                ranked.sort(key=lambda x: x[0], reverse=True)
                scan_limit = max(limit * 3, 50)
                work = [(t, d, u, g, c) for _ts, t, d, u, g, c in ranked[:scan_limit]]
                logger.debug(f"Smart mode: {len(ranked)} active (table,shard) pairs, scanning top {len(work)}")

            for tname, dbf, username, is_group, chat_name in work:
                scanned += 1
                sender_map = self._db_sender_maps.get(dbf, {})
                query = f"SELECT create_time, message_content, real_sender_id FROM {tname}"
                params = []
                if min_time:
                    query += " WHERE create_time >= ?"
                    params.append(min_time)
                query += " ORDER BY create_time DESC"
                if limit:
                    query += " LIMIT ?"
                    params.append(limit * 2)
                try:
                    cur = _conn(dbf).cursor()
                    cur.execute(query, params)
                    rows = cur.fetchall()
                except Exception as _e:
                    logger.debug(f"Query {tname} failed: {_e}")
                    continue
                if rows:
                    with_data += 1
                for row in rows:
                    msg, content = self._parse_row(row, is_group, sender_map)
                    if not msg:
                        continue
                    if search and search.lower() not in content.lower():
                        continue
                    msg['chat_name'] = chat_name
                    msg['is_group'] = is_group
                    all_messages.append(msg)
        finally:
            for c in conns.values():
                try:
                    c.close()
                except Exception:
                    pass

        all_messages.sort(key=lambda x: x['time'], reverse=True)
        logger.info(f"Query total: scanned {scanned} (table,shard) pairs ({with_data} with data), "
                    f"{len(all_messages)} msgs before limit, {len(conns)} shards opened, "
                    f"total {time.time()-_t_total:.3f}s")
        return all_messages[:limit] if limit else all_messages

    # ---------- 标签（Label）加载与查询 ----------
    def _load_labels(self):
        """Load contact labels from Windows contact.db.

        Two schema variants we've seen / are defensively supporting:
          1. camelCase (common in reference schemas):
               ContactLabel(LabelID INTEGER, LabelName TEXT)
               Contact.LabelIDList TEXT  (comma wrapped: ',1,2,5,')
          2. snake_case (newer Windows 4.x variant):
               contact_label(label_id INTEGER, label_name TEXT)
               contact.label_id_list TEXT

        If neither schema is present (or there are simply no labels), leaves
        self.labels empty. No fatal error — labels are an optional feature.
        """
        _t0 = time.time()
        contact_db = os.path.join(self._work_dir, "contact", "contact.db")
        if not os.path.exists(contact_db):
            # try capitalized variant
            alt = os.path.join(self._work_dir, "Contact", "Contact.db")
            if os.path.exists(alt):
                contact_db = alt
            else:
                logger.debug("No contact.db for label loading")
                return

        try:
            conn = self.sqlite3.connect(contact_db)
            cursor = conn.cursor()

            # Inventory tables/columns present in this DB
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_lower = {r[0].lower(): r[0] for r in cursor.fetchall()}

            # --- 1. Read label dictionary ---
            schema = None
            label_rows = []
            if 'contactlabel' in tables_lower:
                tname = tables_lower['contactlabel']
                try:
                    # Probe columns
                    cursor.execute(f"PRAGMA table_info({tname})")
                    cols_raw = [c[1] for c in cursor.fetchall()]
                    cols = [c.lower() for c in cols_raw]
                    if 'labelid' in cols and 'labelname' in cols:
                        cursor.execute(f"SELECT LabelID, LabelName FROM {tname}")
                        label_rows = cursor.fetchall()
                        schema = 'camel'
                    elif 'label_id' in cols and 'label_name' in cols:
                        id_col = cols_raw[cols.index('label_id')]
                        name_col = cols_raw[cols.index('label_name')]
                        cursor.execute(f"SELECT [{id_col}], [{name_col}] FROM [{tname}]")
                        label_rows = cursor.fetchall()
                        schema = 'snake'
                    elif 'label_id_' in cols and 'label_name_' in cols:
                        id_col = cols_raw[cols.index('label_id_')]
                        name_col = cols_raw[cols.index('label_name_')]
                        cursor.execute(f"SELECT [{id_col}], [{name_col}] FROM [{tname}]")
                        label_rows = cursor.fetchall()
                        schema = 'snake_underscore'
                    elif 'id' in cols and ('name' in cols or 'label' in cols):
                        name_col = 'name' if 'name' in cols else 'label'
                        cursor.execute(f"SELECT id, {name_col} FROM {tname}")
                        label_rows = cursor.fetchall()
                        schema = 'generic'
                except Exception as e:
                    logger.debug(f"ContactLabel probe failed: {e}")
            elif 'contact_label' in tables_lower:
                tname = tables_lower['contact_label']
                try:
                    cursor.execute(f"PRAGMA table_info({tname})")
                    cols_raw = [c[1] for c in cursor.fetchall()]
                    cols = [c.lower() for c in cols_raw]
                    if 'label_id' in cols and 'label_name' in cols:
                        id_col = cols_raw[cols.index('label_id')]
                        name_col = cols_raw[cols.index('label_name')]
                        cursor.execute(f"SELECT [{id_col}], [{name_col}] FROM [{tname}]")
                        label_rows = cursor.fetchall()
                        schema = 'snake'
                    elif 'label_id_' in cols and 'label_name_' in cols:
                        id_col = cols_raw[cols.index('label_id_')]
                        name_col = cols_raw[cols.index('label_name_')]
                        cursor.execute(f"SELECT [{id_col}], [{name_col}] FROM [{tname}]")
                        label_rows = cursor.fetchall()
                        schema = 'snake_underscore'
                    elif 'labelid' in cols and 'labelname' in cols:
                        cursor.execute(f"SELECT LabelID, LabelName FROM {tname}")
                        label_rows = cursor.fetchall()
                        schema = 'camel'
                except Exception as e:
                    logger.debug(f"contact_label probe failed: {e}")

            for lid, lname in label_rows:
                try:
                    lid_int = int(lid)
                except (TypeError, ValueError):
                    continue
                if lname:
                    self.labels[lid_int] = lname
                    self.label_name_to_id[lname.lower()] = lid_int

            # --- 2. Read per-contact label id list ---
            if 'contact' in tables_lower:
                cname = tables_lower['contact']
                try:
                    cursor.execute(f"PRAGMA table_info({cname})")
                    cols = [c[1].lower() for c in cursor.fetchall()]
                    # identify label-list column
                    list_col = None
                    for candidate in ('labelidlist', 'label_id_list', 'labelIdList', 'label_list'):
                        if candidate.lower() in cols:
                            list_col = candidate
                            break
                    if list_col:
                        # Also pick the username column
                        uname_col = None
                        for c in ('username', 'user_name', 'wxid'):
                            if c in cols:
                                uname_col = c
                                break
                        if uname_col:
                            cursor.execute(f"SELECT {uname_col}, {list_col} FROM {cname} WHERE {list_col} IS NOT NULL AND {list_col} != ''")
                            for uname, raw in cursor.fetchall():
                                ids = _parse_label_id_list(raw)
                                if ids:
                                    self.contact_labels[uname] = ids
                except Exception as e:
                    logger.debug(f"contact label-list load failed: {e}")

            # --- 3. Fallback: parse extra_buffer protobuf field 30 (label_list) ---
            # Windows WeChat 4.x stores per-contact label IDs in contact.extra_buffer
            # as a protobuf-encoded blob.  Field number 30 (wire type 2 / length-delimited)
            # contains a comma-separated string of label IDs, e.g. "41,67,68".
            if not self.contact_labels and 'contact' in tables_lower:
                cname = tables_lower['contact']
                try:
                    cursor.execute(f"PRAGMA table_info({cname})")
                    contact_cols = [c[1].lower() for c in cursor.fetchall()]
                    if 'extra_buffer' in contact_cols:
                        uname_col = None
                        for c in ('username', 'user_name', 'wxid'):
                            if c in contact_cols:
                                uname_col = c
                                break
                        if uname_col:
                            cursor.execute(
                                f"SELECT [{uname_col}], extra_buffer FROM [{cname}] "
                                f"WHERE extra_buffer IS NOT NULL AND length(extra_buffer) > 2"
                            )
                            for uname, blob in cursor.fetchall():
                                label_str = _extract_protobuf_field30(blob)
                                if label_str:
                                    ids = _parse_label_id_list(label_str)
                                    if ids:
                                        self.contact_labels[uname] = ids
                except Exception as e:
                    logger.debug(f"extra_buffer protobuf fallback failed: {e}")

            conn.close()
            self._labels_schema = schema
            logger.info(f"Loaded {len(self.labels)} labels, {len(self.contact_labels)} contacts-with-labels "
                        f"(schema={schema}), took {time.time()-_t0:.3f}s")
        except Exception as e:
            logger.warning(f"Load labels failed: {e}")

    def list_tags(self):
        """Return list of dicts: [{id, name, count}, ...] sorted by name."""
        if not self.labels:
            return []
        # count contacts per label
        counts = {}
        for lid_list in self.contact_labels.values():
            for lid in lid_list:
                counts[lid] = counts.get(lid, 0) + 1
        out = []
        for lid, name in self.labels.items():
            out.append({'id': lid, 'name': name, 'count': counts.get(lid, 0)})
        out.sort(key=lambda x: x['name'])
        return out

    def list_tag_contacts_usernames(self, tag_name):
        """Return list of wxid strings who carry this label."""
        lid = self.label_name_to_id.get(tag_name.lower()) if tag_name else None
        if lid is None:
            return []
        return [uname for uname, ids in self.contact_labels.items() if lid in ids]

    def query_by_tag(self, tag_name):
        """Return list of contacts carrying the given label.

        Each entry: {wxid, name, remark, tags}
        """
        if not self.labels:
            return []
        lid = self.label_name_to_id.get(tag_name.lower())
        if lid is None:
            return []  # tag not found
        result = []
        for uname, ids in self.contact_labels.items():
            if lid not in ids:
                continue
            name = self.contacts.get(uname, uname)
            tag_names = [self.labels[i] for i in ids if i in self.labels]
            result.append({
                'wxid': uname,
                'name': name,
                'remark': name,  # Windows contact store merges remark/nickname in _load_contacts
                'tags': tag_names,
            })
        result.sort(key=lambda x: x['name'] or '')
        return result

    def get_contact_tags(self, contact_name):
        """Return list of tag names attached to a contact (lookup by name / remark / wxid)."""
        if not self.labels or not self.contact_labels:
            return []
        contact_lower = (contact_name or '').lower()
        if not contact_lower:
            return []
        # Try direct wxid lookup
        if contact_name in self.contact_labels:
            ids = self.contact_labels[contact_name]
            return [self.labels[i] for i in ids if i in self.labels]
        # Search by name
        hits = set()
        for uname, name in self.contacts.items():
            if name and contact_lower in name.lower() and uname in self.contact_labels:
                hits.update(self.contact_labels[uname])
        return [self.labels[i] for i in hits if i in self.labels]

    def list_contacts(self):
        result = []
        for user_id, name in self.contacts.items():
            if '@chatroom' not in user_id and '@openim' not in user_id:
                result.append(('contact', name))
        for group_id, name in self.group_names.items():
            result.append(('group', name))
        return sorted(result, key=lambda x: x[1])

    def find_new_contacts(self, threshold):
        """Return [(first_ts, name, dt_str), ...] for non-group chats whose
        earliest message timestamp is >= threshold (unix epoch seconds).

        Output shape matches the Mac inline implementation so the call-site
        printer is shared between platforms.
        """
        _t0 = time.time()
        friends = {uid: name for uid, name in self.contacts.items()
                   if uid not in self.group_names and '@chatroom' not in uid}
        friend_md5 = {hashlib.md5(uid.encode()).hexdigest(): name
                      for uid, name in friends.items()}
        logger.info(f"[new-contacts] {len(friends)} 1-on-1 friends to check")

        msg_dir = os.path.join(self._work_dir, "message")
        if not os.path.isdir(msg_dir):
            logger.warning(f"[new-contacts] message dir not found: {msg_dir}")
            return []

        # A contact's messages can split across many message_*.db, so we must
        # take the GLOBAL MIN across all DBs before applying threshold.
        # Optimization: as soon as we see a contact with min_ts < threshold in
        # any DB, mark them OLD and skip in remaining DBs (saves SELECT MIN
        # calls on long-active contacts).
        global_min = {}        # md5 -> earliest create_time seen so far
        confirmed_old = set()  # md5 already proven < threshold (skip henceforth)

        dbs_scanned = 0
        tables_scanned = 0
        select_min_calls = 0

        for fname in sorted(os.listdir(msg_dir)):
            if not (fname.startswith("message_") and fname.endswith(".db")):
                continue
            if "fts" in fname or "resource" in fname or "biz" in fname or "media" in fname:
                continue
            dbf = os.path.join(msg_dir, fname)
            _t_db = time.time()
            try:
                conn = self.sqlite3.connect(dbf)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")
                tables_in_db = [r[0] for r in cur.fetchall()]
                tables_scanned += len(tables_in_db)
                db_select_calls = 0
                for table in tables_in_db:
                    md5 = table[len("Msg_"):]
                    if md5 not in friend_md5:
                        continue
                    if md5 in confirmed_old:
                        continue  # already < threshold from earlier db, skip
                    try:
                        cur.execute(f"SELECT MIN(create_time) FROM {table}")
                        row = cur.fetchone()
                        db_select_calls += 1
                    except Exception as _e:
                        logger.debug(f"[new-contacts] {table}: {_e}")
                        continue
                    if not row or not row[0]:
                        continue
                    ts = row[0]
                    prev = global_min.get(md5)
                    if prev is None or ts < prev:
                        global_min[md5] = ts
                    if ts < threshold:
                        confirmed_old.add(md5)
                conn.close()
                select_min_calls += db_select_calls
                dbs_scanned += 1
                logger.info(f"[new-contacts] {fname}: {len(tables_in_db)} Msg_ tables, "
                            f"{db_select_calls} MIN queries, {time.time()-_t_db:.3f}s")
            except Exception as e:
                logger.warning(f"[new-contacts] error reading {fname}: {e}")

        results = []
        for md5, ts in global_min.items():
            if ts >= threshold:
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                results.append((ts, friend_md5[md5], dt))

        logger.info(f"[new-contacts] DONE: {dbs_scanned} dbs, {tables_scanned} Msg_ tables, "
                    f"{select_min_calls} MIN queries, {len(global_min)} contacts seen, "
                    f"{len(confirmed_old)} confirmed old (early-skip), "
                    f"{len(results)} new, total {time.time()-_t0:.3f}s")
        return results


class WindowsV4Query(V4QueryBase):
    """Windows 微信 4.x：key 走内存扫描（wechat_extract_windows.py 产出
    all_keys.json），解密用 V4QueryBase 自带的手动 AES 逐页实现。
    读库逻辑全部继承自 V4QueryBase，本类不需要额外代码。"""
    pass


class MacV4Query(V4QueryBase):
    """Mac WeChat 4.x — SQLCipher4 (page 4096 / kdf 256000 / HMAC-SHA512).

    macOS WeChat 4.x abandoned the 3.x layout
        .../Application Support/com.tencent.xinWeChat/<2.x>/<hash>/Message/msg_N.db
        (Chat_<md5> tables, SQLCipher3: page 1024 / kdf 64000 / HMAC-SHA1)
    and adopted the SAME schema family as Windows 4.x:
        ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/
            <wxid>/db_storage/message/message_N.db   -> Msg_<md5> tables + Name2Id
            <wxid>/db_storage/contact/contact.db      -> contact / chatroom_member

    Because the decrypted schema matches Windows 4.x, this class subclasses
    the shared V4QueryBase and reuses its ENTIRE query stack verbatim
    (_load_contacts / _build_message_index / query_messages / labels /
    find_new_contacts). The only Mac-4.x-specific work is:
        (a) 4.x db_storage discovery
        (b) per-DB key acquisition (lldb hook CCKeyDerivationPBKDF, via
            wechat_extract_mac.py → data/all_keys.json)
        (c) SQLCipher4 decryption of the encrypted DBs to a plaintext cache.

    Key format: 微信 4.x 每个库一把独立 enc_key（64hex raw key），salt 从各库头读。
    历史上也接受 96hex（enc+salt）单 key，但正路是 per-DB keys 文件。
    """

    # Only these db_storage subdirs are worth decrypting; skip media / emoji /
    # fts / voice which are large and never queried here.
    _NEEDED_SUBDIRS = ('message', 'contact', 'session', 'biz', 'favorite')
    _SKIP_DB_MARKERS = ('fts', 'media', 'emoticon', 'resource', 'voice', 'hardlink')

    def __init__(self, key: str = None, user_hash: str = None, keys_file: str = None):
        import sqlite3
        self.sqlite3 = sqlite3
        self.full_key = (key or '').replace('0x', '').replace(' ', '').strip()
        self.src_db_storage = _find_mac4_db_storage(user_hash)
        if not self.src_db_storage:
            print("Error: Mac WeChat 4.x db_storage not found "
                  "(~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/*/db_storage)")
            sys.exit(1)
        # 微信 4.x 每个库一把独立 key（与 Windows 4.x 相同），由 wechat_extract_mac.py
        # 经 lldb hook CCKeyDerivationPBKDF 提取，存 data/all_keys.json。
        # 仅当没有 per-DB keys 且用户显式给了单 key 时，才回退到「单 key 全解」旧路径。
        self.db_keys = self._load_mac4_keys(keys_file)
        if not self.db_keys and not self.full_key:
            print("Error: 未找到 Mac 4.x 密钥。请先运行提取器：")
            print("  sudo python3 wechat_extract_mac.py")
            print("（微信 4.x 每库一把 key，经 lldb hook 提取到 data/all_keys.json）")
            sys.exit(1)
        logger.info(f"[mac4] db_storage={self.src_db_storage}, "
                    f"per_db_keys={len(self.db_keys)}, single_key={bool(self.full_key)}")
        plaintext_dir = self._decrypt_mac4(self.src_db_storage)
        # 复用 V4QueryBase 的整套 4.x 读库逻辑：key=None / keys_file=None →
        # 基类跳过自带解密，直接把明文目录 plaintext_dir 当普通 SQLite 读。
        super().__init__(plaintext_dir, key=None, keys_file=None)

    def _load_mac4_keys(self, keys_file: str = None) -> dict:
        """加载 per-DB 密钥表 {相对路径: enc_key_hex}。

        默认读 skill 的 data/all_keys.json（wechat_extract_mac.py 产出；兼容旧 all_keys.json）。
        兼容两种取值形态：直接 hex 串，或 {"enc_key": hex}（与 Windows keys 同构）。
        """
        if not keys_file:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            keys_file = resolve_keys_file(os.path.join(script_dir, '..', 'data'))
        if not keys_file or not os.path.exists(keys_file):
            return {}
        try:
            with open(keys_file, encoding='utf-8') as f:
                raw = _json.load(f)
        except Exception as e:
            logger.warning(f"[mac4] 读取 keys 文件失败 {keys_file}: {e}")
            return {}
        data = raw.get('keys', raw) if isinstance(raw, dict) else {}
        out = {}
        for rel, v in data.items():
            if isinstance(v, dict):
                v = v.get('enc_key')
            if isinstance(v, str) and v:
                out[os.path.normpath(rel)] = v.replace('0x', '').replace(' ', '').strip()
        return out

    def _key_for(self, rel: str) -> str:
        """取某库的解密 key：优先 per-DB key，回退单 key。"""
        return self.db_keys.get(os.path.normpath(rel)) or self.full_key

    def _decrypt_mac4(self, db_storage: str) -> str:
        """Decrypt the needed SQLCipher4 DBs into a stable plaintext cache dir,
        mirroring the db_storage relative layout so WindowsWeChatQuery finds
        message/ and contact/ where it expects them. Per-file mtime caching
        skips re-decryption of unchanged DBs (same policy as the Windows path).
        """
        try:
            import sqlcipher3
        except ImportError:
            print("Error: pip3 install sqlcipher3  "
                  "(required for Mac 4.x SQLCipher4 decryption)")
            sys.exit(1)

        cache_dir = _get_decrypt_cache_dir(db_storage)

        def _open_encrypted(path, key):
            conn = sqlcipher3.connect(path)
            cur = conn.cursor()
            # 4.x = SQLCipher4. 每库用自己的 enc_key（64-hex raw key），salt 从各库
            # 头读；main key 不再派生（raw key），HMAC 子密钥按下面算法参数派生。
            cur.execute(f"PRAGMA key = \"x'{key}'\"")
            cur.execute("PRAGMA cipher_page_size = 4096")
            cur.execute("PRAGMA kdf_iter = 256000")
            cur.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
            cur.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
            return conn, cur

        matched = reused = failed = 0
        for root, _dirs, files in os.walk(db_storage):
            rel_root = os.path.relpath(root, db_storage)
            top = rel_root.split(os.sep)[0]
            if top not in self._NEEDED_SUBDIRS:
                continue
            for fn in files:
                if not fn.endswith('.db') or fn.endswith('-wal') or fn.endswith('-shm'):
                    continue
                if any(m in fn for m in self._SKIP_DB_MARKERS):
                    continue
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, db_storage)
                dst = os.path.join(cache_dir, rel)

                # Reuse cached plaintext if the source DB hasn't changed.
                if os.path.exists(dst):
                    try:
                        if os.path.getmtime(dst) >= os.path.getmtime(src):
                            reused += 1
                            matched += 1
                            continue
                    except OSError:
                        pass

                key = self._key_for(rel)
                if not key:
                    # 没有这个库的 key（per-DB keys 表里没有、也没单 key 兜底）——跳过。
                    logger.info(f"[mac4-decrypt] skip {rel}: 无对应 key")
                    continue

                os.makedirs(os.path.dirname(dst), exist_ok=True)
                tmp = dst + '.tmp'
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                conn = None
                try:
                    conn, cur = _open_encrypted(src, key)
                    # sqlcipher_export writes a fully decrypted copy into the
                    # attached (unencrypted, KEY '') database.
                    cur.execute("ATTACH DATABASE ? AS plaintext KEY ''", (tmp,))
                    cur.execute("SELECT sqlcipher_export('plaintext')")
                    cur.execute("DETACH DATABASE plaintext")
                    conn.close()
                    conn = None
                    os.replace(tmp, dst)
                    matched += 1
                    logger.info(f"[mac4-decrypt] ok {rel}")
                except Exception as e:
                    failed += 1
                    logger.warning(f"[mac4-decrypt] FAILED {rel}: {e}")
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass

        print(f"Mac 4.x: decrypted {matched} DBs "
              f"(reused {reused} from cache, {failed} failed)")
        logger.info(f"[mac4-decrypt] {matched} ok ({reused} cached), "
                    f"{failed} failed, cache={cache_dir}")
        if matched == 0:
            print("Warning: 0 DBs decrypted — the key may be wrong, or this is "
                  "not a SQLCipher4 (4.x) database. Check SKILL.md 取密钥 §4.x.")
        return cache_dir


# ── 向后兼容别名（旧代码/文档仍可用老类名）──────────────────────
WindowsWeChatQuery = WindowsV4Query
MacV4WeChatQuery = MacV4Query


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


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _local_time_to_iso(value: str) -> str:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').astimezone().isoformat(timespec='seconds')
    except ValueError:
        return value


def _collect_record_to_event(record: dict, collected_at: str) -> dict:
    data = record.get('data') or {}
    chat = data.get('chat') or ''
    sender = data.get('sender') or ''
    text = data.get('text') or ''
    time_str = data.get('time') or ''
    legacy_id = record.get('id') or hashlib.sha1(
        f"{chat}|{sender}|{time_str}|{text}".encode('utf-8')
    ).hexdigest()[:16]
    event_id = legacy_id if str(legacy_id).startswith('wechat:') else f"wechat:{legacy_id}"
    return {
        'schema': 'collectorx.event.v1',
        'id': event_id,
        'collector': 'wechat',
        'source': record.get('source') or _format_collect_source(chat, False, time_str),
        'owner_scope': 'personal',
        'kind': 'message',
        'time': _local_time_to_iso(time_str),
        'collected_at': collected_at,
        'data': {
            'chat': chat,
            'sender': sender,
            'sender_is_owner': sender == '我',
            'text': text,
            'text_length': len(text),
            'message_type': 'text',
        },
        'raw_ref': {
            'legacy_collect_id': legacy_id,
            'chat': chat,
            'time': time_str,
        },
        'privacy': {
            'sensitive': True,
            'local_only': True,
            'contains': ['personal_message', 'contact'],
        },
        'wiki_targets': [
            'internal.communication.wechat',
        ],
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(_json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')


def _is_gap_event(event: dict) -> bool:
    data = event.get('data') or {}
    return isinstance(data, dict) and bool(data.get('gap'))


def _build_collect_manifest(records, events, *, collected_at: str, args, platform: str, gap: dict = None) -> dict:
    chats = sorted({(r.get('data') or {}).get('chat') for r in records if (r.get('data') or {}).get('chat')})
    message_events = [event for event in events if event.get('kind') == 'message']
    gap_events = [event for event in events if _is_gap_event(event)]
    usable_events = [event for event in events if not _is_gap_event(event)]
    owner_sent = sum(1 for event in message_events if event.get('data', {}).get('sender_is_owner'))
    text_lengths = [event.get('data', {}).get('text_length', 0) for event in message_events]
    readiness_status = (gap or {}).get('status') or ('baseline+audit' if message_events else 'gap')
    readiness_reason = (gap or {}).get('reason') or ('wechat_collect_standard_package_written' if message_events else 'no_wechat_messages_collected')
    return {
        'schema': 'collectorx.collection_manifest.v1',
        'collector': 'wechat',
        'collected_at': collected_at,
        'event_count': len(events),
        'message_event_count': len(message_events),
        'usable_event_count': len(usable_events),
        'gap_event_count': len(gap_events),
        'source_record_count': len(records),
        'collection_readiness': {
            'status': readiness_status,
            'real_account_validation': False,
            'standard_package': True,
            'reason': readiness_reason,
            'gap_event': bool(gap),
            'can_enter_finclaw_lake': bool(events),
            'can_enter_personal_channel_lake': bool(message_events),
            'can_enter_data_quality_lake': bool(gap_events),
            'can_enter_investor_lens': bool(message_events),
            'can_enter_investor_wiki': False,
            'next_action': (gap or {}).get('next_action'),
        },
        'platform_status': {
            'platform': platform,
            'macos': 'requires_wechat_4_keys_and_sip_disabled_for_key_extraction',
            'windows': 'requires_authorized_db_dir_and_all_keys_or_decrypted_db',
            'linux': 'requires_authorized_db_dir_and_root_key_extraction',
        },
        'scope': {
            'collects': [
                'owner_relevant_private_chat_messages',
                'explicit_or_active_group_messages',
                'chat_name',
                'sender',
                'message_time',
                'message_text',
            ],
            'excludes': [
                'wechat_password',
                'encryption_keys',
                'cookies',
                'tokens',
                'raw_database_pages',
                'unparticipated_groups_by_default',
                'xml_cards_without_text',
                'recalled_message_notices',
            ],
        },
        'filter_policy': {
            'days': args.days,
            'after': args.after,
            'limit': args.limit,
            'exclude_count': len(_split_csv(args.exclude)),
            'include_group_count': len(_split_csv(args.include_groups)),
            'active_group_days': args.active_group_days if args.active_group_days is not None else 30,
            'participated_only': bool(args.participated_only),
        },
        'field_coverage': {
            'chat': bool(chats),
            'sender': any(event.get('data', {}).get('sender') for event in events),
            'sender_is_owner': any(event.get('data', {}).get('sender_is_owner') for event in events),
            'time': any(event.get('time') for event in events),
            'text': any(event.get('data', {}).get('text') for event in events),
            'text_length': bool(text_lengths),
        },
        'message_surface_summary': {
            'chat_count': len(chats),
            'owner_sent_events': owner_sent,
            'received_events': max(0, len(message_events) - owner_sent),
            'max_text_length': max(text_lengths) if text_lengths else 0,
        },
        'source_audit': {
            'source_type': 'wechat_local_database_query',
            'legacy_json_array_compatible': True,
            'writes_final_wiki_directly': False,
            'requires_downstream_lens': 'wechat-investment-dialogue',
            'gap_status': (gap or {}).get('status'),
        },
        'evidence_policy': {
            'generic_collector': True,
            'investment_claim_allowed': False,
            'routes_to_lens': 'wechat-investment-dialogue',
            'writes_investor_wiki_evidence_directly': False,
        },
    }


def _collect_gap_event(*, status: str, reason: str, collected_at: str, platform: str = 'unknown', next_action: str = None) -> dict:
    digest = hashlib.sha1(f"{status}|{reason}|{platform}".encode('utf-8')).hexdigest()[:20]
    return {
        'schema': 'collectorx.event.v1',
        'id': f'wechat:gap:{digest}',
        'collector': 'wechat',
        'source': '微信采集前置条件',
        'owner_scope': 'personal',
        'kind': 'profile',
        'time': collected_at,
        'collected_at': collected_at,
        'data': {
            'profile_type': 'wechat_collection_gap',
            'subtype': 'collector_gap',
            'action_type': 'collector_gap',
            'gap': status,
            'status': status,
            'reason': reason,
            'platform': platform,
            'next_action': next_action,
            'standard_package': True,
            'generic_collector': True,
            'investment_claim_allowed': False,
            'writes_investor_wiki_evidence_directly': False,
            'raw_database_access_performed': False,
            'raw_database_pages_collected': False,
            'credentials_collected': False,
            'message_text_collected': False,
            'personal_message_fact_collected': False,
            'direct_investment_conclusion_claimed': False,
        },
        'raw_ref': {'derived_from': 'wechat_collect_preflight'},
        'privacy': {
            'sensitive': True,
            'local_only': True,
            'contains': ['collection_gap'],
        },
        'wiki_targets': [
            DATA_QUALITY_TARGET,
        ],
    }


def _write_collect_summary(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# WeChat Collector Summary',
        '',
        f"- Collector: `{manifest['collector']}`",
        f"- Collected at: `{manifest['collected_at']}`",
        f"- Events: `{manifest['event_count']}`",
        f"- Messages: `{manifest.get('message_event_count', 0)}`",
        f"- Gaps: `{manifest.get('gap_event_count', 0)}`",
        f"- Chats: `{manifest['message_surface_summary']['chat_count']}`",
        f"- Readiness: `{manifest['collection_readiness']['status']}`",
        '',
        'This is a generic communication collector package. Feed `lake/wechat/events.jsonl` into the `wechat-investment-dialogue` lens before using it as FinClaw investor Wiki evidence.',
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def _write_collect_package(records, out_dir: str, *, args, platform: str, collected_at: str = None) -> dict:
    out_path = Path(out_dir).expanduser()
    collected_at = collected_at or _now_iso()
    events = [_collect_record_to_event(record, collected_at) for record in records]
    gap = None
    if not events:
        gap = {
            'status': 'no_wechat_messages_collected',
            'reason': 'wechat_query_returned_no_owner_relevant_text_messages',
            'next_action': '检查联系人/群聊授权范围、时间范围、活跃群策略和 --exclude/--include-groups 过滤条件。',
        }
        events = [
            _collect_gap_event(
                status=gap['status'],
                reason=gap['reason'],
                collected_at=collected_at,
                platform=platform,
                next_action=gap['next_action'],
            )
        ]
    manifest = _build_collect_manifest(records, events, collected_at=collected_at, args=args, platform=platform, gap=gap)
    _write_jsonl(out_path / 'lake' / 'wechat' / 'events.jsonl', events)
    _write_json(out_path / 'manifest.json', manifest)
    _write_collect_summary(out_path / 'SUMMARY.md', manifest)
    return manifest


def _write_collect_gap_package(
    out_dir: str,
    *,
    args,
    platform: str,
    status: str,
    reason: str,
    next_action: str,
    collected_at: str = None,
) -> dict:
    out_path = Path(out_dir).expanduser()
    collected_at = collected_at or _now_iso()
    gap = {
        'status': status,
        'reason': reason,
        'next_action': next_action,
    }
    events = [
        _collect_gap_event(
            status=status,
            reason=reason,
            collected_at=collected_at,
            platform=platform,
            next_action=next_action,
        )
    ]
    manifest = _build_collect_manifest([], events, collected_at=collected_at, args=args, platform=platform, gap=gap)
    _write_jsonl(out_path / 'lake' / 'wechat' / 'events.jsonl', events)
    _write_json(out_path / 'manifest.json', manifest)
    _write_collect_summary(out_path / 'SUMMARY.md', manifest)
    return manifest


def _collect_out_dir_requested(args) -> bool:
    return bool(getattr(args, 'collect', False) and getattr(args, 'out_dir', None))


def _finish_collect_gap(args, *, platform: str, status: str, reason: str, next_action: str) -> bool:
    if not _collect_out_dir_requested(args):
        return False
    manifest = _write_collect_gap_package(
        args.out_dir,
        args=args,
        platform=platform,
        status=status,
        reason=reason,
        next_action=next_action,
    )
    print(_json.dumps({
        'collector': 'wechat',
        'event_count': manifest['event_count'],
        'out_dir': str(Path(args.out_dir).expanduser()),
        'status': manifest['collection_readiness']['status'],
    }, ensure_ascii=False, sort_keys=True))
    return True


def _format_collect_source(chat: str, is_group: bool, time_str: str) -> str:
    date = (time_str or '')[:10]
    chat = chat or '(unknown)'
    if is_group:
        return f"微信群「{chat}」· {date} 的聊天" if date else f"微信群「{chat}」的聊天"
    return f"跟{chat}在 {date} 的微信聊天" if date else f"跟{chat}的微信聊天"


def _read_wechat_config():
    """读取微信4.x配置文件，获取自定义数据路径（Windows only）"""
    config_dir = os.path.join(
        os.environ.get('USERPROFILE', ''),
        'AppData', 'Roaming', 'Tencent', 'xwechat', 'config'
    )
    if not os.path.isdir(config_dir):
        return []
    paths = []
    for f in os.listdir(config_dir):
        if f.endswith('.ini'):
            try:
                with open(os.path.join(config_dir, f), 'rb') as fp:
                    content = fp.read()
                for enc in ['gbk', 'utf-8', 'utf-16']:
                    try:
                        text = content.decode(enc).strip()
                        if text and len(text) > 2 and os.path.isdir(text):
                            paths.append(text)
                            break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
            except Exception:
                pass
    return paths


def _auto_find_windows_db_dir():
    """Windows: 自动查找 db_storage 目录（支持自定义路径和多账号）"""
    candidates = []

    def scan(base_path):
        xwechat = os.path.join(base_path, 'xwechat_files')
        if not os.path.isdir(xwechat):
            return
        for wxid_dir in os.listdir(xwechat):
            db_storage = os.path.join(xwechat, wxid_dir, 'db_storage')
            if os.path.isdir(db_storage):
                has_db = any(
                    f.endswith('.db')
                    for root, _, files in os.walk(db_storage)
                    for f in files
                )
                if has_db:
                    # 优先用 login/key_info.db 的修改时间（最准确）
                    login_dir_path = os.path.join(xwechat, 'all_users', 'login')
                    mtime = 0
                    if os.path.isdir(login_dir_path):
                        for login_name in os.listdir(login_dir_path):
                            if wxid_dir.startswith(login_name):
                                login_key = os.path.join(login_dir_path, login_name, 'key_info.db')
                                if os.path.exists(login_key):
                                    mtime = os.path.getmtime(login_key)
                                    break
                    if not mtime:
                        # fallback: 递归取最新文件的修改时间
                        for r, _, fs in os.walk(db_storage):
                            for f in fs:
                                t = os.path.getmtime(os.path.join(r, f))
                                if t > mtime:
                                    mtime = t
                    candidates.append((db_storage, mtime, wxid_dir))

    # 1. 从微信配置文件读取
    for base_path in _read_wechat_config():
        scan(base_path)
        scan(os.path.join(base_path, 'Documents'))

    # 2. 默认位置
    for env_var in ['USERPROFILE', 'HOME']:
        user_dir = os.environ.get(env_var)
        if user_dir:
            scan(user_dir)
            scan(os.path.join(user_dir, 'Documents'))

    # 3. 其他用户目录
    for drive in ['C:', 'D:', 'E:']:
        users_dir = os.path.join(drive + os.sep, 'Users')
        if os.path.isdir(users_dir):
            for user in os.listdir(users_dir):
                scan(os.path.join(users_dir, user))

    # 去重
    seen = set()
    unique = []
    for path, mtime, wxid in candidates:
        if path not in seen:
            seen.add(path)
            unique.append((path, mtime, wxid))

    if not unique:
        return None

    unique.sort(key=lambda x: x[1], reverse=True)
    if len(unique) > 1:
        print(f"发现 {len(unique)} 个微信账号数据目录：")
        for path, mtime, wxid in unique:
            time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
            print(f"  {wxid} (最后活跃: {time_str})")
        print(f"使用最近活跃的: {unique[0][2]}\n")

    return unique[0][0]


# ── Mac WeChat version detection & 4.x path discovery ───────────────
_MAC_WECHAT_CONTAINER = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data"
)


def _find_mac4_db_storage(user_hash: str = None):
    """Discover the Mac WeChat 4.x db_storage directory.

    4.x moved data OUT of the 3.x location and into:
        ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/
            xwechat_files/<wxid>/db_storage/
    (This is why the 3.x `_find_wechat_data_path` — which scans Application
    Support for `2.x` version dirs — never sees 4.x data. 4.x lives in a
    different tree entirely, so it gets its own discovery function rather than
    a patch to the 3.x one.)

    Returns the db_storage path of the most-recently-active account, or None.
    """
    xwechat = os.path.join(_MAC_WECHAT_CONTAINER, "Documents", "xwechat_files")
    if not os.path.isdir(xwechat):
        return None

    candidates = []
    for wxid_dir in os.listdir(xwechat):
        if wxid_dir.startswith('.') or wxid_dir in ('all_users',):
            continue
        db_storage = os.path.join(xwechat, wxid_dir, 'db_storage')
        if not os.path.isdir(db_storage):
            continue
        has_db = any(
            f.endswith('.db')
            for _r, _d, fs in os.walk(db_storage)
            for f in fs
        )
        if not has_db:
            continue
        mtime = _dir_latest_mtime(os.path.join(db_storage, 'message')) or \
            _dir_latest_mtime(db_storage)
        candidates.append((db_storage, mtime, wxid_dir))

    if not candidates:
        return None

    if user_hash:
        for path, _m, wxid in candidates:
            if user_hash in wxid:
                return path
        print(f"Warning: Mac 4.x account '{user_hash}' not found, using most recent")

    candidates.sort(key=lambda x: x[1], reverse=True)
    if len(candidates) > 1:
        print(f"Found {len(candidates)} Mac 4.x accounts, using: {candidates[0][2]}")
    return candidates[0][0]


def _dir_latest_mtime(path: str) -> float:
    """Latest mtime among files under path (0 if none / missing)."""
    latest = 0.0
    if not os.path.isdir(path):
        return latest
    for r, _d, fs in os.walk(path):
        for f in fs:
            try:
                latest = max(latest, os.path.getmtime(os.path.join(r, f)))
            except OSError:
                pass
    return latest


def _detect_mac_version():
    """Auto-detect the installed Mac WeChat generation.

    Returns ('mac4', db_storage_path) or ('mac3', None). When BOTH a 3.x user
    dir and a 4.x db_storage are present (common right after an upgrade, when
    the old tree lingers), the more-recently-active one wins.
    """
    mac4 = _find_mac4_db_storage()

    mac3_base = os.path.join(
        _MAC_WECHAT_CONTAINER,
        "Library", "Application Support", "com.tencent.xinWeChat"
    )
    mac3_mtime = 0.0
    if os.path.isdir(mac3_base):
        for item in os.listdir(mac3_base):
            vpath = os.path.join(mac3_base, item)
            if os.path.isdir(vpath) and item.startswith("2."):
                for ud in os.listdir(vpath):
                    mp = os.path.join(vpath, ud, "Message")
                    if os.path.isdir(mp):
                        try:
                            mac3_mtime = max(mac3_mtime, os.path.getmtime(mp))
                        except OSError:
                            mac3_mtime = max(mac3_mtime, 1.0)

    if mac4 and mac3_mtime:
        mac4_mtime = _dir_latest_mtime(os.path.join(mac4, 'message'))
        return ('mac4', mac4) if mac4_mtime >= mac3_mtime else ('mac3', None)
    if mac4:
        return ('mac4', mac4)
    return ('mac3', None)


def _mac_friend_list(exporter):
    """Load Mac friends (type=3) as [(username, nickname, remark), ...]"""
    contact_db = os.path.join(exporter.base_path, "Contact", "wccontact_new2.db")
    conn, cur = exporter._open_db(contact_db)
    cur.execute("SELECT m_nsUsrName, nickname, m_nsRemark FROM WCContact WHERE m_uiType=3")
    rows = cur.fetchall()
    conn.close()
    return rows


def main():
    _t_main = time.time()
    logger.info("=" * 60)
    logger.info(f"wechat_query.py v{__version__} started")

    _cleanup_legacy_temp()
    _migrate_legacy_decrypted()

    # Force UTF-8 output on Windows (PowerShell/cmd default is GBK)
    if sys.platform in ('win32', 'cygwin'):
        for stream in [sys.stdout, sys.stderr]:
            if stream and hasattr(stream, 'reconfigure'):
                try:
                    stream.reconfigure(encoding='utf-8')
                except Exception:
                    stream.reconfigure(errors='replace')

    parser = argparse.ArgumentParser(description='WeChat chat record query tool (Mac + Windows)')
    parser.add_argument('--key', help='DB encryption key in hex (advanced; normal flow uses auto-extracted keys)')
    parser.add_argument('--keys', help='Windows: path to all_keys.json from wechat_extract_windows.py')
    parser.add_argument('--user', help='Mac: specify user directory hash')
    parser.add_argument('--db-dir', help='Windows: path to db_storage directory (encrypted or decrypted)')
    parser.add_argument('--recent', type=int, default=None, help='Show latest N messages (default: 10 when no other filters)')
    parser.add_argument('--search', help='Search keyword')
    parser.add_argument('--contact', help='Filter by contact or group name')
    parser.add_argument('--days', type=int, help='Only query last N days')
    parser.add_argument('--limit', type=int, help='Limit result count')
    parser.add_argument('--export', help='Export owner-relevant compact, cleaned txt to file')
    parser.add_argument('--export-all', action='store_true',
                        help='With --export compact mode, include all chats including inactive groups')
    parser.add_argument('--raw-export', action='store_true',
                        help='Keep legacy raw multi-line export with uncleaned XML/card payloads; implies --export-all')
    parser.add_argument('--export-max-chars', type=int, default=500, metavar='N',
                        help='Max characters per exported message in compact mode (default 500; 0 disables truncation)')
    parser.add_argument('--list-contacts', action='store_true', help='List all contacts and groups')
    parser.add_argument('--filter', dest='name_filter', metavar='KEYWORD', help='Filter --list-contacts by name substring (case-insensitive)')
    parser.add_argument('--new-contacts', type=int, metavar='DAYS', help='Show contacts whose first message is within last N days')
    parser.add_argument('--list-tags', action='store_true', help='List all contact tags/labels (Mac 4.x + Windows 4.x)')
    parser.add_argument('--tag', metavar='NAME', help='Query contacts/messages by tag name (Mac 4.x + Windows 4.x). Combine with --recent/--search/--days for messages.')
    parser.add_argument('--contact-tags', metavar='NAME', help='Show tags attached to a specific contact')
    parser.add_argument('--collect', action='store_true', help='Collect mode: query+filter+format messages to CUFin JSON in one shot')
    parser.add_argument('--after', metavar='TIME', help='Collect mode: only messages at/after this time, format "YYYY-MM-DD HH:MM:SS"')
    parser.add_argument('--out', metavar='FILE', help='Collect mode: write the JSON array to this file')
    parser.add_argument('--out-dir', metavar='DIR', help='Collect mode: write a standard CollectorX package to this directory')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print --collect JSON for human inspection; default collect output is compact')
    parser.add_argument('--exclude', metavar='NAMES',
                        help='Collect/export mode: comma-separated chat names to skip (blacklist; applies to private and groups)')
    parser.add_argument('--include-groups', metavar='NAMES',
                        help='Collect/export mode: comma-separated group names to always include (whitelist, in addition to active-recent ones)')
    parser.add_argument('--active-group-days', type=int, default=None, metavar='N',
                        help='Collect/export mode: auto-include groups I have spoken in within last N days (collect default 30; export default follows --days, or 30 when --days is omitted; 0 disables)')
    parser.add_argument('--participated-only', action='store_true',
                        help='Collect mode: only keep chats the owner actually spoke in (applies to private chats too; default collects all private). 没回过的会话(纯接收/营销/服务号)不收,省 token。')
    args = parser.parse_args()

    # Strip leading/trailing whitespace from name-like inputs.
    # Some upstream clients (notably openclaw-control-ui's exec wrapper) inject a
    # leading space when forwarding the command, so `--contact "韩成丰"` arrives at
    # argv as ` 韩成丰`, which breaks our substring lookup. Strip defensively here
    # and warn so the caller knows their input was sanitized.
    for _attr in ('contact', 'search', 'name_filter', 'tag', 'contact_tags'):
        _v = getattr(args, _attr, None)
        if isinstance(_v, str) and _v != _v.strip():
            sys.stderr.write(f"⚠️  --{_attr.replace('_','-')} arg had whitespace, stripped: {_v!r} -> {_v.strip()!r}\n")
            setattr(args, _attr, _v.strip())

    if args.db_dir or sys.platform == 'win32' or sys.platform == 'cygwin':
        # Windows: 自动检测 db_dir（如果未指定）
        db_dir = args.db_dir
        if not db_dir:
            db_dir = _auto_find_windows_db_dir()
            if db_dir:
                print(f"Auto-detected db_dir: {db_dir}")
                logger.info(f"Auto-detected db_dir: {db_dir}")
            else:
                if _finish_collect_gap(
                    args,
                    platform='windows' if sys.platform in ('win32', 'cygwin') else 'generic-db-dir',
                    status='needs_readable_wechat_db_dir',
                    reason='wechat_db_dir_not_detected',
                    next_action='请授权并指定微信 4.x db_storage 目录，或先完成平台提取器准备。',
                ):
                    return
                print("Error: 未找到微信数据目录，请用 --db-dir 指定")
                logger.error("Auto-detect failed: no db_dir found")
                sys.exit(1)
        elif not os.path.isdir(db_dir):
            if _finish_collect_gap(
                args,
                platform='windows' if sys.platform in ('win32', 'cygwin') else 'generic-db-dir',
                status='needs_readable_wechat_db_dir',
                reason='wechat_db_dir_path_not_found',
                next_action='请确认用户授权的微信 4.x db_storage 目录存在且当前进程可读。',
            ):
                return
            print(f"Error: {db_dir} not found")
            sys.exit(1)

        # Auto-detect keys file: 1) user specified --keys  2) skill's data dir  3) no keys (decrypted db)
        keys_file = args.keys
        if not keys_file and not args.key:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            auto_keys = resolve_keys_file(os.path.join(script_dir, '..', 'data'))
            if auto_keys:
                keys_file = auto_keys
                print(f"Auto-detected keys: {auto_keys}")
                logger.info(f"Auto-detected keys file: {auto_keys}")

        logger.info(f"Windows mode: db_dir={db_dir}, keys_file={keys_file}, has_key={bool(args.key)}")
        if sys.platform in ('win32', 'cygwin'):
            collector_platform = 'windows'
        elif sys.platform.startswith('linux'):
            collector_platform = 'linux'
        else:
            collector_platform = 'generic-db-dir'
        _t_init = time.time()
        try:
            exporter = WindowsV4Query(db_dir, key=args.key, keys_file=keys_file)
        except SystemExit:
            if _finish_collect_gap(
                args,
                platform=collector_platform,
                status='needs_wechat_decryption_or_plaintext_db',
                reason='wechat_windows_or_linux_query_preflight_failed',
                next_action='请确认已运行对应平台的微信 key 提取器，或提供已授权可读的明文/已解密数据库目录。',
            ):
                return
            raise
        logger.info(f"Exporter init took {time.time()-_t_init:.3f}s")
    else:
        mac_key = args.key or os.environ.get('WECHAT_KEY')

        # Auto-detect 3.x vs 4.x by which data tree is present (recency wins if
        # both linger after an upgrade). A 96-hex key (enc+salt) is a strong 4.x
        # signal that overrides an ambiguous probe when a 4.x tree exists.
        mac_ver, _mac4_path = _detect_mac_version()
        _kh = (mac_key or '').replace('0x', '').replace(' ', '').strip()
        if mac_ver != 'mac4' and len(_kh) >= 96 and _find_mac4_db_storage():
            mac_ver = 'mac4'

        if mac_ver == 'mac4':
            # 4.x 走 per-DB keys（data/all_keys.json，由 wechat_extract_mac.py 提取）；
            # 不再强制要 WECHAT_KEY。MacV4 内部若既无 keys 文件又无单 key 才报错。
            collector_platform = 'macos'
            try:
                exporter = MacV4Query(mac_key, args.user, keys_file=args.keys)
            except SystemExit:
                if _finish_collect_gap(
                    args,
                    platform=collector_platform,
                    status='needs_wechat_4_keys_or_dependencies',
                    reason='wechat_macos_4_query_preflight_failed',
                    next_action='请确认微信 4.x 已登录、SIP/lldb 提取前置条件满足，并运行 wechat_extract_mac.py 生成 data/all_keys.json；如缺少 sqlcipher3，请安装后重试。',
                ):
                    return
                raise
            logger.info("Mac mode: WeChat 4.x (SQLCipher4, page 4096 / kdf 256000 / HMAC-SHA512)")
        else:
            # 灵镜自 v0.9.1 起仅支持微信 4.x（3.x SQLCipher3 已下线）。
            if _finish_collect_gap(
                args,
                platform='macos',
                status='needs_wechat_4_data',
                reason='wechat_4_data_not_detected_or_legacy_3x_detected',
                next_action='请把微信升级到 4.x，并完成用户授权的本机数据与 per-DB key 提取流程后重试。',
            ):
                return
            print("Error: 未检测到微信 4.x 数据（或检测到已停止支持的 3.x 数据）。")
            print("  请把微信升级到 4.x，再运行 sudo python3 wechat_extract_mac.py 提取 per-DB key 后重试。")
            print("  Windows：先运行 python wechat_extract_windows.py，再 --db-dir 查询。")
            sys.exit(1)

    print(f"Loaded {len(exporter.contacts)} contacts")

    if args.list_contacts:
        contacts = exporter.list_contacts()
        if args.name_filter:
            kw = args.name_filter.lower()
            contacts = [(t, n) for t, n in contacts if kw in n.lower()]
        print("=" * 50)
        title = f"Contacts (filter={args.name_filter})" if args.name_filter else "Contacts"
        print(title)
        print("=" * 50)
        # When filtering, show all matches (usually small); otherwise cap at 100
        cap = len(contacts) if args.name_filter else 100
        for type_name, name in contacts[:cap]:
            print(f"  [{type_name}] {name}")
        if len(contacts) > cap:
            print(f"  ... total {len(contacts)}")
        elif args.name_filter:
            print(f"  ({len(contacts)} matched)")
        return

    if args.list_tags:
        try:
            tags = exporter.list_tags()
        except LabelNotSupportedError as e:
            print(f"[error] {e}")
            logger.info(f"--list-tags blocked: LabelNotSupported")
            return
        print("=" * 50)
        print(f"Tags ({len(tags)})")
        print("=" * 50)
        if not tags:
            print("(no tags found)")
            return
        for tag in tags:
            print(f"  [{tag['id']:>6d}] {tag['name']}  ({tag['count']} contacts)")
        return

    if args.contact_tags:
        try:
            tags = exporter.get_contact_tags(args.contact_tags)
        except LabelNotSupportedError as e:
            print(f"[error] {e}")
            return
        print("=" * 50)
        print(f"Tags of contact: {args.contact_tags}")
        print("=" * 50)
        if not tags:
            print("(no tags found or contact has no labels)")
        else:
            for t in tags:
                print(f"  - {t}")
        return

    if args.tag:
        # Mode 1: --tag alone -> list contacts in the tag
        # Mode 2: --tag + (--recent or --search or --days or --limit) -> messages from those contacts
        try:
            tag_contacts = exporter.query_by_tag(args.tag)
        except LabelNotSupportedError as e:
            print(f"[error] {e}")
            return

        # args.recent defaults to None in v0.5.0 so we can distinguish
        # 'user ran --tag X alone' from 'user ran --tag X --recent 10'.
        wants_messages = (
            bool(args.search)
            or args.recent is not None
            or args.days is not None
            or args.limit is not None
        )

        if not tag_contacts:
            if args.tag.lower() not in getattr(exporter, 'label_name_to_id', {}):
                print(f"[info] Tag '{args.tag}' not found. Use --list-tags to see available tags.")
            else:
                print(f"[info] Tag '{args.tag}' exists but has no member contacts.")
            return

        if not wants_messages:
            print("=" * 50)
            print(f"Contacts with tag: {args.tag}  ({len(tag_contacts)})")
            print("=" * 50)
            for c in tag_contacts:
                tags_str = ', '.join(c.get('tags', [])) or '-'
                print(f"  {c['name']}  (wxid: {c['wxid'][:20]}...)  tags: [{tags_str}]")
            return

        # Mode 2: fetch messages for each member, merge, sort, limit
        all_msgs = []
        final_limit = args.limit or args.recent or 10
        limit_per = max(final_limit * 2, 20)
        for c in tag_contacts:
            msgs = exporter.query_messages(
                limit=limit_per,
                search=args.search,
                contact=c['name'],
                days=args.days,
            )
            for m in msgs:
                m['tag'] = args.tag
            all_msgs.extend(msgs)
        all_msgs.sort(key=lambda x: x['time'], reverse=True)
        all_msgs = all_msgs[:final_limit]
        print("=" * 60)
        print(f"Messages from {len(tag_contacts)} contacts with tag '{args.tag}' ({len(all_msgs)} messages)")
        print("=" * 60)
        for msg in all_msgs:
            print()
            print(format_message(msg))
        return


    if args.new_contacts:
        import hashlib
        from collections import defaultdict

        days = args.new_contacts
        threshold = time.time() - days * 86400

        if isinstance(exporter, V4QueryBase):
            # 所有 4.x（Windows4 + Mac4）都走共享的 find_new_contacts
            results = exporter.find_new_contacts(threshold)
        else:
            print("--new-contacts not supported on this platform")
            return

        results.sort()
        print("=" * 50)
        print(f"近 {days} 天新增联系人：{len(results)} 人")
        print("=" * 50)
        for _, name, dt in results:
            print(f"  {dt}  {name}")
        logger.info(f"New contacts query: days={days}, found={len(results)}")
        return

    if args.collect:
        # 采集模式：查询 → 过滤 → 格式化 → 写 CUFin JSON，一条命令搞定。
        #
        # 过滤策略（v0.7.0 起）：
        #   - 私聊：默认全收，可用 --exclude 黑名单逐个剔除
        #   - 群聊：默认【不收】，除非满足以下任一条件之一：
        #       (a) 在 --include-groups 白名单里（显式）
        #       (b) 最近 --active-group-days 天内我在群里发过言（默认 30 天）
        #     这两个集合的并集 ∩ {真实群名单(group_names)} 才是要采的群。
        #   - 其它通用过滤：跳过通话记录、空文本、卡片 XML、撤回通知。
        #
        # 用 exporter.group_names（id→名）作为权威群名单——比按消息是否带 wxid:
        # 前缀判断稳得多（外发消息没前缀，会被错判成私聊）。
        import hashlib
        after_ts = None
        if args.after:
            try:
                after_ts = datetime.strptime(args.after.strip(), '%Y-%m-%d %H:%M:%S').timestamp()
            except ValueError:
                print(f"COLLECT-ERROR: bad --after {args.after!r}, expect 'YYYY-MM-DD HH:MM:SS'")
                return
        days = args.days
        if days is None and after_ts:
            days = int((time.time() - after_ts) / 86400) + 2  # 粗界，缩小 SQL 扫描

        exclude_set = _split_csv(args.exclude)
        include_groups = _split_csv(args.include_groups)
        active_group_days = args.active_group_days if args.active_group_days is not None else 30
        # 真实群名单（@chatroom 标记）—— 用这个判定一个 chat 是不是群
        all_groups = set(exporter.group_names.values())

        # 自动白名单：最近 N 天我【真的发过实质消息】的群
        # 注意：撤回通知（"XXX 撤回了一条消息"）在 db 里 is_received=False，
        # 容易被当作"我发言"，但其实是系统消息。同 collect 输出端的过滤一致，
        # 这里也要把撤回/通话/XML/空消息排除掉，避免噪声群被误判为活跃。
        active_groups = set()
        if active_group_days and active_group_days > 0:
            recent_msgs = exporter.query_messages(limit=None, days=active_group_days)
            for m in recent_msgs:
                cn = m.get('chat_name')
                if cn not in all_groups or m.get('is_received'):
                    continue
                if _is_noise_for_owner_relevance(m):
                    continue
                active_groups.add(cn)
            logger.info(f"Active groups (last {active_group_days}d): {len(active_groups)}")

        group_whitelist = (include_groups | active_groups) - exclude_set

        messages = exporter.query_messages(limit=None, days=days)
        messages.sort(key=lambda m: m.get('time') or 0)  # 从旧到新
        private_whitelist = None
        if args.participated_only:
            private_whitelist = _detect_active_private(messages, all_groups) - exclude_set
            logger.info(f"Participated private chats: {len(private_whitelist)}")
        messages = _filter_owner_relevant_messages(messages, all_groups, exclude_set, group_whitelist, private_whitelist)
        out = []
        limit = args.limit or 0
        for m in messages:
            ts = m.get('time') or 0
            if after_ts and ts < after_ts:
                continue
            if m.get('kind') == 'call':
                continue                                  # 通话记录非文字
            content = str(m.get('message') or '').strip()
            if not content or content.startswith('<'):
                continue                                  # 空 / 图片链接卡片等 XML
            if '撤回了一条消息' in content:
                continue                                  # 撤回通知，系统消息
            chat = m.get('chat_name') or ''
            # 私聊默认放行（exclude_set 已在上面剔过）
            t_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            sender = '我' if not m.get('is_received') else (m.get('sender') or chat)
            sid = hashlib.sha1(f"{chat}|{t_str}|{sender}|{content}".encode('utf-8')).hexdigest()[:16]
            out.append({
                'id': 'wx-' + sid,
                'source': _format_collect_source(chat, chat in all_groups, t_str),
                'data': {'chat': chat, 'sender': sender, 'time': t_str, 'text': content},
            })
            if limit and len(out) >= limit:
                break
        payload = _dump_collect_payload(out, pretty=args.pretty)
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(payload)
        if args.out_dir:
            manifest = _write_collect_package(out, args.out_dir, args=args, platform=collector_platform)
            print(_json.dumps({
                'collector': 'wechat',
                'event_count': manifest['event_count'],
                'out_dir': str(Path(args.out_dir).expanduser()),
            }, ensure_ascii=False, sort_keys=True))
        elif args.out:
            print(f"COLLECTED {len(out)}")
        else:
            print(payload)
        logger.info(f"Collect: after={args.after}, limit={limit}, wrote={len(out)}, "
                    f"exclude={len(exclude_set)}, include_groups={len(include_groups)}, "
                    f"active_groups={len(active_groups)}")
        if hasattr(exporter, 'cleanup'):
            exporter.cleanup()
        return

    if args.export:
        messages = exporter.query_messages(limit=None, search=args.search, contact=args.contact, days=args.days)
        queried_count = len(messages)
        scope = 'all' if (args.raw_export or args.export_all) else 'owner-relevant'
        if scope == 'owner-relevant':
            exclude_set = _split_csv(args.exclude)
            include_groups = _split_csv(args.include_groups)
            all_groups = set(exporter.group_names.values())
            active_groups = set()
            active_group_days = (
                args.active_group_days
                if args.active_group_days is not None
                else (args.days if args.days is not None else 30)
            )
            if active_group_days and active_group_days > 0:
                recent_msgs = exporter.query_messages(limit=None, days=active_group_days)
                active_groups = _detect_active_groups(recent_msgs, all_groups)
                logger.info(f"Export active groups (last {active_group_days}d): {len(active_groups)}")
            group_whitelist = (include_groups | active_groups) - exclude_set
            messages = _filter_owner_relevant_messages(messages, all_groups, exclude_set, group_whitelist)
        logger.info(f"Export: {len(messages)} {scope} messages from {queried_count} queried to {args.export}")
        if args.raw_export:
            export_rows = [format_message(msg) for msg in reversed(messages)]
        else:
            export_rows = []
            for msg in reversed(messages):
                line = format_export_message(msg, max_chars=args.export_max_chars)
                if line:
                    export_rows.append(line)
        with open(args.export, 'w', encoding='utf-8') as f:
            f.write(f"WeChat Chat Export\n")
            f.write(f"Export time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Messages: {len(export_rows)}\n")
            if scope == 'owner-relevant':
                f.write(f"Queried messages: {queried_count}\n")
                f.write(f"Scope: owner-relevant private chats + active/included groups\n")
            else:
                f.write(f"Scope: all chats\n")
            f.write(f"Format: {'raw' if args.raw_export else 'compact-clean'}\n")
            f.write("=" * 60 + "\n\n")
            for row in export_rows:
                if args.raw_export:
                    f.write(row + "\n\n")
                else:
                    f.write(row + "\n")
        if scope == 'owner-relevant':
            print(f"Exported {len(export_rows)} owner-relevant messages from {queried_count} queried to: {args.export}")
        else:
            print(f"Exported {len(export_rows)} messages to: {args.export}")
        return

    limit = args.limit or args.recent or 10  # default 10 messages if neither --limit nor --recent given
    messages = exporter.query_messages(limit=limit, search=args.search, contact=args.contact, days=args.days)
    logger.info(f"Query: limit={limit}, search={args.search}, contact={args.contact}, days={args.days}, results={len(messages)}")

    # --contact enhancement: show tags attached to this contact (v0.5.0+)
    if args.contact:
        # If the contact name didn't match anything in the address book at all,
        # tell the caller plainly instead of leaving them to guess from "0 results".
        # (Windows path sets _last_contact_matched in _resolve_contact_to_tables.
        # Mac path doesn't have an early-exit, so we approximate: 0 messages +
        # contact specified is the same signal a caller cares about.)
        contact_unresolved = getattr(exporter, '_last_contact_matched', None) is False
        if contact_unresolved:
            print("=" * 60)
            print(f"❌ Contact '{args.contact}' not found in your address book.")
            print(f"   Tip: list contacts containing a substring with:")
            print(f"     python wechat_query.py --list-contacts --filter <部分名字>")
            print(f"   Then re-query with the exact name shown there.")
            print("=" * 60)
        else:
            try:
                tags = exporter.get_contact_tags(args.contact)
            except LabelNotSupportedError:
                tags = []
            print("=" * 60)
            if tags:
                print(f"Contact tags: {tags}")
            else:
                print(f"Contact tags: []  (no labels attached or tag data unavailable)")

    print("=" * 60)
    print(f"Results ({len(messages)} messages)")
    print("=" * 60)
    for msg in messages:
        print()
        print(format_message(msg))

    _t_total = time.time() - _t_main
    print(f"\n--- {len(messages)} messages, {_t_total:.2f}s total ---")
    logger.info(f"main() total: {_t_total:.2f}s")

    if hasattr(exporter, 'cleanup'):
        exporter.cleanup()


if __name__ == '__main__':
    _rc = 0
    try:
        main()
    except SystemExit as _e:
        _rc = _e.code if isinstance(_e.code, int) else (0 if _e.code is None else 1)
    # sqlcipher3 的 Connection 对象在解释器退出、Python 析构阶段会间歇性 double-free
    # 触发 native abort（malloc: freed twice）——这是该 C 扩展的既有 bug（拆包前
    # 就有，实测新旧版崩溃率一致）。查询结果此时已全部输出，无需优雅析构：flush 后
    # 用 os._exit 直接退出、跳过 Python 的对象析构阶段，从根上规避用户可见的崩溃。
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)

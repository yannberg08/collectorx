"""wexport.keycrypto — SQLCipher4 密钥派生 / 校验 / 数据库文件收集（Mac4 + Win4 共用）。

破解层「怎么拿 key」两平台不同（Mac 走 lldb hook，Windows 扫内存），但拿到候选
enc_key 之后的**算法是同一套**：SQLCipher4 的 HMAC 子密钥派生（salt ^ 0x3a、
pbkdf2 sha512 rounds=2）、第 1 页 HMAC-SHA512 校验、遍历 db_storage 收 .db 文件读库头。
这些以前在 wechat_extract_mac.py / wechat_extract_windows.py 各存一份（逐字重复），
现抽到这里由两个提取器共同 import。
"""
import hashlib
import hmac as hmac_mod
import os
import struct

# ── 密钥文件命名（Mac / Windows 统一为 all_keys.json）──────────────
# 一台机器只跑一个平台的提取器，不会并存；文件名统一，格式各自（Mac 是
# {db_dir, keys}，Windows 是 {rel: {enc_key, salt}}），由平台分派的 reader 各读各的。
KEYS_FILENAME = 'all_keys.json'
_LEGACY_KEYS_NAMES = ('mac_all_keys.json', 'windows_all_keys.json')


def keys_path(data_dir):
    """提取器写 key 的统一目标路径（data/all_keys.json）。"""
    return os.path.join(data_dir, KEYS_FILENAME)


def resolve_keys_file(data_dir):
    """查询侧定位已存在的 key 文件：优先统一名 all_keys.json，兼容旧的平台专名。"""
    p = os.path.join(data_dir, KEYS_FILENAME)
    if os.path.exists(p):
        return p
    for legacy in _LEGACY_KEYS_NAMES:
        lp = os.path.join(data_dir, legacy)
        if os.path.exists(lp):
            return lp
    return None


# ── SQLCipher4 常量 ────────────────────────────────────────────
PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16
IV_SZ = 16
HMAC_SZ = 64
RESERVE_SZ = 80  # IV(16) + HMAC(64)
SQLITE_HDR = b'SQLite format 3\x00'


def derive_mac_key(enc_key, salt):
    """从 enc_key + 库头 salt 派生 SQLCipher4 的 HMAC 子密钥（salt ^ 0x3a、sha512、rounds=2）。"""
    mac_salt = bytes(b ^ 0x3a for b in salt)
    return hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SZ)


def verify_key_page1(enc_key, page1):
    """用第 1 页的 HMAC-SHA512 校验 enc_key 是否属于该库（把候选 key 对回具体库）。"""
    if len(page1) < PAGE_SZ or len(enc_key) != KEY_SZ:
        return False
    salt = page1[:SALT_SZ]
    mac_key = derive_mac_key(enc_key, salt)
    p1_hmac_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    p1_stored = page1[PAGE_SZ - HMAC_SZ: PAGE_SZ]
    hm = hmac_mod.new(mac_key, p1_hmac_data, hashlib.sha512)
    hm.update(struct.pack('<I', 1))
    return hm.digest() == p1_stored


def collect_db_files(db_dir):
    """遍历 db_storage 收集所有加密 .db 文件的库头。

    返回 (db_files, salt_to_dbs)：
      db_files[rel] = {'path': 绝对路径, 'salt': salt 的 hex, 'page1': 首页 bytes（读满 4096 时才有）}
      salt_to_dbs[salt_hex] = [rel, ...]   （Windows 扫内存按 salt 反查用）

    两平台共用：Windows 只需 salt（内存里 key 带 salt 反查），Mac 需要 page1（HMAC 校验）。
    读满一页就带上 page1；salt 取头 16 字节，任一能读到 16 字节的 .db 都收。
    """
    db_files = {}
    salt_to_dbs = {}
    for root, dirs, files in os.walk(db_dir):
        # 跳过 WCDB 的 .factory 备份/修复目录（如 message_0.db.factory/<时间戳>/）：
        # 里面是活库的历史快照副本，微信启动时不打开、不派生 key，扫进来只会
        # 让密钥匹配数虚少一个（36/37），查询侧也不该去读这些陈旧副本。
        dirs[:] = [d for d in dirs if not d.endswith('.factory')]
        for f in files:
            if not f.endswith('.db') or f.endswith('-wal') or f.endswith('-shm'):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, 'rb') as fp:
                    head = fp.read(PAGE_SZ)
            except OSError:
                continue
            if len(head) < SALT_SZ:
                continue
            rel = os.path.relpath(path, db_dir)
            salt = head[:SALT_SZ]
            entry = {'path': path, 'salt': salt.hex()}
            if len(head) == PAGE_SZ:
                entry['page1'] = head
            db_files[rel] = entry
            salt_to_dbs.setdefault(salt.hex(), []).append(rel)
    return db_files, salt_to_dbs


# ── SQLCipher4 解密（AES-256-CBC 逐页；三平台共用）──────────────
# 从 wechat_extract_windows.py 抽出，纯算法、无平台依赖。AES 延迟 import
# （pycryptodome），让不解密的调用方（如仅提取 key）无需装 Crypto 也能 import 本模块。
def decrypt_page(enc_key, page_data, pgno):
    """解密单个数据库页（4096 字节）。第 1 页前 16 字节是明文 salt，换回 SQLite 文件头。"""
    from Crypto.Cipher import AES
    iv = page_data[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    if pgno == 1:
        encrypted = page_data[SALT_SZ: PAGE_SZ - RESERVE_SZ]
        decrypted = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(encrypted)
        return bytes(SQLITE_HDR + decrypted + b'\x00' * RESERVE_SZ)
    encrypted = page_data[:PAGE_SZ - RESERVE_SZ]
    decrypted = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(encrypted)
    return decrypted + b'\x00' * RESERVE_SZ


def decrypt_database(db_path, out_path, enc_key_hex):
    """解密整个 SQLCipher4 库到明文 sqlite 文件。先用第 1 页 HMAC 校验 key，再逐页解。"""
    enc_key = bytes.fromhex(enc_key_hex)
    file_size = os.path.getsize(db_path)
    if file_size == 0 or file_size % PAGE_SZ != 0:
        return False, "文件大小不是页大小的整数倍"
    total_pages = file_size // PAGE_SZ
    with open(db_path, 'rb') as f:
        page1 = f.read(PAGE_SZ)
    if not verify_key_page1(enc_key, page1):
        return False, "HMAC 验证失败（密钥不匹配）"
    out_parent = os.path.dirname(out_path)
    if out_parent:
        os.makedirs(out_parent, exist_ok=True)
    with open(db_path, 'rb') as fin, open(out_path, 'wb') as fout:
        for pgno in range(1, total_pages + 1):
            page = fin.read(PAGE_SZ)
            if len(page) < PAGE_SZ:
                break
            fout.write(decrypt_page(enc_key, page, pgno))
    return True, f"{total_pages} pages"


__all__ = [
    'PAGE_SZ', 'KEY_SZ', 'SALT_SZ', 'IV_SZ', 'HMAC_SZ', 'RESERVE_SZ', 'SQLITE_HDR',
    'KEYS_FILENAME', 'keys_path', 'resolve_keys_file',
    'derive_mac_key', 'verify_key_page1', 'collect_db_files',
    'decrypt_page', 'decrypt_database',
]

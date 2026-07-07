"""
Windows WeChat 4.x database key extraction and decryption.

Usage:
  python wechat_extract_windows.py              # Auto: scan WeChat process memory for keys
  python wechat_extract_windows.py --key HEX    # Manually provide a raw hex key (advanced)
  python wechat_extract_windows.py --keys-only  # Only extract keys, skip decryption

If key scanning only recovers some of the 17 DB keys on your WeChat version,
it's a known gap in the current scan algorithm (not a user-side issue).
Please send the log to Kevin; do NOT use third-party key-dump tools.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# SQLCipher4 常量 + 派生/校验/收库：与 Mac 提取器共用（wexport.keycrypto）。
from wexport.keycrypto import (  # noqa: E402
    PAGE_SZ, SALT_SZ, IV_SZ, RESERVE_SZ, SQLITE_HDR,
    collect_db_files, verify_key_page1, keys_path, resolve_keys_file,
)
# db_storage 目录发现：与查询侧共用（wexport.detect）。
from wexport.detect import _auto_find_windows_db_dir as auto_find_db_dir  # noqa: E402

# ── 日志配置 ────────────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, 'wechat_export.log')

logger = logging.getLogger('wechat')
logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler(_log_file, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_fh)

# SQLCipher4 常量见 wexport.keycrypto（已在文件顶部 import）。
kernel32 = ctypes.windll.kernel32
MEM_COMMIT = 0x1000
READABLE_PROTECT = {0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80}


# ── Windows API 结构体 ────────────────────────────────────────
class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wt.DWORD),
        ("_pad1", wt.DWORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
        ("_pad2", wt.DWORD),
    ]


# ── 进程查找 ──────────────────────────────────────────────────
def get_wechat_pids():
    """获取 Weixin.exe 进程列表，按内存占用降序"""
    r = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True
    )
    pids = []
    for line in r.stdout.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.strip('"').split('","')
        if len(parts) >= 5:
            pid = int(parts[1])
            mem_str = parts[4].replace(',', '').replace(' K', '').strip()
            mem = int(mem_str) if mem_str else 0
            pids.append((pid, mem))
    pids.sort(key=lambda x: x[1], reverse=True)
    return pids


# ── 版本检测 ──────────────────────────────────────────────────
def get_wechat_version():
    """获取微信版本号（从 Weixin.exe 文件版本信息）"""
    try:
        r = subprocess.run(
            ['powershell', '-Command',
             '$p = (Get-Process Weixin -EA 0).Path;'
             'if($p){(Get-Item $p).VersionInfo.FileVersion}'],
            capture_output=True, text=True, timeout=10
        )
        v = r.stdout.strip().split('\n')[0].strip()
        if v and v[0].isdigit():
            return v
    except Exception:
        pass
    return None


def check_version_compatibility(version_str):
    """记录微信版本号，不做兼容性前置判断。

    内存扫描在所有 WeChat 4.x 版本上都会尝试；扫描命中率随版本浮动，
    但永远先跑再看结果，不依据版本号提前放弃（避免给用户"你版本不兼容"的误判）。
    """
    return True, (version_str or "unknown")


# ── 内存读取 ──────────────────────────────────────────────────
def read_process_memory(handle, addr, size):
    """读取进程内存"""
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(handle, ctypes.c_uint64(addr), buf, size, ctypes.byref(n)):
        return buf.raw[:n.value]
    return None


def enum_memory_regions(handle):
    """枚举进程中已提交且可读的内存区域"""
    regions = []
    addr = 0
    mbi = MBI()
    while addr < 0x7FFFFFFFFFFF:
        if kernel32.VirtualQueryEx(handle, ctypes.c_uint64(addr),
                                   ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        if (mbi.State == MEM_COMMIT
                and mbi.Protect in READABLE_PROTECT
                and 0 < mbi.RegionSize < 500 * 1024 * 1024):
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return regions


# ── 密钥扫描 ──────────────────────────────────────────────────
def scan_for_keys(handle, regions, salt_to_dbs):
    """扫描进程内存，匹配 x'<96hex>' 格式的密钥"""
    hex_re = re.compile(b"x'([0-9a-fA-F]{96})'")
    key_map = {}
    found_salts = set()

    for base, size in regions:
        data = read_process_memory(handle, base, size)
        if not data:
            continue
        for m in hex_re.finditer(data):
            full_hex = m.group(1).decode('ascii')
            enc_key_hex = full_hex[:64]   # 32 bytes
            salt_hex = full_hex[64:]      # 16 bytes

            if salt_hex in salt_to_dbs:
                for db_rel in salt_to_dbs[salt_hex]:
                    key_map[db_rel] = {'enc_key': enc_key_hex, 'salt': salt_hex}
                    found_salts.add(salt_hex)

    return key_map, found_salts


# ── 解密逻辑 ──────────────────────────────────────────────────

def decrypt_page(enc_key, page_data, pgno):
    """解密单个数据库页（4096 字节）"""
    iv = page_data[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    from Crypto.Cipher import AES

    if pgno == 1:
        # 第1页：前16字节是 salt（不是加密数据），替换为 SQLite 文件头
        encrypted = page_data[SALT_SZ: PAGE_SZ - RESERVE_SZ]
        cipher = AES.new(enc_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted)
        page = bytearray(SQLITE_HDR + decrypted + b'\x00' * RESERVE_SZ)
        return bytes(page)
    else:
        encrypted = page_data[:PAGE_SZ - RESERVE_SZ]
        cipher = AES.new(enc_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted)
        return decrypted + b'\x00' * RESERVE_SZ


def decrypt_database(db_path, out_path, enc_key_hex):
    """解密单个数据库文件"""
    from Crypto.Cipher import AES

    enc_key = bytes.fromhex(enc_key_hex)
    file_size = os.path.getsize(db_path)
    if file_size == 0 or file_size % PAGE_SZ != 0:
        return False, "文件大小不是页大小的整数倍"
    total_pages = file_size // PAGE_SZ

    with open(db_path, 'rb') as f:
        page1 = f.read(PAGE_SZ)

    # 第 1 页 HMAC-SHA512 校验密钥（与 Mac 提取器同一实现，wexport.keycrypto）。
    if not verify_key_page1(enc_key, page1):
        return False, "HMAC 验证失败（密钥不匹配）"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(db_path, 'rb') as fin, open(out_path, 'wb') as fout:
        for pgno in range(1, total_pages + 1):
            page = fin.read(PAGE_SZ)
            if len(page) < PAGE_SZ:
                break
            fout.write(decrypt_page(enc_key, page, pgno))

    return True, f"{total_pages} pages"


# ── 主流程 ────────────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("wechat_extract_windows.py started")

    # Force UTF-8 output on Windows (PowerShell/cmd default is GBK)
    if sys.platform in ('win32', 'cygwin'):
        for stream in [sys.stdout, sys.stderr]:
            if stream and hasattr(stream, 'reconfigure'):
                try:
                    stream.reconfigure(encoding='utf-8')
                except Exception:
                    stream.reconfigure(errors='replace')

    parser = argparse.ArgumentParser(
        description='Windows 微信 4.x 数据库密钥提取 + 解密',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python wechat_extract_windows.py
  python wechat_extract_windows.py --db-dir "C:\\Users\\My\\xwechat_files\\wxid_xxx\\db_storage"
  python wechat_extract_windows.py --out-dir "D:\\decrypted"
  python wechat_extract_windows.py --keys-only
        """
    )
    parser.add_argument('--db-dir', help='微信 db_storage 目录路径（不指定则自动查找）')
    parser.add_argument('--out-dir', help='解密输出目录（默认: 脚本同目录下的 decrypted）')
    parser.add_argument('--keys-only', action='store_true', help='仅提取密钥，不解密数据库')
    args = parser.parse_args()

    print("=" * 60)
    print("  WeChat 4.x database key extraction + decryption")
    print("=" * 60)

    # ── 0. 记录微信版本（不做前置兼容判断，总是尝试扫描） ──
    version = get_wechat_version()
    if version:
        print(f"\nWeChat version: {version}")
        logger.info(f"WeChat version: {version}")
    else:
        print("\nWeChat version: unknown")
    print("  -> Running memory scan...")

    # ── 1. 检查是否已有密钥 ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    keys_file = resolve_keys_file(data_dir)   # all_keys.json，兼容旧 windows_all_keys.json
    if keys_file and os.path.exists(keys_file):
        with open(keys_file, 'r', encoding='utf-8') as f:
            existing_keys = json.load(f)
        if existing_keys:
            print(f"\nKeys already exist: {keys_file} ({len(existing_keys)} keys)")
            print("Skip extraction. Use wechat_query.py to query directly.")
            logger.info(f"Keys file already exists with {len(existing_keys)} keys, skipping extraction")
            return

    # ── 2. 定位数据库目录 ──
    db_dir = args.db_dir
    if not db_dir:
        db_dir = auto_find_db_dir()
        if not db_dir:
            print("\n[ERROR] db directory not found!")
            print("Usage: --db-dir C:\\Users\\<user>\\xwechat_files\\<wxid>\\db_storage")
            sys.exit(1)
    print(f"\nDB dir: {db_dir}")
    logger.info(f"DB dir: {db_dir}")

    # ── 3. 收集 .db 文件 ──
    db_files, salt_to_dbs = collect_db_files(db_dir)
    if not db_files:
        print("\n[ERROR] No .db files found!")
        logger.error("No .db files found in db_dir")
        sys.exit(1)
    print(f"Found {len(db_files)} databases, {len(salt_to_dbs)} unique salts")
    logger.info(f"Collected {len(db_files)} db files, {len(salt_to_dbs)} unique salts")

    # ── 4. 扫描进程内存获取密钥 ──
    key_map = {}

    pids = get_wechat_pids()
    if not pids:
        print("\n[ERROR] Weixin.exe not found!")
        print("Please login to WeChat first.")
        logger.error("Weixin.exe process not found")
        sys.exit(1)
    print(f"Found {len(pids)} Weixin.exe processes")
    for pid, mem in pids:
        print(f"  PID={pid} ({mem // 1024}MB)")

    for pid, _ in pids:
        PROCESS_VM_READ = 0x0010
        PROCESS_QUERY_INFORMATION = 0x0400
        h = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not h:
            print(f"  [WARN] Cannot open PID={pid} (need admin)")
            continue

        print(f"\nScanning PID={pid} memory...")
        regions = enum_memory_regions(h)
        print(f"  {len(regions)} memory regions")

        found, salts = scan_for_keys(h, regions, salt_to_dbs)
        key_map.update(found)
        print(f"  Found {len(found)} keys (matched {len(salts)} salts)")
        logger.info(f"PID={pid}: scanned {len(regions)} regions, found {len(found)} keys, {len(salts)} matched salts")

        kernel32.CloseHandle(h)

    if not key_map:
        print("\n[ERROR] No keys found via memory scan!")
        print("Ensure WeChat is logged in and running, then try again.")
        logger.error("Memory scan found 0 keys across all PIDs")
        sys.exit(1)

    print(f"\nTotal: {len(key_map)} database keys")
    logger.info(f"Total key_map: {len(key_map)} keys for {len(set(k.split(os.sep)[0] for k in key_map))} db categories")

    # ── 5. 保存密钥到持久化目录（SKILL/data/）──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    keys_file = keys_path(data_dir)   # data/all_keys.json（Mac/Windows 统一命名）
    with open(keys_file, 'w', encoding='utf-8') as f:
        json.dump(key_map, f, indent=2, ensure_ascii=False)
    print(f"密钥已保存到: {keys_file}")
    logger.info(f"Keys saved to {keys_file} ({len(key_map)} entries)")

    if args.keys_only or not args.out_dir:
        print("\n密钥提取完成。查询时 wechat_query.py 会自动解密，无需手动处理。")
        return

    # ── 6. 解密所有数据库（仅在用户显式指定 --out-dir 时执行）──
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n开始解密到: {out_dir}")
    success = 0
    for rel, info in sorted(key_map.items()):
        db_path = db_files[rel]['path']
        out_path = os.path.join(out_dir, rel)

        size_kb = os.path.getsize(db_path) / 1024
        print(f"  解密: {rel} ({size_kb:.0f}KB) ... ", end="", flush=True)
        ok, msg = decrypt_database(db_path, out_path, info['enc_key'])

        if ok:
            import sqlite3
            try:
                conn = sqlite3.connect(out_path)
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                table_names = [t[0] for t in tables[:5]]
                if len(tables) > 5:
                    table_names.append(f"...共{len(tables)}个")
                print(f"OK! 表: {table_names}")
                conn.close()
            except Exception as e:
                print(f"OK (但读取表失败: {e})")
            success += 1
            logger.debug(f"Decrypted OK: {rel} ({msg})")
        else:
            print(f"FAIL: {msg}")
            logger.warning(f"Decrypted FAIL: {rel} - {msg}")

    print(f"\n完成! {success}/{len(key_map)} 个解密成功")
    print(f"解密文件在: {out_dir}")
    logger.info(f"Decryption done: {success}/{len(key_map)} success, output: {out_dir}")

    if success > 0:
        print(f"\n可使用 sqlite3 或 DB Browser for SQLite 查看解密后的 .db 文件")


if __name__ == '__main__':
    main()

"""
Linux WeChat 4.x database key extraction and decryption.

在【运行中的】Linux 原生微信（/opt/wechat/wechat，微信 4.x，SQLCipher4）上，
从进程内存 /proc/<pid>/mem 里扫出每个库的 enc_key，把候选 key 用「库第 1 页
HMAC-SHA512」对回具体库，产出 data/all_keys.json（{相对路径: {enc_key, salt}}，
与 Windows 提取器同构），供 wechat_query.py --db-dir 走 WindowsV4Query 路径解密查询。

原理与 Windows 同：WCDB 在进程内存里缓存派生后的 raw key，形态为
  x'<64hex enc_key><32hex salt>'
本脚本正是 regex 扫这个明文串，再按 salt 反查是哪个库。若某版本微信内存不留此
明文（如 Mac 4.1.11 已不留），regex 会扫不到 —— 那是版本差异，请把日志发 Kevin，
不要用第三方 dump 工具。

用法（需 root / CAP_SYS_PTRACE 才能读 /proc/<pid>/mem）：
  sudo python3 wechat_extract_linux.py                 # 自动：找微信进程 + db_storage，扫 key
  sudo python3 wechat_extract_linux.py --keys-only     # 只提取 key，不解密
  sudo python3 wechat_extract_linux.py --out-dir /tmp/dec   # 顺便把库解密到目录（自检用）
  sudo python3 wechat_extract_linux.py --db-dir <db_storage 绝对路径>   # 手动指定库目录
"""
import argparse
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# SQLCipher4 常量 + 派生/校验/收库/解密：与 Mac / Windows 提取器共用（wexport.keycrypto）。
from wexport.keycrypto import (  # noqa: E402
    collect_db_files, verify_key_page1, decrypt_database,
    keys_path, resolve_keys_file,
)
# db_storage 目录发现：与查询侧共用（wexport.detect）。
from wexport.detect import _auto_find_linux_db_dir as auto_find_db_dir  # noqa: E402

# ── 日志 ────────────────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_log_dir, exist_ok=True)
logger = logging.getLogger('wechat')
logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler(os.path.join(_log_dir, 'wechat_export.log'), encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_fh)

# 微信主进程可执行路径（key 缓存在这个进程里，不是 WeChatAppEx 小程序容器）。
WECHAT_EXE = '/opt/wechat/wechat'
# 单块内存区域读取上限，跳过超大映射（与 Windows 提取器口径一致）。
MAX_REGION = 500 * 1024 * 1024
# 内存里 key 的明文形态：x'<64hex enc_key><32hex salt>'
KEY_RE = re.compile(rb"x'([0-9a-fA-F]{96})'")


def find_wechat_pids():
    """扫 /proc 找微信主进程 pid（exe 指向 /opt/wechat/wechat），按 RSS 降序。"""
    pids = []
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            exe = os.readlink(f'/proc/{pid}/exe')
        except OSError:
            continue
        # 主进程 exe == /opt/wechat/wechat；排除 RadiumWMPF/runtime/WeChatAppEx 等子进程。
        if exe != WECHAT_EXE:
            continue
        rss = 0
        try:
            with open(f'/proc/{pid}/statm') as f:
                rss = int(f.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, IndexError):
            pass
        pids.append((pid, rss))
    pids.sort(key=lambda x: x[1], reverse=True)
    return pids


def iter_readable_regions(pid):
    """解析 /proc/<pid>/maps，产出可读区域 (start, end)。跳过特殊区与超大映射。"""
    with open(f'/proc/{pid}/maps') as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            addr, perms = parts[0], parts[1]
            if 'r' not in perms:
                continue
            path = parts[5] if len(parts) >= 6 else ''
            if path in ('[vvar]', '[vsyscall]', '[vdso]'):
                continue
            try:
                start_s, end_s = addr.split('-')
                start, end = int(start_s, 16), int(end_s, 16)
            except ValueError:
                continue
            if 0 < end - start <= MAX_REGION:
                yield start, end


def scan_pid_for_keys(pid, salt_to_dbs):
    """扫描一个进程的内存，regex 匹配 x'<96hex>' 密钥并按 salt 反查是哪个库。"""
    key_map = {}
    found_salts = set()
    try:
        mem = open(f'/proc/{pid}/mem', 'rb', 0)
    except OSError as e:
        print(f"  [WARN] 打不开 /proc/{pid}/mem（需 root）: {e}")
        logger.warning(f"open /proc/{pid}/mem failed: {e}")
        return key_map, found_salts
    regions = 0
    with mem:
        for start, end in iter_readable_regions(pid):
            try:
                mem.seek(start)
                data = mem.read(end - start)
            except (OSError, OverflowError, ValueError):
                continue  # 未映射 gap / 读权限问题，跳过
            if not data:
                continue
            regions += 1
            for m in KEY_RE.finditer(data):
                full = m.group(1).decode('ascii')
                enc_key_hex, salt_hex = full[:64], full[64:]
                for db_rel in salt_to_dbs.get(salt_hex, ()):
                    key_map[db_rel] = {'enc_key': enc_key_hex, 'salt': salt_hex}
                    found_salts.add(salt_hex)
    logger.info(f"PID={pid}: scanned {regions} regions, {len(key_map)} keys, {len(found_salts)} salts")
    print(f"  扫描 {regions} 个可读内存区，命中 {len(key_map)} 个库 key（{len(found_salts)} 个 salt）")
    return key_map, found_salts


def main():
    parser = argparse.ArgumentParser(
        description='Linux 微信 4.x 数据库密钥提取 + 解密',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--db-dir', help='微信 db_storage 目录（不指定则自动查找）')
    parser.add_argument('--out-dir', help='把库解密到该目录（自检用；不给则只提取 key）')
    parser.add_argument('--keys-only', action='store_true', help='仅提取密钥，不解密')
    parser.add_argument('--pid', type=int, help='手动指定微信进程 pid')
    args = parser.parse_args()

    print("=" * 60)
    print("  Linux WeChat 4.x 数据库密钥提取 + 解密")
    print("=" * 60)

    if os.geteuid() != 0:
        print("\n[ERROR] 需要 root（读 /proc/<pid>/mem）。请用 sudo 重跑。")
        sys.exit(2)

    # ── 1. 定位 db_storage ──
    db_dir = args.db_dir or auto_find_db_dir()
    if not db_dir:
        print("\n[ERROR] 找不到 db_storage 目录。请用 --db-dir 指定，"
              "形如 ~/xwechat_files/<wxid>/db_storage")
        sys.exit(1)
    print(f"\nDB 目录: {db_dir}")
    logger.info(f"[linux] db_dir={db_dir}")

    # ── 2. 收集 .db 库头（salt 反查表）──
    db_files, salt_to_dbs = collect_db_files(db_dir)
    if not db_files:
        print("\n[ERROR] db_storage 里没有 .db 文件")
        sys.exit(1)
    print(f"发现 {len(db_files)} 个库，{len(salt_to_dbs)} 个不同 salt")

    # ── 3. 找微信进程 ──
    if args.pid:
        pids = [(args.pid, 0)]
    else:
        pids = find_wechat_pids()
    if not pids:
        print(f"\n[ERROR] 没找到微信主进程（exe={WECHAT_EXE}）。请先登录微信再重试。")
        sys.exit(1)
    print(f"微信进程: {', '.join(f'PID={p}' for p, _ in pids)}")

    # ── 4. 扫内存提取 key ──
    key_map = {}
    for pid, _ in pids:
        print(f"\n扫描 PID={pid} …")
        found, _salts = scan_pid_for_keys(pid, salt_to_dbs)
        key_map.update(found)

    if not key_map:
        print("\n[ERROR] 内存里没扫到 key。确认微信已登录且在运行；"
              "若确实在运行仍扫不到，可能是该微信版本内存不留明文 key，请把 logs/wechat_export.log 发 Kevin。")
        sys.exit(1)
    print(f"\n共提取 {len(key_map)}/{len(db_files)} 个库的 key")

    # ── 5. 保存 all_keys.json（与 Windows 同构，供 query --db-dir 直接用）──
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    kf = keys_path(data_dir)
    with open(kf, 'w', encoding='utf-8') as f:
        json.dump(key_map, f, indent=2, ensure_ascii=False)
    os.chmod(kf, 0o600)
    print(f"密钥已保存: {kf}")
    logger.info(f"[linux] keys saved to {kf}: {len(key_map)} entries")

    if args.keys_only or not args.out_dir:
        print("\n完成。查询用: python3 wechat_query.py --db-dir "
              f"'{db_dir}' --recent 10")
        return

    # ── 6.（可选）解密自检 ──
    out_dir = args.out_dir
    ok = 0
    for rel, info in sorted(key_map.items()):
        src = db_files[rel]['path']
        dst = os.path.join(out_dir, rel)
        success, msg = decrypt_database(src, dst, info['enc_key'])
        print(f"  解密 {rel}: {'OK ' + msg if success else 'FAIL ' + msg}")
        ok += 1 if success else 0
    print(f"\n完成 {ok}/{len(key_map)} 个库解密 → {out_dir}")


if __name__ == '__main__':
    main()

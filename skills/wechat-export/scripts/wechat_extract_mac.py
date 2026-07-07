"""
Mac WeChat 4.x database key extraction — lldb hook CCKeyDerivationPBKDF.

与 wechat_extract_windows.py 是同一目标（每库一把 enc_key），但取 key 的手段
按操作系统不同：
  - Windows：扫进程内存里的 x'<96hex>' 定值（key 以 ASCII 缓存在堆上）。
  - Mac 4.x：**内存里扫不到**——新版微信 WCDB 不把 key/salt 以明文串留在堆里
    （实测库头 salt 在内存出现 0 次）。正解是 hook 系统派生函数
    `CCKeyDerivationPBKDF`（CommonCrypto），在微信打开每个库、派生 SQLCipher HMAC
    子密钥的那一刻把 key 截下来。

原理：SQLCipher4 每打开一个库要做两次 PBKDF2：
  ① 主密钥派生（rounds=256000，password=用户口令）——WCDB 已缓存 enc_key，通常不再走这条；
  ② HMAC 子密钥派生（rounds=2，password = 该库的 32 字节 enc_key，salt = 库头salt ^ 0x3a）。
我们要的正是 ②：命中 rounds==2 的调用，其 password 参数就是该库的 enc_key。
拿到一批 enc_key 后，用「每个库第 1 页的 HMAC-SHA512 校验」把 key 对回具体的库。

前置条件（macOS 读 hardened 进程内存的硬门槛，和 3.x hook sqlite3_key 一样）：
  1. SIP 必须关闭（csrutil status 显示 disabled）。微信是 hardened runtime。
  2. 需要 root：`sudo python3 wechat_extract_mac.py`（lldb 附加加固进程要 root）。
  3. 微信已安装、能启动、已登录（key 在启动打开库时才派生）。

会短暂重启一次微信（优雅退出→重开），以便在启动派生密钥那一刻挂上 hook。
提取到的 key 存 data/all_keys.json（{相对路径: enc_key_hex}，chmod 600），
之后 wechat_query.py 自动读取，日常查询不再需要 sudo。

用法：
  sudo python3 wechat_extract_mac.py
  sudo python3 wechat_extract_mac.py --db-dir <db_storage>   # 手动指定数据目录
  sudo python3 wechat_extract_mac.py --timeout 45            # 抓取窗口秒数
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# SQLCipher4 常量 + 派生/校验/收库：与 Windows 提取器共用（wexport.keycrypto）。
from wexport.keycrypto import (  # noqa: E402
    collect_db_files, verify_key_page1, keys_path, SQLITE_HDR,
)
# db_storage 目录发现：与查询侧共用（wexport.detect）。
from wexport.detect import _find_mac4_db_storage as find_mac4_db_storage  # noqa: E402

# 每次抓取的临时产物（lldb hook 脚本 + 命中 dump）。
_HOOK_PY = "/tmp/wx_kd_hook.py"
_DRIVER = "/tmp/wx_kd_driver.txt"
_DUMP = "/tmp/wx_kd_dump.txt"
_LLDB_OUT = "/tmp/wx_kd_lldb.out"
_HITS = "/tmp/wx_kd_hits.txt"      # 每次断点命中的 rounds/pwl（判断函数到底被调没）
_DIAG = "/tmp/wx_kd_diag.txt"      # 人读的综合诊断（系统/微信版本/符号/命中/结果），成败都写


def wechat_pid():
    for name in ("WeChat", "Weixin"):
        r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
        pids = r.stdout.split()
        if pids:
            return pids[0], name
    return None, None


# ── lldb hook 脚本（在 lldb 内置 python 里跑）────────────────────
_HOOK_SRC = r'''
import lldb

def _read(proc, addr, n):
    err = lldb.SBError()
    b = proc.ReadMemory(addr, n, err)
    return b if err.Success() else None

def on_break(frame, bp_loc, internal_dict):
    # int CCKeyDerivationPBKDF(algorithm, password, passwordLen, salt, saltLen,
    #                          prf, rounds, derivedKey, derivedLen)
    # arm64 入参：x0..x8
    proc = frame.GetThread().GetProcess()
    regs = {r.GetName(): r.GetValueAsUnsigned() for r in frame.GetRegisters()[0]}
    pw, pwl = regs.get('x1'), regs.get('x2')
    rounds = regs.get('x6')
    # 诊断：记录每一次命中的 rounds/pwl —— 失败时用来判断到底是
    # 「函数一次没被调」(hits 文件为空/不存在) 还是「调了但参数不是我们要的」。
    try:
        with open("%HITS%", "a") as f:
            f.write("rounds=%s pwl=%s\n" % (rounds, pwl))
    except Exception:
        pass
    # 只要 rounds==2 的 HMAC 子密钥派生：其 password 就是该库的 enc_key(32B)
    if rounds == 2 and pw and pwl == 32:
        d = _read(proc, pw, 32)
        if d:
            with open("%DUMP%", "a") as f:
                f.write("enc_key=" + d.hex() + "\n")
    return False  # 自动 continue
''' .replace("%DUMP%", _DUMP).replace("%HITS%", _HITS)


def run_lldb_capture(pid_hint_name, timeout):
    """挂 lldb --waitfor 到微信，hook CCKeyDerivationPBKDF，抓 timeout 秒。"""
    for p in (_HOOK_PY, _DRIVER, _DUMP, _LLDB_OUT, _HITS):
        try:
            os.remove(p)
        except OSError:
            pass
    with open(_HOOK_PY, "w") as f:
        f.write(_HOOK_SRC)
    driver = (
        f"command script import {_HOOK_PY}\n"
        f"process attach --waitfor --name {pid_hint_name}\n"
        f"br set -n CCKeyDerivationPBKDF\n"
        f"breakpoint command add -F wx_kd_hook.on_break 1\n"
        f"continue\n"
    )
    with open(_DRIVER, "w") as f:
        f.write(driver)

    out = open(_LLDB_OUT, "w")
    proc = subprocess.Popen(["lldb", "--batch", "-s", _DRIVER],
                            stdout=out, stderr=subprocess.STDOUT)
    try:
        # 给 lldb 3 秒挂上 waitfor，再优雅重启微信触发启动派生。
        time.sleep(3)
        restart_wechat()
        # 轮询 dump：命中稳定（4 秒无新增）或到 timeout 就收。
        deadline = time.time() + timeout
        last_size, stable_since = -1, None
        while time.time() < deadline:
            time.sleep(1)
            sz = os.path.getsize(_DUMP) if os.path.exists(_DUMP) else 0
            if sz != last_size:
                last_size, stable_since = sz, time.time()
            elif sz > 0 and stable_since and time.time() - stable_since >= 4:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        out.close()


def restart_wechat():
    """优雅退出并重开微信，让 lldb 在启动打开库时挂上 hook。"""
    subprocess.run(["osascript", "-e", 'tell application "WeChat" to quit'],
                   capture_output=True, text=True)
    time.sleep(1)
    subprocess.run(["pkill", "-x", "WeChat"], capture_output=True)  # SIGTERM 兜底
    subprocess.run(["pkill", "-x", "Weixin"], capture_output=True)
    time.sleep(2)
    subprocess.run(["open", "-a", "WeChat"], capture_output=True)


def parse_dump():
    cands = set()
    if not os.path.exists(_DUMP):
        return cands
    for line in open(_DUMP):
        m = re.search(r'enc_key=([0-9a-f]{64})', line)
        if m:
            cands.add(m.group(1))
    return cands


def _sh(cmd):
    """跑个短命令取 stdout，失败不抛（诊断用，缺一条不该让整体挂）。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (r.stdout or r.stderr or "").strip()
    except Exception as e:
        return f"(取值失败: {e})"


def _plist(key):
    return _sh(["defaults", "read",
                "/Applications/WeChat.app/Contents/Info.plist", key])


def _mtime(path):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))
    except OSError:
        return "(读不到)"


def _cckdf_present():
    """本机 libSystem 里能否解析到 CCKeyDerivationPBKDF —— 排除「函数没了/系统库不一样」。
    能解析=系统侧没问题，抓不到就是微信 App 不调它；解析不了才怀疑系统。"""
    try:
        import ctypes
        ctypes.CDLL(None).CCKeyDerivationPBKDF
        return "存在（本系统可解析，排除'函数没了'）"
    except Exception as e:
        return f"解析失败: {e} ← 若如此，怀疑系统/库层"


def write_diagnostics(db_dir, db_files, cands=None, matched=None, note=None):
    """把系统 / 微信版本 / 符号 / 断点命中 / 抓取结果全写进 _DIAG（人读，成败都写）。

    两台机器对比这一个文件就能定位差异：微信构建号、来源、二进制构建日、
    macOS 版本、CCKeyDerivationPBKDF 是否可解析、断点命中次数与 rounds 分布。
    """
    import platform
    app = "/Applications/WeChat.app"
    L = []
    L.append("==================== 灵镜 · 微信密钥提取诊断 ====================")
    L.append("生成时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    L.append("\n[系统]")
    L.append("macOS: %s (%s)" % (_sh(["sw_vers", "-productVersion"]),
                                 _sh(["sw_vers", "-buildVersion"])))
    L.append("Darwin: " + platform.release())
    L.append("机型: " + _sh(["sysctl", "-n", "hw.model"]))
    L.append("芯片: " + _sh(["sysctl", "-n", "machdep.cpu.brand_string"]))
    L.append("SIP: " + _sh(["csrutil", "status"]))
    L.append("CCKeyDerivationPBKDF 符号: " + _cckdf_present())

    L.append("\n[微信 App]")
    L.append("路径存在: " + str(os.path.exists(app)))
    L.append("版本 (CFBundleShortVersionString): " + _plist("CFBundleShortVersionString"))
    L.append("构建 (CFBundleVersion): " + _plist("CFBundleVersion"))
    receipt = os.path.join(app, "Contents/_MASReceipt/receipt")
    L.append("来源: " + ("App Store（有 _MASReceipt）" if os.path.exists(receipt)
                        else "非 App Store（无 receipt，官网 pkg?）"))
    L.append("App bundle 修改时间(≈安装/重装时刻): " + _mtime(app))
    L.append("二进制构建时间(≈该构建出厂日): " + _mtime(os.path.join(app, "Contents/MacOS/WeChat")))
    _p, _n = wechat_pid()
    L.append("当前进程: " + (f"{_n} (pid {_p})" if _n else "未运行"))

    L.append("\n[数据]")
    L.append("db_dir: " + str(db_dir))
    L.append("加密库文件数: " + str(len(db_files) if db_files else 0))

    L.append("\n[提取环境]")
    L.append("lldb: " + _sh(["lldb", "--version"]))
    L.append("python: " + sys.version.split()[0])
    L.append("root(euid==0): " + str(os.geteuid() == 0))

    L.append("\n[抓取结果]")
    if cands is None:
        L.append("(未进入抓取阶段)")
    else:
        L.append("截获 enc_key 候选: " + str(len(cands)))
        if os.path.exists(_HITS):
            hits = [x for x in open(_HITS).read().splitlines() if x.strip()]
            L.append("断点命中总次数: " + str(len(hits)))
            from collections import Counter
            for k, v in Counter(hits).most_common(12):
                L.append("  %s  ×%d" % (k, v))
            if not any("rounds=2 " in h and "pwl=32" in h for h in hits):
                L.append("  ⚠ 有命中但没有 rounds=2/pwl=32 → 该构建的派生参数变了")
        else:
            L.append("断点命中总次数: 0")
            L.append("  ⚠ 关键：函数一次都没被调用。要么微信这个构建不走系统 "
                     "CCKeyDerivationPBKDF（换了加密后端），要么断点没绑上/没进主界面。")
        if matched is not None and db_files:
            L.append("HMAC 校验通过: %d/%d" % (len(matched), len(db_files)))

    if note:
        L.append("\n[备注]")
        L.append(note)

    L.append("\n（把本文件发给 @Kevin 对比：两台差异一眼可见——微信构建号 / 来源 / "
             "二进制构建日 / macOS 版本 / 符号是否可解析 / 断点命中次数。）")
    text = "\n".join(L)
    try:
        with open(_DIAG, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    return text


def _chown_back_to_invoker(path):
    """sudo 运行时把 path（含其下全部内容）的属主改回发起 sudo 的真实用户。

    本脚本必须 sudo 跑（lldb 附加 hardened runtime 进程要 root），进程 euid=0，
    新写的文件属主就成了 root——之后普通用户改不动，连 skill 自己的
    SKILL.md / 测试 / data 目录都写不了（本次就踩了这道墙）。这里读
    SUDO_UID / SUDO_GID 递归 chown 回真实用户，避免留下 root 属主文件。
    非 sudo（euid!=0）或拿不到 SUDO_UID 时静默跳过。
    """
    if os.geteuid() != 0:
        return
    uid = os.environ.get('SUDO_UID')
    if not uid:
        return
    uid = int(uid)
    gid = int(os.environ.get('SUDO_GID') or -1)
    try:
        os.chown(path, uid, gid)
        for root, dirs, files in os.walk(path):
            for name in dirs + files:
                try:
                    os.chown(os.path.join(root, name), uid, gid)
                except OSError:
                    pass
    except OSError as e:
        print(f"[warn] chown 回属主失败（可手动 sudo chown）：{e}")


def main():
    ap = argparse.ArgumentParser(description="Mac WeChat 4.x 密钥提取（lldb hook）")
    ap.add_argument("--db-dir", help="db_storage 目录（默认自动查找）")
    ap.add_argument("--timeout", type=int, default=40, help="抓取窗口秒数（默认 40）")
    args = ap.parse_args()

    print("=" * 60)
    print("  Mac WeChat 4.x key extraction — lldb hook CCKeyDerivationPBKDF")
    print("=" * 60)

    sip = subprocess.run(["csrutil", "status"], capture_output=True, text=True).stdout
    if "disabled" not in sip:
        print("\n[ERROR] SIP 未关闭。微信是 hardened runtime，SIP 开着 lldb 无法附加。")
        print("  关 SIP：重启进恢复模式 → 终端 csrutil disable → 重启。")
        sys.exit(2)
    if os.geteuid() != 0:
        print("\n[ERROR] 需要 root：sudo python3 wechat_extract_mac.py")
        sys.exit(2)

    db_dir = args.db_dir or find_mac4_db_storage()
    if not db_dir:
        print("\n[ERROR] 找不到 Mac 4.x db_storage（xwechat_files/<wxid>/db_storage）。")
        sys.exit(1)
    print(f"\nDB dir: {db_dir}")

    db_files, _ = collect_db_files(db_dir)
    if not db_files:
        print("[ERROR] db_storage 下没有可用 .db 文件。")
        sys.exit(1)
    print(f"Found {len(db_files)} databases")

    _pid, pname = wechat_pid()
    if not pname:
        pname = "WeChat"   # 没在跑也行，waitfor 会等我们下面重启它
        print("微信当前未运行，将由脚本启动。")
    else:
        print(f"WeChat process: {pname} (将优雅重启以捕获启动派生)")

    print(f"\n挂 lldb 抓取密钥派生（约 {args.timeout}s，会短暂重启一次微信）...")
    run_lldb_capture(pname, args.timeout)

    cands = parse_dump()
    if not cands:
        write_diagnostics(db_dir, db_files, cands=cands, matched=None,
                          note="失败于「没抓到密钥派生调用」——见上 [抓取结果] 的断点命中次数判读。")
        print("\n[ERROR] 没抓到密钥派生调用。")
        print(f"  1) 确认微信已登录并点进主界面；2) 重试；")
        print(f"  3) 把诊断文件发给 @Kevin 对比 → {_DIAG}")
        print(f"     （原始 lldb 日志仍在 {_LLDB_OUT}）")
        sys.exit(1)
    print(f"截获 {len(cands)} 个 enc_key 候选，开始按 HMAC 校验对回各库...")

    matched = {}
    for enc in cands:
        eb = bytes.fromhex(enc)
        for rel, info in db_files.items():
            if info.get('page1') and verify_key_page1(eb, info['page1']):
                matched[os.path.normpath(rel)] = enc

    if not matched:
        write_diagnostics(db_dir, db_files, cands=cands, matched=matched,
                          note="抓到候选但无一通过 HMAC 校验——布局/参数可能有变。")
        print("[ERROR] 抓到候选但无一通过 HMAC 校验——布局可能有变。")
        print(f"  把诊断文件 {_DIAG} 和 {_DUMP} 发给 @Kevin。")
        sys.exit(1)

    print(f"校验通过：{len(matched)}/{len(db_files)} 个库匹配到 key")
    write_diagnostics(db_dir, db_files, cands=cands, matched=matched,
                      note="本次成功。")
    print(f"（诊断信息已写入 {_DIAG}，需要对比时可发出）")

    # 未匹配到 key 的库：逐个打印路径 + 大小 + 未中原因，别让用户对着
    # "36/37" 干猜。绝大多数是"本轮微信没打开这个库、key 没派生"，无害。
    unmatched = [(rel, info) for rel, info in db_files.items()
                 if os.path.normpath(rel) not in matched]
    if unmatched:
        print(f"\n未匹配到 key 的库（{len(unmatched)} 个，通常无害，用到时重跑一次即可）：")
        for rel, info in sorted(unmatched):
            try:
                size = os.path.getsize(info['path'])
            except OSError:
                size = -1
            page1 = info.get('page1')
            if not page1:
                reason = f"不足一页({size}B < {4096}B)，无法 HMAC 校验（多为空/占位库）"
            elif page1[:len(SQLITE_HDR)] == SQLITE_HDR:
                reason = "库头是明文 SQLite，未加密——本就不需要 key"
            else:
                reason = "本轮未捕获到它的 enc_key（启动时微信没打开这个库；用到时重跑提取即可）"
            print(f"  · {rel}  [{size}B]  → {reason}")

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    out = keys_path(data_dir)   # data/all_keys.json（Mac/Windows 统一命名）
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'db_dir': db_dir, 'keys': matched}, f, indent=2)
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    # sudo 跑本脚本会把 data/ 下新写的文件留成 root 属主，普通用户之后改不动；
    # 递归 chown data 目录回真实用户（同时修掉 all_keys.json 与已有的
    # decrypted_cache/），避免每次提取后都要手动 sudo chown 解锁。
    _chown_back_to_invoker(data_dir)

    print(f"\n已保存 {len(matched)} 把 per-DB key 到: {out}（权限 600）")
    print("现在可直接查询（无需 sudo）：")
    print("  python3 wechat_query.py --contact \"<联系人名>\"")


if __name__ == '__main__':
    main()

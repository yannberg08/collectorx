"""wexport.detect — 微信数据目录发现与版本检测（Windows db_dir / Mac 4.x db_storage）。

从单体 wechat_query.py 原样抽出，函数体逐字未改。
"""
import os
from datetime import datetime


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


# ── Linux WeChat 4.x db_storage 发现 ───────────────────────────
# Linux 原生微信 4.x 数据目录：~/xwechat_files/<wxid>/db_storage/
#（实测微信启动参数 --wechat-files-path=$HOME/xwechat_files）。
# 兼容个别打包把数据放在 ~/.xwechat/xwechat_files 下的情形。
def _auto_find_linux_db_dir():
    """Linux: 自动查找 db_storage 目录（多账号取最近活跃的）。"""
    home = os.path.expanduser('~')
    bases = [
        os.path.join(home, 'xwechat_files'),
        os.path.join(home, '.xwechat', 'xwechat_files'),
    ]
    candidates = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        for wxid_dir in os.listdir(base):
            if wxid_dir.startswith('.') or wxid_dir == 'all_users':
                continue
            db_storage = os.path.join(base, wxid_dir, 'db_storage')
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
    candidates.sort(key=lambda x: x[1], reverse=True)
    if len(candidates) > 1:
        print(f"发现 {len(candidates)} 个微信账号，用最近活跃的: {candidates[0][2]}")
    return candidates[0][0]


__all__ = [
    '_read_wechat_config', '_auto_find_windows_db_dir', '_MAC_WECHAT_CONTAINER',
    '_find_mac4_db_storage', '_dir_latest_mtime', '_detect_mac_version',
    '_auto_find_linux_db_dir',
]

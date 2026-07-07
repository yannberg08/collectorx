"""wexport.paths — 路径 / 版本 / 日志 / 解密缓存基础设施。

从单体 wechat_query.py 原样抽出。唯一改动：本模块下沉到 wexport/ 子目录后，
比单体（原在 scripts/ 下）深了一层，故把路径基准从「脚本所在目录」改为以 skill
根目录为基准（SKILL_ROOT = wexport → scripts → skill 根），保证解析出的绝对路径
与单体在 scripts/ 下运行时完全一致（scripts/../data == scripts/wexport/../../data）。
"""
import os
import hashlib
import logging
import pathlib


# wexport/ → scripts/ → skill 根
SKILL_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DATA_DIR = SKILL_ROOT / 'data'


def _load_version():
    """读 skill 根目录的 VERSION 文件（由 covo-hub 发版时注入 / 仓库内也带一份）。"""
    try:
        vf = SKILL_ROOT / 'VERSION'
        if vf.exists():
            return vf.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return '0.0.0-dev'


__version__ = _load_version()


# ── 日志配置 ────────────────────────────────────────────────────
_log_dir = os.path.join(str(SKILL_ROOT), 'logs')
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, 'wechat_export.log')

logger = logging.getLogger('wechat_query')
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
    data_dir = str(DATA_DIR)
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
    # 单体在 scripts/ 下运行时 script_dir == scripts/；本模块下沉到 wexport/ 后，
    # 用 parent.parent 取回同一个 scripts/ 目录，保证 old_cache 绝对路径不变。
    script_dir = str(pathlib.Path(__file__).resolve().parent.parent)
    data_dir = str(DATA_DIR)
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


__all__ = [
    'SKILL_ROOT', 'DATA_DIR', '__version__', '_load_version',
    'logger', '_log_dir', '_log_file',
    '_get_decrypt_cache_dir', '_cleanup_legacy_temp', '_migrate_legacy_decrypted',
]

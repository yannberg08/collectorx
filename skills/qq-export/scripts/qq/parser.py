"""
qq.parser — QQ聊天记录解析
"""
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path


def find_qq_db_dir() -> Optional[Path]:
    """自动查找QQ数据库目录"""
    import sys
    candidates = []
    
    if sys.platform == "darwin":
        qq_dir = Path.home() / "Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ"
        if qq_dir.exists():
            for user_dir in qq_dir.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    elif sys.platform == "win32":
        documents = Path.home() / "Documents"
        tencent_files = documents / "Tencent Files"
        if tencent_files.exists():
            for user_dir in tencent_files.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    elif sys.platform == "linux":
        linux_paths = [
            Path.home() / ".local/share/QQ",
            Path.home() / ".QQ",
            Path("/opt/QQ"),
        ]
        for qq_base in linux_paths:
            if qq_base.exists():
                for user_dir in qq_base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        msg_dir = user_dir / "Msg"
                        if msg_dir.exists():
                            candidates.append(msg_dir)
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda p: max(f.stat().st_mtime for f in p.rglob("*.db")), reverse=True)
    return candidates[0]


def get_db_path(db_dir: Path) -> Optional[Path]:
    """获取数据库文件路径"""
    for db_file in db_dir.rglob("*.db"):
        if "Msg" in db_file.name or "msg" in db_file.name:
            return db_file
    return None

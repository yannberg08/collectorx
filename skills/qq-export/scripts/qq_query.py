#!/usr/bin/env python3
"""
QQ聊天记录查询工具
支持QQ 9.x（NT架构）的SQLite数据库
"""
import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def _find_qq_db_dir():
    """自动查找QQ数据库目录"""
    candidates = []
    
    # macOS
    if sys.platform == "darwin":
        qq_dir = Path.home() / "Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ"
        if qq_dir.exists():
            for user_dir in qq_dir.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    # Windows
    elif sys.platform == "win32":
        documents = Path.home() / "Documents"
        tencent_files = documents / "Tencent Files"
        if tencent_files.exists():
            for user_dir in tencent_files.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    # Linux
    elif sys.platform == "linux":
        # Linux QQ数据目录（可能的位置）
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
    
    # 返回最新的
    candidates.sort(key=lambda p: max(f.stat().st_mtime for f in p.rglob("*.db")), reverse=True)
    return candidates[0]


def _get_db_path(db_dir: Path):
    """获取数据库文件路径"""
    for db_file in db_dir.rglob("*.db"):
        if "Msg" in db_file.name or "msg" in db_file.name:
            return db_file
    return None


def cmd_recent(db_dir: Path, limit: int = 10):
    """查看最新消息"""
    db_path = _get_db_path(db_dir)
    if not db_path:
        print("ERROR: 未找到QQ数据库文件")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 查询最新消息（表结构可能因版本而异）
        cursor.execute("""
            SELECT * FROM message 
            ORDER BY msgTime DESC 
            LIMIT ?
        """, (limit,))
        
        messages = cursor.fetchall()
        conn.close()
        
        for msg in messages:
            print(json.dumps(msg, ensure_ascii=False, default=str))
        
    except Exception as e:
        print(f"查询失败: {e}")


def cmd_search(db_dir: Path, keyword: str):
    """搜索消息"""
    db_path = _get_db_path(db_dir)
    if not db_path:
        print("ERROR: 未找到QQ数据库文件")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM message 
            WHERE content LIKE ?
            LIMIT 50
        """, (f"%{keyword}%",))
        
        messages = cursor.fetchall()
        conn.close()
        
        print(f"找到 {len(messages)} 条消息")
        for msg in messages:
            print(json.dumps(msg, ensure_ascii=False, default=str))
        
    except Exception as e:
        print(f"搜索失败: {e}")


def cmd_export(db_dir: Path, output: str):
    """导出聊天记录"""
    db_path = _get_db_path(db_dir)
    if not db_path:
        print("ERROR: 未找到QQ数据库文件")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM message")
        messages = cursor.fetchall()
        conn.close()
        
        with open(output, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, default=str)
        
        print(f"导出完成: {len(messages)} 条消息 -> {output}")
        
    except Exception as e:
        print(f"导出失败: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="QQ聊天记录查询")
    parser.add_argument("--db-dir", help="QQ数据库目录")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # recent命令
    recent_parser = subparsers.add_parser("recent", help="查看最新消息")
    recent_parser.add_argument("--limit", type=int, default=10)
    
    # search命令
    search_parser = subparsers.add_parser("search", help="搜索消息")
    search_parser.add_argument("keyword", help="搜索关键词")
    
    # export命令
    export_parser = subparsers.add_parser("export", help="导出聊天记录")
    export_parser.add_argument("output", help="输出文件路径")
    
    args = parser.parse_args()
    
    # 查找数据库目录
    if args.db_dir:
        db_dir = Path(args.db_dir)
    else:
        db_dir = _find_qq_db_dir()
        if not db_dir:
            print("ERROR: 未找到QQ数据目录")
            print("请手动指定 --db-dir 参数")
            sys.exit(1)
    
    print(f"使用数据库目录: {db_dir}")
    
    if args.command == "recent":
        cmd_recent(db_dir, args.limit)
    elif args.command == "search":
        cmd_search(db_dir, args.keyword)
    elif args.command == "export":
        cmd_export(db_dir, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

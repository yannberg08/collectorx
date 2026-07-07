"""
notes.parser — 笔记解析
"""
import json
from pathlib import Path
from typing import List, Dict, Any


def parse_obsidian_vault(vault_path: str, limit: int = None) -> List[Dict[str, Any]]:
    """解析Obsidian笔记"""
    vault = Path(vault_path)
    if not vault.exists():
        return []
    
    notes = []
    md_files = list(vault.rglob("*.md"))
    
    if limit:
        md_files = md_files[:limit]
    
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            note = {
                "source": "obsidian",
                "path": str(md_file.relative_to(vault)),
                "name": md_file.stem,
                "content": content[:5000],
                "mtime": md_file.stat().st_mtime
            }
            notes.append(note)
        except Exception:
            pass
    
    return notes


def parse_notion_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """解析Notion页面"""
    return {
        "source": "notion",
        "id": page["id"],
        "title": _extract_notion_title(page),
        "url": page.get("url", ""),
        "created": page.get("created_time", ""),
        "last_edited": page.get("last_edited_time", "")
    }


def _extract_notion_title(page):
    props = page.get("properties", {})
    for prop_name, prop_value in props.items():
        if prop_value.get("type") == "title":
            title_parts = prop_value.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts)
    return page.get("id", "Untitled")

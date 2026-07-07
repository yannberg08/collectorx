"""
xueqiu.parser — 雪球关注列表CSV解析
"""
import csv
import json
from typing import List, Dict, Any, Optional


def parse_watchlist_csv(file_path: str) -> List[Dict[str, Any]]:
    """解析关注列表CSV"""
    records = []
    
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read().strip()
        
        # 尝试JSON格式
        if content.startswith("["):
            try:
                return json.loads(content)
            except:
                pass
        
        # 尝试CSV格式
        lines = content.split("\n")
        if len(lines) > 1:
            first_line = lines[0]
            if "," in first_line and any(k in first_line for k in ["代码", "名称", "code", "name"]):
                f.seek(0)
                reader = csv.DictReader(f)
                for row in reader:
                    record = _parse_row(row)
                    if record:
                        records.append(record)
            else:
                for line in lines:
                    code = line.strip()
                    if code and (code.isdigit() or code.startswith("6")):
                        records.append({"code": code, "name": "", "industry": "", "note": "", "source": "xueqiu"})
    
    return records


def _parse_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    code = row.get("代码") or row.get("code") or ""
    name = row.get("名称") or row.get("name") or ""
    industry = row.get("行业") or row.get("industry") or ""
    note = row.get("备注") or row.get("note") or ""
    
    if not code:
        return None
    
    return {
        "source": "xueqiu",
        "code": code,
        "name": name,
        "industry": industry,
        "note": note
    }

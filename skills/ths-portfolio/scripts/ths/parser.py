"""
ths.parser — 同花顺交割单CSV解析
"""
import csv
from datetime import datetime
from typing import List, Dict, Any


def parse_portfolio_csv(file_path: str) -> List[Dict[str, Any]]:
    """解析交割单CSV"""
    records = []
    
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = _parse_row(row)
            if record:
                records.append(record)
    
    return records


def _parse_row(row: Dict[str, str]) -> Dict[str, Any]:
    """解析单行数据"""
    # 尝试不同的字段名
    date = row.get("成交日期") or row.get("日期") or row.get("date") or ""
    time = row.get("成交时间") or row.get("时间") or row.get("time") or ""
    code = row.get("证券代码") or row.get("代码") or row.get("stock_code") or ""
    name = row.get("证券名称") or row.get("名称") or row.get("stock_name") or ""
    direction = row.get("买卖方向") or row.get("方向") or row.get("direction") or ""
    price = row.get("成交价格") or row.get("价格") or row.get("price") or "0"
    quantity = row.get("成交数量") or row.get("数量") or row.get("quantity") or "0"
    amount = row.get("成交金额") or row.get("金额") or row.get("amount") or "0"
    fee = row.get("手续费") or row.get("佣金") or row.get("fee") or "0"
    tax = row.get("印花税") or row.get("tax") or "0"
    
    if not code and not name:
        return None
    
    return {
        "date": date.split(" ")[0] if " " in date else date,
        "time": time.split(" ")[1] if " " in time else time,
        "code": code,
        "name": name,
        "direction": direction,
        "price": _to_float(price),
        "quantity": _to_int(quantity),
        "amount": _to_float(amount),
        "fee": _to_float(fee),
        "tax": _to_float(tax)
    }


def _to_float(value: str) -> float:
    """安全转换为float"""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0


def _to_int(value: str) -> int:
    """安全转换为int"""
    try:
        return int(float(value)) if value else 0
    except (ValueError, TypeError):
        return 0

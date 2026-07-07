"""
ths.stats — 交割单统计分析
"""
from typing import List, Dict, Any
from collections import defaultdict


def calculate_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算交易统计"""
    if not records:
        return {"total": 0}
    
    buy_records = [r for r in records if r["direction"] == "买入"]
    sell_records = [r for r in records if r["direction"] == "卖出"]
    
    buy_amount = sum(r["amount"] for r in buy_records)
    sell_amount = sum(r["amount"] for r in sell_records)
    total_fee = sum(r["fee"] for r in records)
    total_tax = sum(r["tax"] for r in records)
    
    return {
        "total": len(records),
        "buy_count": len(buy_records),
        "sell_count": len(sell_records),
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "net_amount": sell_amount - buy_amount,
        "total_fee": total_fee,
        "total_tax": total_tax
    }


def calculate_stock_stats(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按股票统计"""
    stocks = defaultdict(lambda: {"buy": 0, "sell": 0, "count": 0})
    
    for r in records:
        key = f"{r['code']} {r['name']}"
        stocks[key]["count"] += 1
        if r["direction"] == "买入":
            stocks[key]["buy"] += r["amount"]
        else:
            stocks[key]["sell"] += r["amount"]
    
    result = []
    for stock, data in stocks.items():
        result.append({
            "stock": stock,
            "count": data["count"],
            "buy_amount": data["buy"],
            "sell_amount": data["sell"],
            "net_amount": data["sell"] - data["buy"]
        })
    
    return sorted(result, key=lambda x: x["count"], reverse=True)


def format_stats(stats: Dict[str, Any]) -> str:
    """格式化统计信息"""
    lines = [
        "交易记录统计",
        "=" * 40,
        f"总记录数: {stats['total']}",
        f"买入记录: {stats['buy_count']} 笔",
        f"卖出记录: {stats['sell_count']} 笔",
        f"买入金额: {stats['buy_amount']:,.2f} 元",
        f"卖出金额: {stats['sell_amount']:,.2f} 元",
        f"净额: {stats['net_amount']:,.2f} 元",
        f"总手续费: {stats['total_fee']:,.2f} 元",
        f"总印花税: {stats['total_tax']:,.2f} 元"
    ]
    return "\n".join(lines)

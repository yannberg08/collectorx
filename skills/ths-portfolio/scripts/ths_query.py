#!/usr/bin/env python3
"""
同花顺交割单查询工具
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def parse_portfolio_csv(file_path: str):
    """解析交割单CSV"""
    records = []
    
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
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
                continue
            
            record = {
                "date": date.split(" ")[0] if " " in date else date,
                "time": time.split(" ")[1] if " " in time else time,
                "code": code,
                "name": name,
                "direction": direction,
                "price": float(price) if price else 0,
                "quantity": int(quantity) if quantity else 0,
                "amount": float(amount) if amount else 0,
                "fee": float(fee) if fee else 0,
                "tax": float(tax) if tax else 0
            }
            records.append(record)
    
    return records


def print_stats(records):
    """打印统计信息"""
    if not records:
        print("无交易记录")
        return
    
    # 按方向统计
    buy_records = [r for r in records if r["direction"] == "买入"]
    sell_records = [r for r in records if r["direction"] == "卖出"]
    
    buy_amount = sum(r["amount"] for r in buy_records)
    sell_amount = sum(r["amount"] for r in sell_records)
    total_fee = sum(r["fee"] for r in records)
    total_tax = sum(r["tax"] for r in records)
    
    print(f"交易记录统计")
    print(f"=" * 40)
    print(f"总记录数: {len(records)}")
    print(f"买入记录: {len(buy_records)} 笔")
    print(f"卖出记录: {len(sell_records)} 笔")
    print(f"买入金额: {buy_amount:,.2f} 元")
    print(f"卖出金额: {sell_amount:,.2f} 元")
    print(f"净额: {sell_amount - buy_amount:,.2f} 元")
    print(f"总手续费: {total_fee:,.2f} 元")
    print(f"总印花税: {total_tax:,.2f} 元")
    
    # 按股票统计
    stocks = {}
    for r in records:
        key = f"{r['code']} {r['name']}"
        if key not in stocks:
            stocks[key] = {"buy": 0, "sell": 0, "count": 0}
        stocks[key]["count"] += 1
        if r["direction"] == "买入":
            stocks[key]["buy"] += r["amount"]
        else:
            stocks[key]["sell"] += r["amount"]
    
    print(f"\n个股统计")
    print(f"=" * 40)
    for stock, data in sorted(stocks.items(), key=lambda x: x[1]["count"], reverse=True):
        net = data["sell"] - data["buy"]
        print(f"{stock}: {data['count']}笔 买入{data['buy']:,.0f} 卖出{data['sell']:,.0f} 净额{net:,.0f}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="同花顺交割单查询")
    parser.add_argument("--file", required=True, help="交割单CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    
    args = parser.parse_args()
    
    # 解析CSV
    records = parse_portfolio_csv(args.file)
    print(f"解析完成: {len(records)} 条交易记录")
    
    if args.stats:
        print_stats(records)
    
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"导出完成: {args.export}")


if __name__ == "__main__":
    main()

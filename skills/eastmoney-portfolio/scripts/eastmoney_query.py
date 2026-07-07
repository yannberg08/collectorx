#!/usr/bin/env python3
"""
东方财富交割单查询工具
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eastmoney.parser import parse_portfolio_csv
from eastmoney.stats import calculate_stats, calculate_stock_stats

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def main():
    parser = argparse.ArgumentParser(description="东方财富交割单查询")
    parser.add_argument("--file", required=True, help="交割单CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    
    args = parser.parse_args()
    
    records = parse_portfolio_csv(args.file)
    print(f"解析完成: {len(records)} 条交易记录")
    
    if args.stats:
        stats = calculate_stats(records)
        print(f"\n交易记录统计")
        print("=" * 40)
        print(f"总记录数: {stats['total']}")
        print(f"买入记录: {stats['buy_count']} 笔")
        print(f"卖出记录: {stats['sell_count']} 笔")
        print(f"买入金额: {stats['buy_amount']:,.2f} 元")
        print(f"卖出金额: {stats['sell_amount']:,.2f} 元")
        print(f"净额: {stats['net_amount']:,.2f} 元")
        
        stock_stats = calculate_stock_stats(records)
        print(f"\n个股统计")
        print("=" * 40)
        for s in stock_stats:
            print(f"{s['stock']}: {s['count']}笔")
    
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"导出完成: {args.export}")


if __name__ == "__main__":
    main()

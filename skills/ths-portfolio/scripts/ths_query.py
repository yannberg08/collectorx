#!/usr/bin/env python3
"""
同花顺交割单查询工具
"""
import argparse
import json
import sys
from pathlib import Path

# 添加当前目录到sys.path
sys.path.insert(0, str(Path(__file__).parent))

from ths.parser import parse_portfolio_csv
from ths.stats import calculate_stats, calculate_stock_stats, format_stats

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def main():
    parser = argparse.ArgumentParser(description="同花顺交割单查询")
    parser.add_argument("--file", required=True, help="交割单CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    
    args = parser.parse_args()
    
    # 解析CSV
    records = parse_portfolio_csv(args.file)
    print(f"解析完成: {len(records)} 条交易记录")
    
    if args.stats:
        stats = calculate_stats(records)
        print(format_stats(stats))
        
        stock_stats = calculate_stock_stats(records)
        print(f"\n个股统计")
        print("=" * 40)
        for s in stock_stats:
            print(f"{s['stock']}: {s['count']}笔 买入{s['buy_amount']:,.0f} 卖出{s['sell_amount']:,.0f} 净额{s['net_amount']:,.0f}")
    
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"导出完成: {args.export}")


if __name__ == "__main__":
    main()

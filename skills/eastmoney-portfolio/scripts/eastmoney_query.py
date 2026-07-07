#!/usr/bin/env python3
"""
东方财富投资行为与交易强证据采集工具
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eastmoney.local_collect import (
    DEFAULT_HOME,
    build_local_probe_report,
    collect_local,
    find_eastmoney_homes,
    sync_package_to_soulmirror,
)
from eastmoney.parser import parse_portfolio_csv
from eastmoney.stats import calculate_stats, calculate_stock_stats

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def main():
    parser = argparse.ArgumentParser(description="东方财富投资行为与交易强证据采集")
    parser.add_argument("--file", help="交割单CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--collect-local", action="store_true", help="采集东方财富本机投资行为证据")
    parser.add_argument("--platform", choices=["auto", "mac", "windows", "generic"], default="auto", help="本机扫描平台适配器")
    parser.add_argument("--container-root", help="本机扫描根目录；Mac 默认使用东方财富容器目录")
    parser.add_argument("--probe-export", help="导出本机平台探测报告JSON路径")
    parser.add_argument("--eastmoney-home", help="东方财富本机数据目录")
    parser.add_argument("--trade-export", action="append", default=[], help="东方财富交易界面导出的明细文件，可重复传入")
    parser.add_argument("--trade-export-dir", action="append", default=[], help="东方财富交易明细导出目录，会递归读取 CSV/TSV/TXT/JSON")
    parser.add_argument("--auto-trade-ui", action="store_true", help="自动打开东方财富交易页并只读采集资产/持仓/成交/委托/资金表")
    parser.add_argument("--output", help="本机采集包输出目录")
    parser.add_argument("--sync-soulmirror", action="store_true", help="采集后把事件和投资证据包同步到 ~/.soulmirror/lake")
    parser.add_argument("--soulmirror-home", help="SoulMirror 根目录，默认 ~/.soulmirror")
    parser.add_argument("--user", help="指定东方财富本地用户目录名")
    
    args = parser.parse_args()
    trade_export_inputs = [
        Path(path).expanduser()
        for path in [*args.trade_export, *args.trade_export_dir]
    ]

    exact_home = Path(args.eastmoney_home).expanduser() if args.eastmoney_home else None
    discovered_homes = []
    if exact_home:
        discovered_homes = [exact_home]
    elif args.collect_local or args.probe_export:
        discovered_homes = find_eastmoney_homes(args.container_root, platform=args.platform)

    if args.probe_export:
        report = build_local_probe_report(
            platform=args.platform,
            container_root=args.container_root,
            homes=discovered_homes,
        )
        with open(args.probe_export, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"探测报告导出完成: {args.probe_export}")
        if not args.collect_local and not args.file:
            print("未执行本机采集，仅导出探测报告")
            return

    if args.collect_local:
        output = Path(args.output).expanduser() if args.output else Path.cwd() / "eastmoney-investor-v2-collect"
        if exact_home:
            home = exact_home
        elif discovered_homes:
            home = discovered_homes[0]
        elif args.container_root:
            parser.error("未在 --container-root 下发现东方财富本机数据目录")
        else:
            home = DEFAULT_HOME
        manifest = collect_local(
            output_dir=output,
            eastmoney_home=home,
            user=args.user,
            platform=args.platform,
            trade_export_files=trade_export_inputs,
            auto_trade_ui=args.auto_trade_ui,
        )
        validation = manifest.get("validation", {})
        print(f"采集完成: {manifest['source_counts']['total_events']} 条事件")
        print(f"输出目录: {output}")
        if trade_export_inputs:
            print(f"交易明细输入: {len(trade_export_inputs)} 个文件/目录")
        if args.auto_trade_ui:
            print("交易页自动采集: 已尝试")
        if args.sync_soulmirror:
            sync_report = sync_package_to_soulmirror(
                output,
                soulmirror_home=Path(args.soulmirror_home).expanduser() if args.soulmirror_home else None,
            )
            print(f"SoulMirror lake 同步: {sync_report['latest_dir']}")
        print(f"校验: {'通过' if validation.get('ok') else '失败'}")
        if validation.get("errors"):
            for err in validation["errors"]:
                print(f"- {err}")
        return

    if not args.file:
        parser.error("CSV 模式需要 --file；本机采集请使用 --collect-local，平台探测请使用 --probe-export")
    
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

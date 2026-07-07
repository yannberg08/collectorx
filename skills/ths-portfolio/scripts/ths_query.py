#!/usr/bin/env python3
"""
同花顺交易记录查询工具
"""
import argparse
import json
import sys
from pathlib import Path

# 添加当前目录到sys.path
sys.path.insert(0, str(Path(__file__).parent))

from ths.parser import parse_portfolio_csv
from ths.events import (
    gap_status_to_event,
    gui_snapshot_to_events,
    holdings_to_events,
    personal_metadata_to_events,
    records_to_events,
)
from ths.gui import collect_gui_snapshot
from ths.local import (
    build_local_probe_report,
    build_gap_status,
    find_xcs_lscj_files,
    infer_holdings,
    local_file_label,
    local_source_label,
    parse_xcs_lscj,
)
from ths.metadata import collect_personal_metadata
from ths.stats import calculate_stats, calculate_stock_stats, format_stats

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def main():
    parser = argparse.ArgumentParser(description="同花顺交易记录查询")
    parser.add_argument("--file", help="交割单CSV文件路径")
    parser.add_argument("--local-xcs-file", help="同花顺本机XcsLscj历史成交文件路径")
    parser.add_argument("--local-scan", action="store_true", help="自动扫描同花顺本机XcsLscj历史成交文件")
    parser.add_argument("--platform", choices=["auto", "mac", "windows", "generic"], default="auto", help="本机扫描平台适配器")
    parser.add_argument("--container-root", help="本机扫描根目录；Mac默认使用同花顺容器Data目录")
    parser.add_argument("--probe-export", help="导出本机平台探测报告JSON路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--holdings-export", help="导出从历史成交估算的持仓JSON路径")
    parser.add_argument("--metadata-export", help="导出同花顺个人化元数据JSON路径")
    parser.add_argument("--gui-snapshot-export", help="导出同花顺已打开交易界面的真实账户快照JSON路径")
    parser.add_argument("--gui-screenshot-dir", help="导出GUI快照截图目录；默认不截图")
    parser.add_argument("--event-export", help="导出CollectorX Event JSONL路径")
    parser.add_argument("--include-holding-events", action="store_true", help="在事件JSONL中加入估算持仓事件")
    parser.add_argument("--include-metadata-events", action="store_true", help="在事件JSONL中加入自选/策略/资讯/组件等个人化元数据事件")
    parser.add_argument("--include-gui-events", action="store_true", help="在事件JSONL中加入已打开同花顺交易界面的真实账户/持仓/委托/成交快照事件")
    parser.add_argument("--gap-event", action="store_true", help="在事件JSONL中加入本机采集缺口状态事件")
    parser.add_argument("--source", help="事件source字段")
    parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    
    args = parser.parse_args()

    records = []
    raw_labels = []

    if args.file:
        csv_records = parse_portfolio_csv(args.file)
        records.extend(csv_records)
        raw_labels.append(args.file)

    local_files = []
    if args.local_xcs_file:
        local_files.append(Path(args.local_xcs_file).expanduser())
    if args.local_scan:
        local_files.extend(find_xcs_lscj_files(args.container_root, platform=args.platform))

    seen_local_files = []
    for path in local_files:
        if path in seen_local_files:
            continue
        seen_local_files.append(path)
        local_records = parse_xcs_lscj(str(path))
        records.extend(local_records)
        raw_labels.append(local_file_label(path))

    if args.probe_export:
        report = build_local_probe_report(
            platform=args.platform,
            container_root=args.container_root,
            files=seen_local_files,
        )
        with open(args.probe_export, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"探测报告导出完成: {args.probe_export}")

    metadata = None
    if args.metadata_export or args.include_metadata_events:
        metadata = collect_personal_metadata(args.container_root, platform=args.platform)

    if args.metadata_export:
        with open(args.metadata_export, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"个人化元数据导出完成: {args.metadata_export}")

    gui_snapshot = None
    if args.gui_snapshot_export or args.include_gui_events:
        gui_snapshot = collect_gui_snapshot(
            screenshot_dir=args.gui_screenshot_dir,
            collected_at=args.collected_at,
        )

    if args.gui_snapshot_export:
        with open(args.gui_snapshot_export, "w", encoding="utf-8") as f:
            json.dump(gui_snapshot, f, ensure_ascii=False, indent=2)
        print(f"GUI真实账户快照导出完成: {args.gui_snapshot_export}")

    if not args.file and not seen_local_files:
        if args.metadata_export or args.include_metadata_events or args.gui_snapshot_export or args.include_gui_events:
            if not args.event_export:
                return
        elif args.probe_export:
            print("未发现本机Xcs文件，仅导出探测报告")
            return
        else:
            parser.error("请提供 --file、--local-xcs-file、--local-scan 或 --metadata-export 之一")

    source = args.source
    if not source:
        if args.file and seen_local_files:
            source = "同花顺交易记录"
        elif seen_local_files:
            source = local_source_label(args.platform)
        elif args.metadata_export or args.include_metadata_events:
            source = "同花顺个人化元数据"
        elif args.gui_snapshot_export or args.include_gui_events:
            source = "同花顺Mac交易界面确认快照"
        else:
            source = "同花顺交割单 CSV"

    raw_file = raw_labels[0] if len(raw_labels) == 1 else None
    print(f"解析完成: {len(records)} 条交易记录")
    if seen_local_files:
        print(f"本机Xcs文件: {len(seen_local_files)} 个")
    
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

    holdings = []
    if args.holdings_export or args.include_holding_events or args.gap_event:
        holdings = infer_holdings(records)

    if args.holdings_export:
        with open(args.holdings_export, "w", encoding="utf-8") as f:
            json.dump(holdings, f, ensure_ascii=False, indent=2)
        print(f"估算持仓导出完成: {len(holdings)} 条 -> {args.holdings_export}")

    if args.event_export:
        events = records_to_events(
            records,
            source=source,
            raw_file=raw_file,
            collected_at=args.collected_at,
        )
        if args.include_holding_events:
            events.extend(
                holdings_to_events(
                    holdings,
                    source=f"{source} / 估算持仓",
                    raw_file=raw_file,
                    collected_at=args.collected_at,
                )
            )
        if args.gap_event:
            events.append(
                gap_status_to_event(
                    build_gap_status(records, holdings),
                    source=f"{source} / 本机采集状态",
                    collected_at=args.collected_at,
                )
            )
        if args.include_metadata_events:
            events.extend(
                personal_metadata_to_events(
                    metadata or collect_personal_metadata(args.container_root, platform=args.platform),
                    source=f"{source} / 个人化元数据",
                    collected_at=args.collected_at,
                )
            )
        if args.include_gui_events:
            events.extend(
                gui_snapshot_to_events(
                    gui_snapshot or collect_gui_snapshot(
                        screenshot_dir=args.gui_screenshot_dir,
                        collected_at=args.collected_at,
                    ),
                    source=f"{source} / GUI确认快照",
                    collected_at=args.collected_at,
                )
            )
        with open(args.event_export, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
                f.write("\n")
        print(f"事件导出完成: {len(events)} 条 -> {args.event_export}")


if __name__ == "__main__":
    main()

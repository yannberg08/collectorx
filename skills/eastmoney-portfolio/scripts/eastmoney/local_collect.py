"""
eastmoney.local_collect -- collect local EastMoney investor evidence.

The collector follows the same evidence boundary used by the THS collector:
facts, inferred state, and gaps are emitted as separate events. Credentials,
cookies, sessions, and raw protocol payloads are never written to outputs.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
import shutil
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from eastmoney.trade_export import discover_export_files, parse_trade_export_file
from eastmoney.ui_collect import TradeUISnapshot, collect_trade_ui_snapshot


COLLECTOR = "eastmoney-investor-v2"
EVENT_SCHEMA = "collectorx.event.v1"
MANIFEST_SCHEMA = "eastmoney.investor_v2_collect.manifest.v1"
TZ = timezone(timedelta(hours=8))

DEFAULT_HOME = Path.home() / (
    "Library/Containers/com.emmac.mac/Data/Library/Application Support/EastMoney"
)
APP_INFO_PLIST = Path("/Applications/东方财富经典版.app/Contents/Info.plist")
SUPPORTED_LOCAL_PLATFORMS = {"auto", "mac", "windows", "linux", "generic"}
LOCAL_SOURCE_PREFIX_BY_PLATFORM = {
    "mac": "东方财富 Mac",
    "windows": "东方财富 Windows",
    "linux": "东方财富 Linux",
    "generic": "东方财富本机",
}

MARKET_MAP = {
    "0": "SZ",
    "1": "SH",
    "2": "BJ",
    "105": "FUND",
    "150": "FUND",
}

FORBIDDEN_OUTPUT_PATTERNS = [
    re.compile(r"(?i)\b(cookie|token|password|passwd|secret|session|ticket|sign)\b"),
    re.compile(r"(?i)CUser(Session|TcpSession)\s*="),
    re.compile(r"(?i)deviceid"),
    re.compile(r"(?i)deviceinfo"),
]

COLLECTORX_ALLOWED_KINDS = {
    "message",
    "file",
    "note",
    "email",
    "calendar",
    "task",
    "trade",
    "holding",
    "watchlist",
    "a2a",
    "profile",
    "other",
}

SOURCE_KIND_TO_COLLECTORX_KIND = {
    "watchlist": "watchlist",
    "recent_stock": "watchlist",
    "stock_note": "note",
    "chart_drawing": "note",
    "broker_asset_snapshot": "holding",
    "broker_position_detail": "holding",
    "broker_trade_execution": "trade",
    "broker_entrust_order": "trade",
    "broker_fund_flow": "trade",
}

LEGACY_WIKI_TARGET_MAP = {
    "vertical/investor/opportunity-watchlist": [
        "investor.opportunity_watchlist.watchlist",
        "investor.capability_circle.attention_universe",
    ],
    "vertical/investor/competence-circle": [
        "investor.capability_circle.attention_universe",
    ],
    "vertical/investor/research-consumption": [
        "investor.information_sources.news_consumption",
        "investor.research_consumption.workflow",
    ],
    "vertical/investor/decision-framework": [
        "investor.decision_framework.strategy_rules",
        "investor.decision_framework.monitoring_rules",
    ],
    "vertical/investor/record-review": [
        "investor.record_review.decision_log",
    ],
    "vertical/investor/risk-portfolio": [
        "investor.risk_portfolio.current_positions",
        "investor.risk_portfolio.current_assets",
        "investor.risk_portfolio.portfolio_constraints",
    ],
    "vertical/investor/profile": [
        "investor.data_quality.collection_gaps",
    ],
}

SOURCE_KIND_EXTRA_WIKI_TARGETS = {
    "watchlist": [
        "investor.opportunity_watchlist.watchlist",
        "investor.capability_circle.attention_universe",
    ],
    "recent_stock": [
        "investor.opportunity_watchlist.watchlist",
        "investor.information_sources.news_consumption",
    ],
    "stock_note": [
        "investor.record_review.decision_log",
        "investor.decision_framework.strategy_rules",
        "investor.research_consumption.workflow",
    ],
    "chart_drawing": [
        "investor.decision_framework.monitoring_rules",
        "investor.research_consumption.workflow",
    ],
    "custom_panel": [
        "investor.research_consumption.workflow",
        "investor.decision_framework.monitoring_rules",
    ],
    "broker_asset_snapshot": [
        "investor.risk_portfolio.current_assets",
        "investor.risk_portfolio.portfolio_constraints",
        "external.capital.assets",
    ],
    "broker_asset_status": [
        "investor.risk_portfolio.current_assets",
        "investor.data_quality.collection_gaps",
    ],
    "broker_position_detail": [
        "investor.risk_portfolio.current_positions",
        "investor.decision_framework.position_sizing",
        "external.capital.assets",
    ],
    "broker_position_status": [
        "investor.risk_portfolio.current_positions",
        "investor.data_quality.collection_gaps",
    ],
    "broker_trade_execution": [
        "investor.record_review.decision_log",
        "investor.risk_portfolio.portfolio_constraints",
        "investor.decision_framework.position_sizing",
    ],
    "broker_entrust_order": [
        "investor.execution.orders",
        "investor.decision_framework.monitoring_rules",
    ],
    "broker_fund_flow": [
        "external.capital.cashflows",
        "investor.risk_portfolio.current_assets",
    ],
    "trade_page_stock_context": [
        "investor.decision_framework.triggers",
        "investor.opportunity_watchlist.watchlist",
    ],
    "broker_interface_response": [
        "investor.data_quality.collection_gaps",
        "investor.record_review.decision_log",
    ],
    "broker_trade_ui_status": [
        "investor.data_quality.collection_gaps",
        "investor.risk_portfolio.current_assets",
        "investor.risk_portfolio.current_positions",
    ],
    "broker_trade_table_status": [
        "investor.data_quality.collection_gaps",
        "investor.record_review.decision_log",
        "investor.execution.orders",
        "external.capital.cashflows",
    ],
    "broker_market_gap": [
        "investor.data_quality.collection_gaps",
        "investor.risk_portfolio.current_positions",
    ],
    "broker_login_status": [
        "investor.data_quality.collection_gaps",
    ],
    "watchlist_sync_status": [
        "investor.opportunity_watchlist.watchlist",
        "investor.data_quality.collection_gaps",
    ],
    "watchlist_local_load_status": [
        "investor.opportunity_watchlist.watchlist",
        "investor.data_quality.collection_gaps",
    ],
    "data_gap": [
        "investor.data_quality.collection_gaps",
    ],
    "profile": [
        "investor.data_quality.collection_gaps",
    ],
}


@dataclass
class SourceFile:
    kind: str
    path: Path
    path_redacted: str

    def manifest_entry(self) -> Dict[str, Any]:
        entry = {
            "kind": self.kind,
            "path_redacted": self.path_redacted,
        }
        if self.path.exists() and self.path.is_file():
            entry["file_sha256"] = sha256_file(self.path)
        return entry


def collect_local(
    output_dir: Path,
    eastmoney_home: Optional[Path] = None,
    user: Optional[str] = None,
    platform: str = "auto",
    trade_export_files: Optional[Iterable[Path]] = None,
    auto_trade_ui: bool = False,
) -> Dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    resolved_platform = resolve_platform(platform)
    if eastmoney_home is None:
        homes = find_eastmoney_homes(platform=platform)
        eastmoney_home = homes[0] if homes else DEFAULT_HOME
    eastmoney_home = eastmoney_home.expanduser().resolve()
    collected_at = now_iso()
    source_prefix = local_source_prefix(resolved_platform)
    platform_meta = {
        "requested": platform,
        "resolved": resolved_platform,
        "structure_status": local_structure_status(resolved_platform),
    }

    users = discover_users(eastmoney_home)
    selected_user = user or (users[0] if users else None)
    user_dir = eastmoney_home / "config" / "user" / selected_user if selected_user else None

    events: List[Dict[str, Any]] = []
    sources: List[SourceFile] = []

    app_profile = read_app_profile()
    if selected_user:
        events.append(
            make_event(
                kind="profile",
                data={
                    "profile_type": "eastmoney_local_profile",
                    "product": "东方财富经典版",
                    "app_version": app_profile.get("app_version"),
                    "app_build": app_profile.get("app_build"),
                    "local_platform": resolved_platform,
                    "login_name": selected_user,
                    "login_name_masked": mask_identifier(selected_user),
                    "login_name_sha256": sha256_text(selected_user),
                    "config_user_dir_found": True,
                },
                collected_at=collected_at,
                source=f"{source_prefix} 本地已登录账户数据",
                privacy_contains=["portfolio"],
                raw_ref={
                    "container": redacted_path(eastmoney_home),
                    "user_config_dir": redacted_path(user_dir),
                },
                wiki_targets=["vertical/investor/profile"],
            )
        )

    name_index = load_stock_name_index(eastmoney_home / "data" / "DataCenterV2.db")

    if user_dir:
        selfstocks_path = user_dir / "SelfStocks_v1.plist"
        sources.append(SourceFile("watch_groups", selfstocks_path, redacted_path(selfstocks_path)))
        events.extend(
            collect_watchlist_events(
                selfstocks_path, name_index, collected_at, source_prefix=source_prefix
            )
        )

        recent_path = user_dir / "recent_stock.dat"
        sources.append(SourceFile("recent_stock", recent_path, redacted_path(recent_path)))
        events.extend(
            collect_recent_stock_events(recent_path, name_index, collected_at, source_prefix=source_prefix)
        )

        note_path = user_dir / "StockNote.sqlite"
        sources.append(SourceFile("stock_notes", note_path, redacted_path(note_path)))
        note_events, note_count = collect_stock_note_events(
            note_path, name_index, collected_at, source_prefix=source_prefix
        )
        events.extend(note_events)
        if note_count == 0:
            events.append(
                gap_event(
                    collected_at,
                    gap="stock_notes_empty",
                    status="not_found",
                    note="StockNote.sqlite exists but contains no note rows.",
                    raw_ref={"path_redacted": redacted_path(note_path)},
                    wiki_targets=["vertical/investor/research-consumption"],
                    source_prefix=source_prefix,
                )
            )

        line_path = user_dir / "LineParintv1.db"
        sources.append(SourceFile("chart_drawings", line_path, redacted_path(line_path)))
        drawing_events, drawing_count = collect_chart_drawing_events(
            line_path, name_index, collected_at, source_prefix=source_prefix
        )
        events.extend(drawing_events)
        if drawing_count == 0:
            events.append(
                gap_event(
                    collected_at,
                    gap="chart_drawings_empty",
                    status="not_found",
                    note="LineParintv1.db exists but contains no drawing rows.",
                    raw_ref={"path_redacted": redacted_path(line_path)},
                    wiki_targets=["vertical/investor/research-consumption"],
                    source_prefix=source_prefix,
                )
            )

        panel_path = user_dir / "EMCustomPanelDatas.sqlite"
        sources.append(SourceFile("custom_panels", panel_path, redacted_path(panel_path)))
        panel_events, panel_count = collect_panel_events(
            panel_path, collected_at, source_prefix=source_prefix
        )
        events.extend(panel_events)
        if panel_count == 0:
            events.append(
                gap_event(
                    collected_at,
                    gap="custom_panels_empty",
                    status="not_found",
                    note="EMCustomPanelDatas.sqlite exists but contains no custom panel rows.",
                    raw_ref={"path_redacted": redacted_path(panel_path)},
                    wiki_targets=["vertical/investor/decision-framework"],
                    source_prefix=source_prefix,
                )
            )

    trade_log = eastmoney_home / "log" / "TradeLog.log"
    sync_log = eastmoney_home / "log" / "SyncSelfStock.log"
    sources.append(SourceFile("trade_interface_log", trade_log, redacted_path(trade_log)))
    sources.append(SourceFile("self_stock_sync_log", sync_log, redacted_path(sync_log)))
    events.extend(collect_trade_log_events(trade_log, collected_at, source_prefix=source_prefix))
    events.extend(collect_sync_log_events(sync_log, collected_at, source_prefix=source_prefix))

    if auto_trade_ui:
        events.extend(collect_trade_ui_events(collected_at, source_prefix=source_prefix))

    for export_path in discover_export_files(trade_export_files or []):
        sources.append(SourceFile("trade_detail_export", export_path, redacted_path(export_path)))
        events.extend(collect_trade_export_events(export_path, collected_at, source_prefix=source_prefix))

    add_global_gap_events(events, collected_at, source_prefix=source_prefix)

    events = dedupe_events(events)
    write_package(output_dir, events, sources, collected_at, eastmoney_home, platform_meta)
    manifest = build_manifest(output_dir, events, sources, collected_at, platform_meta)
    write_json(output_dir / "manifest.json", manifest)
    write_summary(output_dir, manifest, events)
    write_wiki(output_dir, events)
    write_investor_wiki_evidence(output_dir, events, collected_at)
    validation = validate_output(output_dir)
    manifest["validation"] = validation
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def sync_package_to_soulmirror(
    output_dir: Path,
    soulmirror_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Copy the validated collector package into SoulMirror's local lake.

    The bridge is file-based on purpose: it does not assume a daemon-side command
    collector driver exists, and it does not write final wiki pages directly.
    """
    output_dir = output_dir.expanduser().resolve()
    soulmirror_root = (soulmirror_home or Path.home() / ".soulmirror").expanduser()
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    collected_at = str(manifest.get("collected_at") or now_iso())
    run_id = re.sub(r"[^0-9A-Za-z_.-]+", "-", collected_at).strip("-")
    lake_root = soulmirror_root / "lake" / COLLECTOR
    run_dir = lake_root / run_id
    latest_dir = lake_root / "latest"
    files = [
        output_dir / "manifest.json",
        output_dir / "structured_profile.json",
        output_dir / "investor_wiki_evidence.v1.json",
        output_dir / "SUMMARY.md",
        output_dir / "lake" / COLLECTOR / "events.jsonl",
    ]
    copied: List[str] = []
    for dest_root in (run_dir, latest_dir):
        dest_root.mkdir(parents=True, exist_ok=True)
        for source in files:
            if not source.exists():
                continue
            dest = dest_root / source.name
            shutil.copy2(source, dest)
            copied.append(str(dest))
    bridge_manifest = {
        "schema": "finclaw.soulmirror_bridge.v1",
        "collector": COLLECTOR,
        "synced_at": now_iso(),
        "source_output": str(output_dir),
        "soulmirror_home": str(soulmirror_root),
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "copied_files": sorted(set(copied)),
        "note": "Copied collector evidence into SoulMirror lake only; final wiki organization remains app-controlled.",
    }
    write_json(output_dir / "soulmirror_sync.json", bridge_manifest)
    write_json(latest_dir / "soulmirror_sync.json", bridge_manifest)
    return bridge_manifest


def resolve_platform(platform: str = "auto") -> str:
    if platform not in SUPPORTED_LOCAL_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    if platform != "auto":
        return platform
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "generic"


def local_source_prefix(platform: str = "auto") -> str:
    return LOCAL_SOURCE_PREFIX_BY_PLATFORM.get(resolve_platform(platform), "东方财富本机")


def local_structure_status(resolved_platform: str) -> str:
    if resolved_platform == "mac" and sys.platform == "darwin":
        return "verified_on_current_mac"
    return "candidate_rules_need_real_machine_verification"


def find_eastmoney_homes(
    container_root: Optional[str] = None,
    *,
    platform: str = "auto",
) -> List[Path]:
    """Find EastMoney local data homes for the requested platform adapter.

    Windows rules are code-level candidates for simulation and future adapters.
    They must be verified on a real Windows EastMoney installation before being
    treated as production-confirmed paths.
    """
    resolved_platform = resolve_platform(platform)
    homes: List[Path] = []
    for root in _scan_roots(container_root, resolved_platform):
        if not root.exists():
            continue
        if _is_eastmoney_home(root):
            homes.append(root)
        for pattern in _eastmoney_home_patterns_for_platform(resolved_platform):
            for path in root.glob(pattern):
                if path.is_dir() and _is_eastmoney_home(path):
                    homes.append(path)
    return _dedupe_paths(homes)


def build_local_probe_report(
    *,
    platform: str = "auto",
    container_root: Optional[str] = None,
    homes: Optional[Iterable[Path]] = None,
) -> Dict[str, Any]:
    resolved_platform = resolve_platform(platform)
    home_source = homes if homes is not None else find_eastmoney_homes(container_root, platform=platform)
    home_list = _dedupe_paths(Path(path).expanduser() for path in home_source)
    roots = _scan_roots(container_root, resolved_platform)
    has_evidence_home = any(_is_eastmoney_home(home) for home in home_list)

    user_count = sum(len(discover_users(home)) for home in home_list)
    watchlist_files = _count_existing(home_list, "config/user/*/SelfStocks_v1.plist")
    recent_files = _count_existing(home_list, "config/user/*/recent_stock.dat")
    note_files = _count_existing(home_list, "config/user/*/StockNote.sqlite")
    drawing_files = _count_existing(home_list, "config/user/*/LineParintv1.db")
    panel_files = _count_existing(home_list, "config/user/*/EMCustomPanelDatas.sqlite")
    trade_logs = _count_existing(home_list, "log/TradeLog.log")
    sync_logs = _count_existing(home_list, "log/SyncSelfStock.log")
    name_dbs = _count_existing(home_list, "data/DataCenterV2.db")

    return {
        "probe_type": "eastmoney_local_investor_evidence",
        "platform": {
            "requested": platform,
            "resolved": resolved_platform,
            "structure_status": local_structure_status(resolved_platform),
        },
        "scan_roots": [_safe_path_label(root) for root in roots],
        "eastmoney_homes": {
            "home_count": len(home_list),
            "homes": [_safe_path_label(home) for home in home_list],
        },
        "capabilities": {
            "config_users": user_count,
            "watchlist_files": watchlist_files,
            "recent_stock_files": recent_files,
            "stock_note_files": note_files,
            "chart_drawing_files": drawing_files,
            "custom_panel_files": panel_files,
            "trade_interface_logs": trade_logs,
            "self_stock_sync_logs": sync_logs,
            "stock_name_databases": name_dbs,
            "trade_ui_automation": (
                "available_on_mac_when_trading_window_unlocked"
                if resolved_platform == "mac"
                else "not_supported_for_platform"
            ),
            "local_investor_evidence": "available" if has_evidence_home else "not_found",
        },
        "unsupported_without_confirmed_snapshot": [
            "current_position_detail",
            "asset_amount_detail",
            "historical_trade_detail",
            "entrust_or_cancel_detail",
        ],
        "privacy_policy": {
            "authorized_business_identifiers": "preserved_in_local_lake",
            "probe_path_labels": "redacted_for_probe_only",
            "login_material": "not_read",
            "raw_trade_payload": "not_written",
        },
    }


def _scan_roots(container_root: Optional[str], platform: str) -> List[Path]:
    if container_root:
        return [Path(container_root).expanduser()]
    if platform == "mac":
        return [DEFAULT_HOME]
    if platform == "windows":
        home = Path.home()
        return [
            home / "AppData" / "Roaming" / "EastMoney",
            home / "AppData" / "Local" / "EastMoney",
            home / "AppData" / "Roaming" / "东方财富",
            home / "AppData" / "Local" / "东方财富",
            Path("C:/ProgramData/EastMoney"),
            Path("C:/ProgramData/东方财富"),
        ]
    if platform == "linux":
        home = Path.home()
        return [
            home / ".config" / "EastMoney",
            home / ".config" / "东方财富",
            home / ".local" / "share" / "EastMoney",
            home / ".local" / "share" / "东方财富",
            home / ".eastmoney",
            home,
        ]
    return [Path.home()]


def _eastmoney_home_patterns_for_platform(platform: str) -> List[str]:
    if platform == "mac":
        return [
            "Library/Containers/com.emmac.mac/Data/Library/Application Support/EastMoney",
            "**/Library/Containers/com.emmac.mac/Data/Library/Application Support/EastMoney",
            "EastMoney",
        ]
    if platform == "windows":
        return [
            "Users/*/AppData/Roaming/EastMoney",
            "Users/*/AppData/Local/EastMoney",
            "Users/*/AppData/Roaming/东方财富",
            "Users/*/AppData/Local/东方财富",
            "AppData/Roaming/EastMoney",
            "AppData/Local/EastMoney",
            "AppData/Roaming/东方财富",
            "AppData/Local/东方财富",
            "ProgramData/EastMoney",
            "ProgramData/东方财富",
            "**/EastMoney",
            "**/东方财富",
        ]
    if platform == "linux":
        return [
            ".config/EastMoney",
            ".config/东方财富",
            ".local/share/EastMoney",
            ".local/share/东方财富",
            ".eastmoney",
            "EastMoney",
            "东方财富",
            "**/EastMoney",
            "**/东方财富",
        ]
    return [
        "**/EastMoney",
        "**/东方财富",
        "**/com.emmac.mac/**/EastMoney",
    ]


def _is_eastmoney_home(path: Path) -> bool:
    return any(
        candidate.exists()
        for candidate in (
            path / "config" / "user",
            path / "log" / "TradeLog.log",
            path / "log" / "SyncSelfStock.log",
            path / "data" / "DataCenterV2.db",
        )
    )


def _count_existing(homes: Iterable[Path], pattern: str) -> int:
    count = 0
    for home in homes:
        count += sum(1 for path in home.glob(pattern) if path.exists())
    return count


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    result: List[Path] = []
    seen = set()
    for path in paths:
        normalized = Path(path).expanduser()
        try:
            key = str(normalized.resolve())
        except FileNotFoundError:
            key = str(normalized.absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _safe_path_label(path: Path) -> str:
    text = str(path)
    text = re.sub(r"(/Users/)([^/]+)", lambda m: m.group(1) + mask_identifier(m.group(2)), text)
    text = re.sub(r"(\\Users\\)([^\\]+)", lambda m: m.group(1) + mask_identifier(m.group(2)), text)
    text = re.sub(r"(/config/user/)([^/]+)", lambda m: m.group(1) + mask_identifier(m.group(2)), text)
    text = re.sub(r"\b\d{7,}\b", lambda m: mask_identifier(m.group(0)), text)
    return text


def read_app_profile() -> Dict[str, Optional[str]]:
    if not APP_INFO_PLIST.exists():
        return {"app_version": None, "app_build": None}
    try:
        data = plistlib.loads(APP_INFO_PLIST.read_bytes())
    except Exception:
        return {"app_version": None, "app_build": None}
    return {
        "app_version": data.get("CFBundleShortVersionString"),
        "app_build": data.get("CFBundleVersion"),
    }


def discover_users(eastmoney_home: Path) -> List[str]:
    user_root = eastmoney_home / "config" / "user"
    if not user_root.exists():
        return []
    return sorted(
        p.name
        for p in user_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def collect_watchlist_events(
    path: Path,
    name_index: Dict[str, str],
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    obj = read_plist(path)
    if not isinstance(obj, list):
        return events
    for group in obj:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("groupName") or "")
        group_id = str(group.get("groupId") or "")
        group_version = group.get("groupVersion")
        stocks = parse_stock_list(str(group.get("selfStocks") or ""))
        for order_index, stock in enumerate(stocks):
            symbol = stock["symbol"]
            market = stock["market"]
            events.append(
                make_event(
                    kind="watchlist",
                    data={
                        "group": group_name,
                        "group_id": group_id,
                        "group_version": group_version,
                        "group_type": "watchlist",
                        "symbol": symbol,
                        "market": market,
                        "name": name_index.get(symbol),
                        "order_index": order_index,
                        "note": "东方财富本地自选/观察组恢复",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 本地自选数据",
                    time=None,
                    privacy_contains=["portfolio"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=[
                        "vertical/investor/opportunity-watchlist",
                        "vertical/investor/competence-circle",
                    ],
                )
            )
    return events


def collect_recent_stock_events(
    path: Path,
    name_index: Dict[str, str],
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    obj = read_plist(path)
    if not isinstance(obj, list):
        return events
    for order_index, raw in enumerate(obj):
        parsed = parse_stock_token(str(raw))
        if not parsed:
            continue
        events.append(
            make_event(
                kind="recent_stock",
                data={
                    "symbol": parsed["symbol"],
                    "market": parsed["market"],
                    "name": name_index.get(parsed["symbol"]),
                    "order_index": order_index,
                    "note": "东方财富近期查看标的",
                },
                collected_at=collected_at,
                source=f"{source_prefix} 本地近期查看数据",
                privacy_contains=["portfolio"],
                raw_ref={
                    "path_redacted": redacted_path(path),
                    "file_sha256": sha256_file(path),
                },
                wiki_targets=[
                    "vertical/investor/opportunity-watchlist",
                    "vertical/investor/research-consumption",
                ],
            )
        )
    return events


def collect_stock_note_events(
    path: Path,
    name_index: Dict[str, str],
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> Tuple[List[Dict[str, Any]], int]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events, 0
    rows = query_sqlite(path, "select noteId, content, title, date, remindTime, remindType from StockDefine_Table")
    assoc = {
        row.get("noteId"): row
        for row in query_sqlite(
            path,
            "select noteId, stockDescription from StockDefineAssociate_Table",
        )
    }
    for row in rows:
        note_id = str(row.get("noteId") or "")
        text = str(row.get("content") or "")
        title = str(row.get("title") or "")
        related = str((assoc.get(note_id) or {}).get("stockDescription") or "")
        symbol = extract_first_symbol(related)
        events.append(
            make_event(
                kind="stock_note",
                data={
                    "note_id_hash": sha256_text(note_id) if note_id else None,
                    "title": scrub_text(title),
                    "content": scrub_text(text),
                    "date": row.get("date"),
                    "remind_type": row.get("remindType"),
                    "symbol": symbol,
                    "name": name_index.get(symbol) if symbol else None,
                },
                collected_at=collected_at,
                source=f"{source_prefix} 本地股票笔记",
                time=parse_time(row.get("date")),
                privacy_contains=["portfolio"],
                raw_ref={
                    "path_redacted": redacted_path(path),
                    "file_sha256": sha256_file(path),
                },
                wiki_targets=[
                    "vertical/investor/research-consumption",
                    "vertical/investor/decision-framework",
                ],
            )
        )
    return events, len(rows)


def collect_chart_drawing_events(
    path: Path,
    name_index: Dict[str, str],
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> Tuple[List[Dict[str, Any]], int]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events, 0
    rows = query_sqlite(
        path,
        "select graphIndex, graphType, lineType, isLocked, textValue, didConvert from GraphTable",
    )
    for row in rows:
        graph_index = str(row.get("graphIndex") or "")
        symbol = extract_first_symbol(graph_index)
        events.append(
            make_event(
                kind="chart_drawing",
                data={
                    "graph_index_hash": sha256_text(graph_index) if graph_index else None,
                    "graph_type": row.get("graphType"),
                    "line_type": row.get("lineType"),
                    "is_locked": row.get("isLocked"),
                    "text_value": scrub_text(row.get("textValue") or ""),
                    "symbol": symbol,
                    "name": name_index.get(symbol) if symbol else None,
                    "note": "东方财富本地画线/图形标注",
                },
                collected_at=collected_at,
                source=f"{source_prefix} 本地画线数据",
                privacy_contains=["portfolio"],
                raw_ref={
                    "path_redacted": redacted_path(path),
                    "file_sha256": sha256_file(path),
                },
                wiki_targets=[
                    "vertical/investor/research-consumption",
                    "vertical/investor/decision-framework",
                ],
            )
        )
    return events, len(rows)


def collect_panel_events(
    path: Path,
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> Tuple[List[Dict[str, Any]], int]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events, 0
    rows = query_sqlite(
        path,
        "select ZPANELID, ZTITLE, ZTYPE, ZEDITABLE, ZLOCKED, ZCREATIONDATE, ZMODIFICATIONDATE from ZPANELINFO",
    )
    for row in rows:
        panel_id = str(row.get("ZPANELID") or "")
        events.append(
            make_event(
                kind="custom_panel",
                data={
                    "panel_id_hash": sha256_text(panel_id) if panel_id else None,
                    "title": scrub_text(row.get("ZTITLE") or ""),
                    "panel_type": row.get("ZTYPE"),
                    "editable": row.get("ZEDITABLE"),
                    "locked": row.get("ZLOCKED"),
                    "created_at_raw": row.get("ZCREATIONDATE"),
                    "modified_at_raw": row.get("ZMODIFICATIONDATE"),
                    "note": "东方财富自定义面板/看盘工作流线索",
                },
                collected_at=collected_at,
                source=f"{source_prefix} 本地自定义面板",
                privacy_contains=["portfolio"],
                raw_ref={
                    "path_redacted": redacted_path(path),
                    "file_sha256": sha256_file(path),
                },
                wiki_targets=[
                    "vertical/investor/decision-framework",
                    "vertical/investor/opportunity-watchlist",
                ],
            )
        )
    return events, len(rows)


def collect_trade_log_events(
    path: Path,
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    for line_no, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
        event_time = parse_log_time(line)
        preparse_match = re.search(
            r"PreParseReceivedData MSG_(\d+), status=([^,]+), count=([^,]+), msg=\"?([^\"\n]*)",
            line,
        )
        if preparse_match:
            events.append(
                make_event(
                    kind="broker_interface_response",
                    data={
                        "msg_code": preparse_match.group(1),
                        "status_code": preparse_match.group(2).strip(),
                        "record_count": int(preparse_match.group(3)) if preparse_match.group(3).strip().isdigit() else None,
                        "message_summary": scrub_text(preparse_match.group(4).strip()),
                        "note": "交易接口通用响应状态；不包含原始通信负载。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=["vertical/investor/record-review"],
                )
            )

        position_match = re.search(r"CHSStockPosition::OnGetPositionResponse.*count:(\d+),msg:(.*)$", line)
        if position_match:
            count = int(position_match.group(1))
            events.append(
                make_event(
                    kind="broker_position_status",
                    data={
                        "status": "query_success",
                        "position_count": count,
                        "snapshot_type": "broker_confirmed_status_only",
                        "note": "日志确认券商持仓查询成功；未发现逐笔持仓明细落地。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["portfolio", "trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=[
                        "vertical/investor/risk-portfolio",
                        "vertical/investor/record-review",
                    ],
                )
            )
            continue

        asset_match = re.search(r"CHSStockAsset::OnGetAssetResponse.*count:(\d+),msg:(.*)$", line)
        if asset_match:
            count = int(asset_match.group(1))
            events.append(
                make_event(
                    kind="broker_asset_status",
                    data={
                        "status": "query_success",
                        "asset_record_count": count,
                        "snapshot_type": "broker_confirmed_status_only",
                        "note": "日志确认券商资产查询成功；未发现资金金额明细落地。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["money", "portfolio", "trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=[
                        "vertical/investor/risk-portfolio",
                        "vertical/investor/record-review",
                    ],
                )
            )
            continue

        load_match = re.search(r"loadUserInfo.*股票\[([0-9A-Z]+|\(null\))\]", line)
        if load_match and load_match.group(1) != "(null)":
            symbol = load_match.group(1)
            events.append(
                make_event(
                    kind="trade_page_stock_context",
                    data={
                        "symbol": symbol,
                        "market": infer_market(symbol),
                        "status": "trade_page_user_info_loaded",
                        "note": "交易面板加载过该标的上下文；不是成交或委托证据。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["portfolio", "trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=[
                        "vertical/investor/record-review",
                        "vertical/investor/decision-framework",
                    ],
                )
            )
            continue

        if "已有用户登录" in line:
            events.append(
                make_event(
                    kind="broker_login_status",
                    data={
                        "status": "logged_in",
                        "note": "交易模块日志显示已有用户登录；不导出会话或凭证。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=["vertical/investor/profile"],
                )
            )
            continue

        if "暂未开通该市场股东账号" in line or "无此客户代码" in line:
            events.append(
                make_event(
                    kind="broker_market_gap",
                    data={
                        "status": "market_account_unavailable",
                        "message_class": "market_or_customer_code_unavailable",
                        "note": "日志包含市场股东账号/客户代码不可用提示；该日志行不是强交易事实，未写入原始通信内容。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易接口日志",
                    time=event_time,
                    privacy_contains=["trade"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=[
                        "vertical/investor/risk-portfolio",
                        "vertical/investor/record-review",
                    ],
                )
            )
    return events


def collect_sync_log_events(
    path: Path,
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    for line_no, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
        event_time = parse_log_time(line)
        if "sync down self stock" in line and "return data:" in line:
            group_count = len(re.findall(r'"gid"\s*:', line))
            events.append(
                make_event(
                    kind="watchlist_sync_status",
                    data={
                        "status": "sync_down_success",
                        "group_mentions": group_count,
                        "note": "东方财富云端自选同步返回成功；不保存原始返回体。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 自选同步日志",
                    time=event_time,
                    privacy_contains=["portfolio"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=["vertical/investor/opportunity-watchlist"],
                )
            )
        elif "load self stocks of user" in line:
            events.append(
                make_event(
                    kind="watchlist_local_load_status",
                    data={
                        "status": "local_watchlist_loaded",
                        "note": "东方财富加载本地自选数据；采集包保留授权业务数据，不读取登录凭据。",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 自选同步日志",
                    time=event_time,
                    privacy_contains=["portfolio"],
                    raw_ref={
                        "path_redacted": redacted_path(path),
                        "line": line_no,
                        "file_sha256": sha256_file(path),
                    },
                    wiki_targets=["vertical/investor/opportunity-watchlist"],
                )
            )
    return events


def collect_trade_export_events(
    path: Path,
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    try:
        rows = parse_trade_export_file(path)
    except Exception as exc:
        return [
            gap_event(
                collected_at,
                gap="trade_detail_export_parse_failed",
                status="error",
                note=f"交易明细导出文件解析失败：{type(exc).__name__}",
                raw_ref={"path_redacted": redacted_path(path), "file_sha256": sha256_file(path)},
                wiki_targets=["vertical/investor/record-review"],
                source_prefix=source_prefix,
            )
        ]

    for parsed in rows:
        contains = ["portfolio", "trade"]
        if parsed.kind in {"broker_asset_snapshot", "broker_fund_flow"}:
            contains.append("money")
        events.append(
            make_event(
                kind=parsed.kind,
                data=parsed.data,
                collected_at=collected_at,
                source=f"{source_prefix} 交易明细导出",
                time=parse_time(parsed.time),
                privacy_contains=contains,
                raw_ref={
                    "path_redacted": redacted_path(path),
                    "row": parsed.row_number,
                    "file_sha256": sha256_file(path),
                },
                wiki_targets=trade_export_wiki_targets(parsed.kind),
            )
        )
    return events


def collect_trade_ui_events(
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    try:
        snapshot = collect_trade_ui_snapshot(copy_tables=True)
    except Exception as exc:
        snapshot = TradeUISnapshot(
            attempted=True,
            platform_supported=sys.platform == "darwin",
            app_running=False,
            window_found=False,
            trade_page_requested=False,
            account={
                "account_status": "collection_failed",
                "needs_unlock": False,
                "visible_trade_labels": [],
                "observed_fields": {},
                "asset_fields": {},
            },
            gaps=[
                {
                    "gap": "trade_ui_collect_failed",
                    "status": "error",
                    "note": f"东方财富交易页自动采集失败：{type(exc).__name__}",
                }
            ],
        )

    if snapshot.gaps and any(gap.get("gap") == "trade_ui_collect_failed" for gap in snapshot.gaps):
        account_status_event = make_event(
            kind="broker_trade_ui_status",
            data=build_trade_ui_account_data(snapshot),
            collected_at=collected_at,
            source=f"{source_prefix} 交易页自动只读采集",
            privacy_contains=["portfolio", "trade"],
            raw_ref={
                "capture_method": "mac_accessibility_and_table_copy",
                "window_found": snapshot.window_found,
                "ax_line_count": snapshot.ax_line_count,
                "ocr_line_count": snapshot.ocr_line_count,
            },
            wiki_targets=[
                "vertical/investor/risk-portfolio",
                "vertical/investor/record-review",
            ],
        )
        return [
            account_status_event,
            gap_event(
                collected_at,
                gap="trade_ui_collect_failed",
                status="error",
                note=str(snapshot.gaps[0].get("note") or "东方财富交易页自动采集失败。"),
                wiki_targets=["vertical/investor/record-review", "vertical/investor/risk-portfolio"],
                source_prefix=source_prefix,
            )
        ]

    account_data = build_trade_ui_account_data(snapshot)
    events.append(
        make_event(
            kind="broker_trade_ui_status",
            data=account_data,
            collected_at=collected_at,
            source=f"{source_prefix} 交易页自动只读采集",
            privacy_contains=["portfolio", "trade"],
            raw_ref={
                "capture_method": "mac_accessibility_and_table_copy",
                "window_found": snapshot.window_found,
                "ax_line_count": snapshot.ax_line_count,
                "ocr_line_count": snapshot.ocr_line_count,
            },
            wiki_targets=[
                "vertical/investor/risk-portfolio",
                "vertical/investor/record-review",
            ],
        )
    )

    asset_data = build_trade_ui_asset_snapshot(snapshot)
    if asset_data:
        events.append(
            make_event(
                kind="broker_asset_snapshot",
                data=asset_data,
                collected_at=collected_at,
                source=f"{source_prefix} 交易页自动只读采集",
                privacy_contains=["money", "portfolio", "trade"],
                raw_ref={
                    "capture_method": "mac_accessibility_account_fields",
                    "window_found": snapshot.window_found,
                    "ax_line_count": snapshot.ax_line_count,
                    "ocr_line_count": snapshot.ocr_line_count,
                },
                wiki_targets=trade_export_wiki_targets("broker_asset_snapshot"),
            )
        )

    for table in snapshot.tables:
        if table.status == "confirmed_empty":
            events.append(
                make_event(
                    kind="broker_trade_table_status",
                    data={
                        "profile_type": "eastmoney_trade_ui_confirmed_empty_table",
                        "tab": table.tab,
                        "label": table.label,
                        "source_kind_for_table": table.kind,
                        "status": table.status,
                        "row_count": 0,
                        "headers_detected": True,
                        "snapshot_type": "broker_ui_accessibility_confirmed",
                        "evidence_level": "confirmed_gui",
                    },
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易页自动只读采集 / {table.label}",
                    privacy_contains=["portfolio", "trade"],
                    raw_ref={
                        "capture_method": "ui_accessibility_table_headers",
                        "ui_tab": table.label,
                        "copied_text_chars": table.copied_text_chars,
                    },
                    wiki_targets=trade_export_wiki_targets(table.kind),
                )
            )
            continue
        for parsed in table.rows:
            contains = ["portfolio", "trade"]
            if parsed.kind in {"broker_asset_snapshot", "broker_fund_flow"}:
                contains.append("money")
            events.append(
                make_event(
                    kind=parsed.kind,
                    data=parsed.data,
                    collected_at=collected_at,
                    source=f"{source_prefix} 交易页自动只读采集",
                    time=parse_time(parsed.time),
                    privacy_contains=contains,
                    raw_ref={
                        "capture_method": "ui_table_copy",
                        "ui_tab": table.label,
                        "row": parsed.row_number,
                        "copied_text_chars": table.copied_text_chars,
                    },
                    wiki_targets=trade_export_wiki_targets(parsed.kind),
                )
            )

    for gap in snapshot.gaps:
        events.append(
            gap_event(
                collected_at,
                gap=str(gap.get("gap") or "trade_ui_unknown_gap"),
                status=str(gap.get("status") or "not_found"),
                note=str(gap.get("note") or "东方财富交易页自动采集未取得数据。"),
                raw_ref={"capture_method": "mac_accessibility_and_table_copy"},
                wiki_targets=[
                    "vertical/investor/risk-portfolio",
                    "vertical/investor/record-review",
                ],
                source_prefix=source_prefix,
            )
        )
    return events


def build_trade_ui_account_data(snapshot: TradeUISnapshot) -> Dict[str, Any]:
    account = snapshot.account or {}
    account_label = str(account.get("account_label") or "")
    numeric_asset_keys = {
        "total_asset",
        "market_value",
        "profit_loss",
        "day_profit_loss",
        "available_cash",
        "withdrawable_cash",
        "frozen_cash",
        "cash_balance",
    }
    asset_fields = account.get("asset_fields") or {}
    table_statuses = [
        {
            "tab": table.tab,
            "label": table.label,
            "status": table.status,
            "row_count": len(table.rows),
            "copied_text_chars": table.copied_text_chars,
        }
        for table in snapshot.tables
    ]
    data = {
        "status": "attempted" if snapshot.attempted else "not_attempted",
        "platform_supported": snapshot.platform_supported,
        "app_running": snapshot.app_running,
        "window_found": snapshot.window_found,
        "trade_page_requested": snapshot.trade_page_requested,
        "account_status": account.get("account_status") or "unknown",
        "needs_unlock": bool(account.get("needs_unlock")),
        "accessibility_status": "readable" if snapshot.ax_line_count else "empty",
        "accessibility_line_count": snapshot.ax_line_count,
        "screen_ocr_line_count": snapshot.ocr_line_count,
        "status_evidence": account.get("status_evidence") or (
            "mac_accessibility" if snapshot.ax_line_count else ""
        ),
        "visible_trade_labels": account.get("visible_trade_labels") or [],
        "observed_field_count": len(account.get("observed_fields") or {}),
        "asset_field_count": sum(1 for key in numeric_asset_keys if key in asset_fields),
        "table_statuses": table_statuses,
        "note": "东方财富交易页自动只读采集状态；不包含交易密码、会话凭据或原始接口负载。",
    }
    if account_label:
        suffix = extract_account_suffix(account_label)
        data["account_label"] = account_label
        data["account_display_hash"] = sha256_text(account_label)
        if suffix:
            data["account_suffix"] = suffix
    return data


def build_trade_ui_asset_snapshot(snapshot: TradeUISnapshot) -> Dict[str, Any]:
    account = snapshot.account or {}
    asset_fields = dict(account.get("asset_fields") or {})
    numeric_keys = {
        "total_asset",
        "market_value",
        "profit_loss",
        "day_profit_loss",
        "available_cash",
        "withdrawable_cash",
        "frozen_cash",
        "cash_balance",
    }
    if not any(key in asset_fields for key in numeric_keys):
        return {}

    data = {
        "snapshot_type": "broker_ui_accessibility_confirmed",
        "account_status": account.get("account_status") or "unknown",
        **asset_fields,
    }
    account_label = str(account.get("account_label") or "")
    if account_label:
        data["account_label"] = account_label
        data["account_display_hash"] = sha256_text(account_label)
        suffix = extract_account_suffix(account_label)
        if suffix:
            data["account_suffix"] = suffix
    return scrub_value(data)


def extract_account_suffix(account_label: str) -> Optional[str]:
    match = re.search(r"\((\d{2,})\)", account_label or "")
    return match.group(1) if match else None


def trade_export_wiki_targets(kind: str) -> List[str]:
    if kind in {"broker_asset_snapshot", "broker_position_detail"}:
        return ["vertical/investor/risk-portfolio", "vertical/investor/record-review"]
    if kind in {"broker_trade_execution", "broker_entrust_order", "broker_fund_flow"}:
        return ["vertical/investor/record-review", "vertical/investor/decision-framework"]
    return ["vertical/investor/record-review"]


def add_global_gap_events(
    events: List[Dict[str, Any]],
    collected_at: str,
    source_prefix: str = "东方财富 Mac",
) -> None:
    kinds = Counter(event["kind"] for event in events)
    ui_attempted = bool(kinds.get("broker_trade_ui_status")) or any(
        event["kind"] == "data_gap" and str(event["data"].get("gap", "")).startswith("trade_ui_")
        for event in events
    )
    ui_locked = any(
        event["kind"] == "broker_trade_ui_status"
        and event["data"].get("account_status") == "locked"
        for event in events
    )
    ui_copy_blocked = any(
        event["kind"] == "data_gap"
        and str(event["data"].get("gap", "")).startswith("trade_ui_")
        for event in events
    )
    ui_table_statuses = {
        table.get("tab"): table.get("status")
        for event in events
        if event["kind"] == "broker_trade_ui_status"
        for table in event["data"].get("table_statuses", [])
        if isinstance(table, dict)
    }
    trade_tables_confirmed_empty = (
        ui_table_statuses.get("executions") == "confirmed_empty"
        and ui_table_statuses.get("entrusts") == "confirmed_empty"
    )
    ui_accessibility_blocked = any(
        event["kind"] == "data_gap"
        and event["data"].get("gap") == "trade_ui_accessibility_tree_empty"
        for event in events
    )
    if not kinds.get("broker_position_status"):
        events.append(
            gap_event(
                collected_at,
                gap="broker_position_status_missing",
                status="not_found",
                note="未在东方财富本地文件中发现券商持仓查询状态。",
                wiki_targets=["vertical/investor/risk-portfolio"],
                source_prefix=source_prefix,
            )
        )
    if not kinds.get("broker_asset_status"):
        events.append(
            gap_event(
                collected_at,
                gap="broker_asset_status_missing",
                status="not_found",
                note="未在东方财富本地文件中发现券商资产查询状态。",
                wiki_targets=["vertical/investor/risk-portfolio"],
                source_prefix=source_prefix,
            )
        )
    if not kinds.get("broker_position_detail"):
        positive_status = any(
            event["kind"] == "broker_position_status"
            and (event["data"].get("position_count") or 0) > 0
            for event in events
        )
        if positive_status:
            events.append(
                gap_event(
                    collected_at,
                    gap="broker_position_detail_not_materialized",
                    status="not_found",
                    note=missing_trade_detail_note(
                        ui_attempted,
                        ui_locked,
                        ui_accessibility_blocked,
                        ui_copy_blocked,
                        "交易日志显示存在持仓记录，但自动采集未取得逐笔持仓明细。",
                    ),
                    wiki_targets=["vertical/investor/risk-portfolio"],
                    source_prefix=source_prefix,
                )
            )
    if (
        not kinds.get("broker_trade_execution")
        and not kinds.get("broker_entrust_order")
        and not trade_tables_confirmed_empty
    ):
        events.append(
            gap_event(
                collected_at,
                gap="broker_trade_detail_not_materialized",
                status="not_found",
                note=missing_trade_detail_note(
                    ui_attempted,
                    ui_locked,
                    ui_accessibility_blocked,
                    ui_copy_blocked,
                    "未发现可安全解析的成交/委托明细。",
                ),
                wiki_targets=[
                    "vertical/investor/record-review",
                    "vertical/investor/decision-framework",
                ],
                source_prefix=source_prefix,
            )
        )
    if not kinds.get("broker_asset_snapshot"):
        events.append(
            gap_event(
                collected_at,
                gap="asset_amounts_not_materialized",
                status="not_found",
                note=missing_trade_detail_note(
                    ui_attempted,
                    ui_locked,
                    ui_accessibility_blocked,
                    ui_copy_blocked,
                    "资产查询状态存在，但未取得可用资金、总资产、市值、盈亏等金额字段。",
                ),
                wiki_targets=["vertical/investor/risk-portfolio"],
                source_prefix=source_prefix,
            )
        )


def missing_trade_detail_note(
    ui_attempted: bool,
    ui_locked: bool,
    ui_accessibility_blocked: bool,
    ui_copy_blocked: bool,
    base: str,
) -> str:
    if ui_locked:
        return f"{base} 东方财富交易页显示证券账户已锁定，采集器不会读取或请求交易密码。"
    if ui_accessibility_blocked:
        return f"{base} 东方财富窗口已打开，但 macOS 未返回可读取控件；请确认交易页已解锁、窗口在前台，并允许辅助功能访问。"
    if ui_copy_blocked:
        return f"{base} 自动交易页表格复制未返回可解析内容。"
    if ui_attempted:
        return f"{base} 自动交易页采集已执行，但没有形成强交易明细事件。"
    return f"{base} 本次未启用自动交易页采集；FinClaw 一键采集应启用 --auto-trade-ui。"


def load_stock_name_index(db_path: Path) -> Dict[str, str]:
    if not db_path.exists():
        return {}
    index: Dict[str, str] = {}
    try:
        con = sqlite3.connect(str(db_path))
        for code, name in con.execute(
            "select stock_code, stock_name from stock_form_name where is_valid=1"
        ):
            if code and name and code not in index:
                index[str(code)] = str(name)
        con.close()
    except sqlite3.Error:
        return {}
    return index


def parse_stock_list(raw: str) -> List[Dict[str, str]]:
    return [item for item in (parse_stock_token(token) for token in raw.split(";")) if item]


def parse_stock_token(raw: str) -> Optional[Dict[str, str]]:
    raw = raw.strip().replace("$", ":")
    if not raw or ":" not in raw:
        return None
    market_code, symbol = raw.split(":", 1)
    symbol = symbol.strip()
    if not re.fullmatch(r"[0-9A-Z._-]{2,12}", symbol):
        return None
    return {
        "market_code": market_code,
        "market": MARKET_MAP.get(market_code, market_code),
        "symbol": symbol,
    }


def infer_market(symbol: str) -> Optional[str]:
    if not symbol:
        return None
    if symbol.startswith(("6", "9")):
        return "SH"
    if symbol.startswith(("0", "2", "3")):
        return "SZ"
    if symbol.startswith(("4", "8")):
        return "BJ"
    return None


def query_sqlite(path: Path, sql: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        con = sqlite3.connect(str(path))
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute(sql)]
        con.close()
        return rows
    except sqlite3.Error:
        return []


def read_plist(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return plistlib.loads(path.read_bytes())
    except Exception:
        return None


def make_event(
    kind: str,
    data: Dict[str, Any],
    collected_at: str,
    source: str,
    privacy_contains: Iterable[str],
    raw_ref: Optional[Dict[str, Any]] = None,
    time: Optional[str] = None,
    wiki_targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    payload = {
        "kind": kind,
        "time": time,
        "data": data,
        "source": source,
    }
    event_id = f"{COLLECTOR}:{sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))[:24]}"
    return {
        "schema": EVENT_SCHEMA,
        "id": event_id,
        "collector": COLLECTOR,
        "collected_at": collected_at,
        "kind": kind,
        "time": time,
        "source": source,
        "owner_scope": "personal",
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": sorted(set(privacy_contains)),
        },
        "data": scrub_value(data),
        "raw_ref": scrub_value(raw_ref or {}),
        "wiki_targets": canonical_wiki_targets(kind, wiki_targets or []),
    }


def canonical_wiki_targets(source_kind: str, targets: Iterable[str]) -> List[str]:
    mapped: List[str] = []
    for target in targets:
        mapped.extend(LEGACY_WIKI_TARGET_MAP.get(target, [target]))
    mapped.extend(SOURCE_KIND_EXTRA_WIKI_TARGETS.get(source_kind, []))
    return sorted({target for target in mapped if target})


def collectorx_kind_for_source(source_kind: str) -> str:
    if source_kind in COLLECTORX_ALLOWED_KINDS:
        return source_kind
    return SOURCE_KIND_TO_COLLECTORX_KIND.get(source_kind, "profile")


def normalize_event_for_lake(event: Dict[str, Any]) -> Dict[str, Any]:
    normalized = json.loads(json.dumps(event, ensure_ascii=False))
    source_kind = str(normalized.get("kind") or "other")
    data = normalized.setdefault("data", {})
    if isinstance(data, dict):
        data.setdefault("source_kind", source_kind)
    normalized["kind"] = collectorx_kind_for_source(source_kind)
    normalized["wiki_targets"] = canonical_wiki_targets(source_kind, normalized.get("wiki_targets") or [])
    return normalized


def gap_event(
    collected_at: str,
    gap: str,
    status: str,
    note: str,
    raw_ref: Optional[Dict[str, Any]] = None,
    wiki_targets: Optional[List[str]] = None,
    source_prefix: str = "东方财富 Mac",
) -> Dict[str, Any]:
    return make_event(
        kind="data_gap",
        data={
            "gap": gap,
            "status": status,
            "note": note,
        },
        collected_at=collected_at,
        source=f"{source_prefix} 本地采集边界",
        privacy_contains=["portfolio"],
        raw_ref=raw_ref or {},
        wiki_targets=wiki_targets or [],
    )


def dedupe_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for event in events:
        if event["id"] in seen:
            continue
        seen.add(event["id"])
        result.append(event)
    return result


def write_package(
    output_dir: Path,
    events: List[Dict[str, Any]],
    sources: List[SourceFile],
    collected_at: str,
    eastmoney_home: Path,
    platform_meta: Optional[Dict[str, Any]] = None,
) -> None:
    lake_dir = output_dir / "lake" / COLLECTOR
    lake_dir.mkdir(parents=True, exist_ok=True)
    events_path = lake_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(normalize_event_for_lake(event), ensure_ascii=False, sort_keys=True) + "\n")
    profile = build_profile(events, sources, collected_at, eastmoney_home, platform_meta)
    write_json(output_dir / "structured_profile.json", profile)


def build_profile(
    events: List[Dict[str, Any]],
    sources: List[SourceFile],
    collected_at: str,
    eastmoney_home: Path,
    platform_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    watch_groups: Dict[str, int] = Counter(
        event["data"].get("group")
        for event in events
        if event["kind"] == "watchlist"
    )
    recent = [
        event["data"]
        for event in events
        if event["kind"] == "recent_stock"
    ]
    broker_status = [
        event["data"]
        for event in events
        if event["kind"] in {"broker_position_status", "broker_asset_status", "broker_market_gap"}
    ]
    asset_snapshots = [
        event["data"]
        for event in events
        if event["kind"] == "broker_asset_snapshot"
    ]
    positions = [
        event["data"]
        for event in events
        if event["kind"] == "broker_position_detail"
    ]
    trade_executions = [
        event["data"]
        for event in events
        if event["kind"] == "broker_trade_execution"
    ]
    entrust_orders = [
        event["data"]
        for event in events
        if event["kind"] == "broker_entrust_order"
    ]
    fund_flows = [
        event["data"]
        for event in events
        if event["kind"] == "broker_fund_flow"
    ]
    trade_ui_statuses = [
        event["data"]
        for event in events
        if event["kind"] == "broker_trade_ui_status"
    ]
    return {
        "schema": "eastmoney.investor_v2_collect.profile.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at,
        "local_platform": platform_meta or {},
        "collection_readiness": build_collection_readiness(events),
        "source_home_redacted": redacted_path(eastmoney_home),
        "event_counts": dict(sorted(counts.items())),
        "watch_groups": {
            (k or "").strip(): v
            for k, v in sorted(watch_groups.items(), key=lambda item: item[0] or "")
        },
        "recent_stock_sample": recent[:20],
        "broker_status": broker_status[:20],
        "asset_snapshot_sample": asset_snapshots[:5],
        "position_sample": positions[:50],
        "trade_execution_sample": trade_executions[:50],
        "entrust_order_sample": entrust_orders[:50],
        "fund_flow_sample": fund_flows[:50],
        "trade_ui_status_sample": trade_ui_statuses[:5],
        "sources": [s.manifest_entry() for s in sources],
    }


def build_manifest(
    output_dir: Path,
    events: List[Dict[str, Any]],
    sources: List[SourceFile],
    collected_at: str,
    platform_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    return {
        "schema": MANIFEST_SCHEMA,
        "collector": COLLECTOR,
        "collected_at": collected_at,
        "local_platform": platform_meta or {},
        "design_principle": (
            "Collect evidence for investor decision-chain, not generic identity data. "
            "Strong evidence is separated from weak/default-template evidence and gaps."
        ),
        "evidence_strength": {
            "strong": [
                "broker_position_status",
                "broker_asset_status",
                "broker_asset_snapshot",
                "broker_position_detail",
                "broker_trade_execution",
                "broker_entrust_order",
                "broker_fund_flow",
                "csv_trade_import",
            ],
            "medium": [
                "watchlist",
                "recent_stock",
                "watchlist_sync_status",
                "stock_note",
            ],
            "weak": [
                "trade_page_stock_context",
                "custom_panel",
                "chart_drawing",
                "broker_login_status",
                "broker_interface_response",
            ],
            "gap": [
                "broker_trade_ui_status",
                "data_gap",
                "broker_market_gap",
            ],
            "excluded": [
                "密码",
                "浏览器登录材料",
                "接口令牌",
                "签名",
                "会话凭据",
                "票据凭据",
                "设备标识",
                "设备详情",
                "原始 HTTP 存储库",
                "原始 WebKit 网站数据",
                "原始交易通信负载",
            ],
        },
        "source_counts": {
            "total_events": len(events),
            **dict(sorted(counts.items())),
        },
        "collection_readiness": build_collection_readiness(events),
        "sources": [s.manifest_entry() for s in sources],
        "outputs": {
            "events": str(output_dir / "lake" / COLLECTOR / "events.jsonl"),
            "structured_profile": str(output_dir / "structured_profile.json"),
            "investor_wiki_evidence": str(output_dir / "investor_wiki_evidence.v1.json"),
            "summary": str(output_dir / "SUMMARY.md"),
            "soulmirror_wiki": str(output_dir / "wiki" / "external" / "investor"),
            "legacy_vertical_wiki": str(output_dir / "wiki" / "vertical" / "investor"),
        },
    }


INVESTOR_DIMENSION_CONTRACT = [
    {
        "dimension_id": "inv-philosophy",
        "dimension_name": "投资哲学与信念",
        "children": [
            ("market-view", "市场观", ["watchlist", "recent_stock", "stock_note"]),
            ("risk-view", "风险观", ["broker_asset_snapshot", "broker_position_detail", "broker_trade_execution"]),
            ("value-preference", "价值偏好", ["watchlist", "stock_note", "broker_position_detail"]),
        ],
    },
    {
        "dimension_id": "inv-circle",
        "dimension_name": "能力圈定义",
        "children": [
            ("industry-circle", "行业能力圈", ["watchlist", "recent_stock", "broker_position_detail", "broker_trade_execution"]),
            ("analysis-ability", "分析能力", ["stock_note", "chart_drawing", "custom_panel"]),
            ("information-learning-style", "信息处理与学习风格", ["recent_stock", "stock_note", "chart_drawing", "custom_panel"]),
        ],
    },
    {
        "dimension_id": "inv-style",
        "dimension_name": "投资风格与策略",
        "children": [
            ("style-profile", "风格画像", ["broker_trade_execution", "broker_position_detail", "broker_asset_snapshot"]),
            ("buy-framework", "买入决策框架", ["broker_trade_execution", "broker_entrust_order", "stock_note"]),
            ("sell-framework", "卖出决策框架", ["broker_trade_execution", "broker_entrust_order", "stock_note"]),
        ],
    },
    {
        "dimension_id": "inv-behavior",
        "dimension_name": "行为特征与偏差画像",
        "children": [
            ("cognitive-bias", "认知偏差档案", ["broker_trade_execution", "broker_entrust_order"]),
            ("emotion-pattern", "情绪模式", ["stock_note"]),
            ("decision-adaptation-style", "决策与适应风格", ["broker_trade_execution", "broker_entrust_order", "trade_page_stock_context"]),
        ],
    },
    {
        "dimension_id": "inv-review",
        "dimension_name": "决策记录与复盘系统",
        "children": [
            ("decision-log", "决策日志", ["broker_trade_execution", "broker_entrust_order", "broker_fund_flow"]),
            ("review-record", "复盘记录", ["stock_note"]),
            ("rules-library", "投资规则库", ["stock_note", "chart_drawing", "custom_panel"]),
        ],
    },
    {
        "dimension_id": "inv-portfolio",
        "dimension_name": "组合与执行",
        "children": [
            ("portfolio-preference", "组合管理偏好", ["broker_asset_snapshot", "broker_position_detail"]),
            ("execution-discipline", "执行纪律", ["broker_trade_execution", "broker_entrust_order"]),
            ("time-preference", "时间偏好", ["broker_trade_execution", "broker_entrust_order", "recent_stock"]),
        ],
    },
    {
        "dimension_id": "inv-network",
        "dimension_name": "信息网络与人脉",
        "children": [
            ("information-source", "信息源", ["recent_stock", "stock_note", "custom_panel"]),
            ("consultation-network", "咨询对象", ["investment_message", "research_meeting"]),
        ],
    },
]

STRONG_TRADE_KINDS = {
    "broker_asset_snapshot",
    "broker_position_detail",
    "broker_trade_execution",
    "broker_entrust_order",
    "broker_fund_flow",
}

MEDIUM_INVESTOR_KINDS = {"watchlist", "recent_stock", "stock_note", "chart_drawing", "custom_panel"}
WEAK_INVESTOR_KINDS = {
    "trade_page_stock_context",
    "broker_position_status",
    "broker_asset_status",
    "broker_login_status",
    "broker_interface_response",
}


def build_collection_readiness(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    gaps = {
        str(event["data"].get("gap"))
        for event in events
        if event["kind"] == "data_gap" and event["data"].get("gap")
    }
    ui_status = next((event["data"] for event in events if event["kind"] == "broker_trade_ui_status"), {})
    account_status = ui_status.get("account_status") or "unknown"
    trade_ui_attempted = bool(ui_status) or any(gap.startswith("trade_ui_") for gap in gaps)
    required = {
        "asset_snapshot": counts.get("broker_asset_snapshot", 0),
        "position_detail": counts.get("broker_position_detail", 0),
        "trade_execution": counts.get("broker_trade_execution", 0),
        "entrust_order": counts.get("broker_entrust_order", 0),
        "fund_flow": counts.get("broker_fund_flow", 0),
    }
    table_statuses = {
        table.get("tab"): table.get("status")
        for table in ui_status.get("table_statuses", [])
        if isinstance(table, dict)
    }
    table_materialized = {
        "asset_snapshot": required["asset_snapshot"] > 0,
        "position_detail": required["position_detail"] > 0 or table_statuses.get("positions") == "confirmed_empty",
        "trade_execution": required["trade_execution"] > 0 or table_statuses.get("executions") == "confirmed_empty",
        "entrust_order": required["entrust_order"] > 0 or table_statuses.get("entrusts") == "confirmed_empty",
        "fund_flow": required["fund_flow"] > 0 or table_statuses.get("funds") == "confirmed_empty",
    }
    missing_required = [name for name, ready in table_materialized.items() if not ready]
    strong_total = sum(required.values())
    accessibility_blocked = "trade_ui_accessibility_tree_empty" in gaps
    if not missing_required:
        status = "ready_for_investor_avatar"
        next_action = "可进入 FinClaw 投资分身蒸馏；继续结合投研笔记、聊天和复盘补原因层。"
    elif account_status == "locked" or "broker_account_locked" in gaps:
        status = "blocked_by_account_lock"
        next_action = "在东方财富交易页手动解锁证券账户后，重新运行 FinClaw 一键采集；采集器不会读取或请求交易密码。"
    elif account_status == "collection_failed" or "trade_ui_collect_failed" in gaps:
        status = "trade_ui_collect_failed"
        next_action = "东方财富交易页自动采集已尝试但被窗口/可访问性超时阻塞；确认客户端主窗口可见并授予辅助功能权限后重试。"
    elif not trade_ui_attempted:
        status = "auto_trade_ui_not_run"
        next_action = "运行时启用 --auto-trade-ui，让采集器自动打开交易页并只读采集强交易表。"
    elif strong_total:
        status = "partial_strong_trade_data"
        next_action = "已取得部分强交易事实；重新运行采集以补齐缺失的资产、持仓、成交、委托或资金流水表。"
    elif accessibility_blocked:
        status = "trade_ui_accessibility_blocked"
        next_action = "交易页已打开，但系统没有返回可读取控件；请确认东方财富交易页在前台、证券账户已解锁，并检查 macOS 辅助功能权限后重跑。"
    else:
        status = "strong_trade_data_missing"
        next_action = "交易页已尝试但没有形成强交易明细；需确认交易页已解锁且表格可见，再重新运行。"

    return {
        "status": status,
        "finclaw_stage": "beta" if missing_required else "production_candidate",
        "can_enter_finclaw": True,
        "can_claim_complete_trade_collection": not missing_required,
        "needs_manual_export": False,
        "account_status": account_status,
        "required_strong_tables": required,
        "required_strong_table_statuses": table_statuses,
        "required_strong_table_materialized": table_materialized,
        "missing_required_strong_tables": missing_required,
        "strong_trade_event_count": strong_total,
        "gap_count": len(gaps),
        "next_action": next_action,
    }


def build_investor_wiki_evidence(events: List[Dict[str, Any]], generated_at: str) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    lake_kinds = Counter(normalize_event_for_lake(event)["kind"] for event in events)
    dimensions = []
    for dim in INVESTOR_DIMENSION_CONTRACT:
        children = []
        for sub_id, sub_name, kinds in dim["children"]:
            evidence_count = sum(counts.get(kind, 0) for kind in kinds)
            present_kinds = [kind for kind in kinds if counts.get(kind, 0)]
            support_level = investor_support_level(present_kinds)
            children.append(
                {
                    "subdimension_id": sub_id,
                    "subdimension_name": sub_name,
                    "support_level": support_level,
                    "suggested_maturity": suggested_maturity_for_support(support_level),
                    "evidence_count": evidence_count,
                    "evidence_kinds": present_kinds,
                    "route_targets": routes_for_kinds(present_kinds),
                    "signals": investor_signals_for_subdimension(sub_id, present_kinds),
                    "gaps": investor_gaps_for_subdimension(sub_id, present_kinds),
                    "privacy": {
                        "local_only": True,
                        "sensitive": any(kind in STRONG_TRADE_KINDS for kind in present_kinds),
                    },
                }
            )
        dimensions.append(
            {
                "dimension_id": dim["dimension_id"],
                "dimension_name": dim["dimension_name"],
                "children": children,
            }
        )
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at,
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": EVENT_SCHEMA,
            "event_count": len(events),
            "source_kind_counts": dict(sorted(counts.items())),
            "lake_kind_counts": dict(sorted(lake_kinds.items())),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": [
                "collectorx.event.v1",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
                "schema-controlled markdown wiki",
            ],
        },
        "dimension_model": {
            "major_dimension_count": 7,
            "product_subdimension_count": 20,
            "schema_parent": "external.investor",
        },
        "collection_readiness": build_collection_readiness(events),
        "dimensions": dimensions,
    }


def write_investor_wiki_evidence(output_dir: Path, events: List[Dict[str, Any]], generated_at: str) -> None:
    write_json(output_dir / "investor_wiki_evidence.v1.json", build_investor_wiki_evidence(events, generated_at))


def investor_support_level(kinds: List[str]) -> str:
    if any(kind in STRONG_TRADE_KINDS for kind in kinds):
        return "strong"
    if any(kind in MEDIUM_INVESTOR_KINDS for kind in kinds):
        return "medium"
    if any(kind in WEAK_INVESTOR_KINDS for kind in kinds):
        return "weak"
    return "none"


def suggested_maturity_for_support(level: str) -> str:
    return {
        "strong": "basic",
        "medium": "hint",
        "weak": "hint",
        "none": "empty",
    }.get(level, "empty")


def routes_for_kinds(kinds: List[str]) -> List[str]:
    routes: List[str] = []
    for kind in kinds:
        routes.extend(SOURCE_KIND_EXTRA_WIKI_TARGETS.get(kind, []))
    return sorted(set(routes))


def investor_signals_for_subdimension(sub_id: str, kinds: List[str]) -> List[str]:
    if not kinds:
        return []
    signals_by_sub = {
        "decision-log": "可形成交易时间线、委托状态和资金变化索引。",
        "portfolio-preference": "可形成资产、持仓、集中度和现金暴露画像。",
        "style-profile": "可从成交、持仓和资产结构观察交易频率、仓位和风格。",
        "industry-circle": "可从自选、近期查看、持仓和成交标的观察关注宇宙。",
        "execution-discipline": "可从成交与委托的数量、价格、状态观察执行纪律。",
        "information-source": "可从近期查看、笔记和面板观察信息入口。",
    }
    return [signals_by_sub.get(sub_id, "已有东方财富个人证据可作为该节点的保守画像输入。")]


def investor_gaps_for_subdimension(sub_id: str, kinds: List[str]) -> List[str]:
    gaps = []
    if not kinds:
        gaps.append("当前东方财富采集未取得该子维度的直接个人证据。")
    if sub_id in {"market-view", "risk-view", "value-preference", "emotion-pattern", "review-record", "consultation-network"}:
        gaps.append("需要结合投研笔记、聊天、会议纪要或盘后复盘补充原因层证据。")
    if sub_id in {"decision-log", "portfolio-preference", "execution-discipline"} and not any(kind in STRONG_TRADE_KINDS for kind in kinds):
        gaps.append("需要解锁交易页后采集资产、持仓、成交、委托或资金流水强事实。")
    return gaps


def write_summary(output_dir: Path, manifest: Dict[str, Any], events: List[Dict[str, Any]]) -> None:
    counts = Counter(event["kind"] for event in events)
    watch_count = counts.get("watchlist", 0)
    group_count = len({
        event["data"].get("group")
        for event in events
        if event["kind"] == "watchlist"
    })
    recent_count = counts.get("recent_stock", 0)
    position_statuses = [
        event["data"]
        for event in events
        if event["kind"] == "broker_position_status"
    ]
    asset_statuses = [
        event["data"]
        for event in events
        if event["kind"] == "broker_asset_status"
    ]
    asset_snapshot_count = counts.get("broker_asset_snapshot", 0)
    position_detail_count = counts.get("broker_position_detail", 0)
    trade_execution_count = counts.get("broker_trade_execution", 0)
    entrust_order_count = counts.get("broker_entrust_order", 0)
    fund_flow_count = counts.get("broker_fund_flow", 0)
    trade_ui_status_count = counts.get("broker_trade_ui_status", 0)
    gaps = [
        event["data"].get("gap")
        for event in events
        if event["kind"] == "data_gap"
    ]
    platform_meta = manifest.get("local_platform") or {}
    resolved_platform = platform_meta.get("resolved") or "mac"
    structure_status = platform_meta.get("structure_status") or "unknown"
    source_prefix = LOCAL_SOURCE_PREFIX_BY_PLATFORM.get(resolved_platform, "东方财富本机")
    strong_trade_count = sum([asset_snapshot_count, position_detail_count, trade_execution_count, entrust_order_count, fund_flow_count])
    readiness = build_collection_readiness(events)
    if strong_trade_count:
        trade_export_note = "交易接口状态日志、交易页自动只读采集或兼容明细输入形成的强明细事件；FinClaw 主路径仍是自动交易页。"
    elif trade_ui_status_count:
        trade_export_note = "交易接口状态日志、交易页自动只读采集状态；本次未形成资产/持仓/成交/委托/资金强明细。"
    else:
        trade_export_note = "交易接口状态日志；FinClaw 一键深采应启用 --auto-trade-ui 自动读取交易页。"
    lines = [
        "# 东方财富投资行为采集报告",
        "",
        f"- 采集器：`{COLLECTOR}`",
        f"- 采集时间：`{manifest['collected_at']}`",
        f"- 平台适配：`{resolved_platform}` / `{structure_status}`",
        f"- 总事件：`{len(events)}`",
        f"- 自选标的：`{watch_count}` 条，`{group_count}` 个分组",
        f"- 近期查看：`{recent_count}` 条",
        f"- 持仓查询状态事件：`{len(position_statuses)}` 条",
        f"- 资产查询状态事件：`{len(asset_statuses)}` 条",
        f"- 交易页自动采集状态：`{trade_ui_status_count}` 条",
        f"- 资产快照：`{asset_snapshot_count}` 条",
        f"- 持仓明细：`{position_detail_count}` 条",
        f"- 成交明细：`{trade_execution_count}` 条",
        f"- 委托明细：`{entrust_order_count}` 条",
        f"- 资金流水：`{fund_flow_count}` 条",
        f"- FinClaw 状态：`{readiness['finclaw_stage']}` / `{readiness['status']}`",
        f"- 强交易表缺口：`{', '.join(readiness['missing_required_strong_tables']) or 'none'}`",
        "",
        "## 数据边界",
        "",
        f"- 已采：{source_prefix} 本地自选、近期查看、股票笔记/画线/面板结构、{trade_export_note}",
        "- 已排除：浏览器登录材料、接口令牌、会话凭据、签名、设备指纹、原始交易通信负载、HTTP 存储。",
        "- 重要边界：如果本地日志只证明“查询成功/为空”，输出只记录状态，不补写金额或持仓明细。",
        f"- 下一步：{readiness['next_action']}",
        "",
        "## 事件分布",
        "",
    ]
    for kind, count in sorted(counts.items()):
        lines.append(f"- `{kind}`: {count}")
    lines.extend(["", "## 缺口", ""])
    for gap in gaps:
        lines.append(f"- `{gap}`")
    lines.append("")
    (output_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_wiki(output_dir: Path, events: List[Dict[str, Any]]) -> None:
    roots = [
        output_dir / "wiki" / "external" / "investor",
        output_dir / "wiki" / "vertical" / "investor",
    ]
    for root in roots:
        write_watchlist_wiki(root, events)
        write_trade_status_wiki(root, events)
        write_risk_boundary_wiki(root, events)
        write_research_wiki(root, events)


def wiki_doc(
    title: str,
    body_lines: List[str],
    *,
    source: str = COLLECTOR,
    maturity: str = "hint",
    evidence_level: str = "medium",
    targets: Optional[List[str]] = None,
) -> str:
    frontmatter = [
        "---",
        f"maturity: {maturity}",
        f"source: {source}",
        f"collector: {COLLECTOR}",
        f"evidence_level: {evidence_level}",
    ]
    if targets:
        frontmatter.append("wiki_targets:")
        for target in targets:
            frontmatter.append(f"  - {target}")
    frontmatter.extend(["---", "", f"# {title}", ""])
    return "\n".join([*frontmatter, *body_lines])


def write_watchlist_wiki(root: Path, events: List[Dict[str, Any]]) -> None:
    watch = [e for e in events if e["kind"] == "watchlist"]
    recent = [e for e in events if e["kind"] == "recent_stock"]
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for event in watch:
        groups.setdefault(event["data"].get("group") or "未命名", []).append(event["data"])
    lines: List[str] = []
    lines.append(f"- 自选事件：{len(watch)}")
    lines.append(f"- 近期查看：{len(recent)}")
    lines.append("")
    for group, items in sorted(groups.items()):
        lines.append(f"## {group}")
        for item in items[:120]:
            name = item.get("name") or ""
            lines.append(f"- {item.get('market') or ''} {item.get('symbol')} {name}".rstrip())
        lines.append("")
    if recent:
        lines.append("## 近期查看")
        for event in recent:
            item = event["data"]
            name = item.get("name") or ""
            lines.append(f"- {item.get('market') or ''} {item.get('symbol')} {name}".rstrip())
        lines.append("")
    write_text(
        root / "opportunity-watchlist" / "东方财富自选与近期查看.md",
        wiki_doc(
            "东方财富自选与近期查看",
            lines,
            maturity="basic" if watch else "hint",
            evidence_level="medium",
            targets=[
                "investor.opportunity_watchlist.watchlist",
                "investor.capability_circle.attention_universe",
            ],
        ),
    )


def write_trade_status_wiki(root: Path, events: List[Dict[str, Any]]) -> None:
    login_events = [e for e in events if e["kind"] == "broker_login_status"]
    selected = [
        e for e in events
        if e["kind"] in {
            "broker_position_status",
            "broker_asset_status",
            "broker_market_gap",
            "broker_trade_ui_status",
            "trade_page_stock_context",
            "broker_interface_response",
            "broker_trade_execution",
            "broker_entrust_order",
            "broker_fund_flow",
        }
    ]
    lines: List[str] = []
    if login_events:
        first_time = login_events[0].get("time") or login_events[0].get("collected_at")
        last_time = login_events[-1].get("time") or login_events[-1].get("collected_at")
        lines.append(
            f"- 登录心跳：`{len(login_events)}` 条，范围 `{first_time}` 到 `{last_time}`；不导出会话或凭证。"
        )
    for event in selected:
        data = event["data"]
        if event["kind"] == "broker_trade_execution":
            parts = [
                data.get("date"),
                data.get("time"),
                data.get("side"),
                data.get("symbol"),
                data.get("name"),
                f"数量 {data.get('quantity')}" if data.get("quantity") is not None else "",
                f"金额 {data.get('amount')}" if data.get("amount") is not None else "",
            ]
            lines.append("- 成交：" + " ".join(str(part) for part in parts if part))
        elif event["kind"] == "broker_entrust_order":
            parts = [
                data.get("date"),
                data.get("time"),
                data.get("side"),
                data.get("symbol"),
                data.get("name"),
                f"委托 {data.get('entrust_quantity')}@{data.get('entrust_price')}"
                if data.get("entrust_quantity") is not None or data.get("entrust_price") is not None
                else "",
                data.get("order_status"),
            ]
            lines.append("- 委托：" + " ".join(str(part) for part in parts if part))
        elif event["kind"] == "broker_fund_flow":
            parts = [
                data.get("date"),
                data.get("business"),
                f"金额 {data.get('amount')}" if data.get("amount") is not None else "",
                f"余额 {data.get('fund_balance')}" if data.get("fund_balance") is not None else "",
            ]
            lines.append("- 资金流水：" + " ".join(str(part) for part in parts if part))
        elif event["kind"] == "broker_interface_response":
            lines.append(
                f"- 接口响应：MSG_{data.get('msg_code')} status `{data.get('status_code')}` "
                f"count `{data.get('record_count')}` {data.get('message_summary') or ''}".rstrip()
            )
        elif event["kind"] == "broker_trade_ui_status":
            lines.append(
                f"- 交易页自动采集：窗口 `{data.get('window_found')}`，"
                f"账户状态 `{data.get('account_status')}`，"
                f"需解锁 `{data.get('needs_unlock')}`。"
            )
        else:
            lines.append(f"- `{event['time'] or event['collected_at']}` `{event['kind']}` {data.get('note') or data.get('status')}")
    lines.append("")
    write_text(
        root / "record-review" / "东方财富交易接口状态.md",
        wiki_doc(
            "东方财富交易接口状态",
            lines,
            maturity="hint",
            evidence_level="strong_status_only",
            targets=[
                "investor.record_review.decision_log",
                "investor.data_quality.collection_gaps",
            ],
        ),
    )


def write_risk_boundary_wiki(root: Path, events: List[Dict[str, Any]]) -> None:
    risk_gap_names = {
        "broker_account_locked",
        "broker_position_status_missing",
        "broker_asset_status_missing",
        "broker_position_detail_not_materialized",
        "broker_trade_detail_not_materialized",
        "asset_amounts_not_materialized",
        "trade_ui_app_not_running",
        "trade_ui_window_missing",
        "trade_ui_collect_failed",
        "trade_ui_accessibility_tree_empty",
        "trade_ui_assets_copy_unavailable",
        "trade_ui_positions_copy_unavailable",
        "trade_ui_executions_copy_unavailable",
        "trade_ui_entrusts_copy_unavailable",
        "trade_ui_funds_copy_unavailable",
    }
    selected = [
        e for e in events
        if e["kind"] in {
            "broker_position_status",
            "broker_asset_status",
            "broker_asset_snapshot",
            "broker_position_detail",
            "broker_trade_ui_status",
            "broker_market_gap",
        }
        or (e["kind"] == "data_gap" and e["data"].get("gap") in risk_gap_names)
    ]
    lines: List[str] = []
    for event in selected:
        data = event["data"]
        if event["kind"] == "broker_position_status":
            lines.append(f"- 持仓查询：成功，返回记录数 `{data.get('position_count')}`。")
        elif event["kind"] == "broker_asset_status":
            lines.append(f"- 资产查询：成功，返回记录数 `{data.get('asset_record_count')}`；本地未落地金额字段。")
        elif event["kind"] == "broker_asset_snapshot":
            parts = [
                f"总资产 `{data.get('total_asset')}`" if data.get("total_asset") is not None else "",
                f"可用 `{data.get('available_cash')}`" if data.get("available_cash") is not None else "",
                f"可取 `{data.get('withdrawable_cash')}`" if data.get("withdrawable_cash") is not None else "",
                f"市值 `{data.get('market_value')}`" if data.get("market_value") is not None else "",
                f"盈亏 `{data.get('profit_loss')}`" if data.get("profit_loss") is not None else "",
            ]
            lines.append("- 资产快照：" + "，".join(part for part in parts if part))
        elif event["kind"] == "broker_position_detail":
            parts = [
                data.get("market"),
                data.get("symbol"),
                data.get("name"),
                f"持仓 `{data.get('quantity')}`" if data.get("quantity") is not None else "",
                f"可用 `{data.get('available_quantity')}`" if data.get("available_quantity") is not None else "",
                f"市值 `{data.get('market_value')}`" if data.get("market_value") is not None else "",
                f"盈亏 `{data.get('profit_loss')}`" if data.get("profit_loss") is not None else "",
            ]
            lines.append("- 持仓：" + " ".join(str(part) for part in parts if part))
        elif event["kind"] == "broker_trade_ui_status":
            lines.append(
                f"- 交易页状态：窗口 `{data.get('window_found')}`，账户 `{data.get('account_status')}`，"
                f"可见字段 `{len(data.get('visible_trade_labels') or [])}` 个。"
            )
        elif event["kind"] == "broker_market_gap":
            lines.append("- 市场/客户代码提示：存在不可用提示；未写入原始交易通信内容。")
        elif data.get("gap"):
            lines.append(f"- 缺口 `{data.get('gap')}`：{data.get('note')}")
    lines.append("")
    has_confirmed_detail = any(
        event["kind"] in {"broker_asset_snapshot", "broker_position_detail"}
        for event in selected
    )
    write_text(
        root / "risk-portfolio" / "东方财富资产持仓边界.md",
        wiki_doc(
            "东方财富资产持仓边界",
            lines,
            maturity="basic" if has_confirmed_detail else "hint",
            evidence_level="strong_boundary" if has_confirmed_detail else "gap_boundary",
            targets=[
                "investor.risk_portfolio.current_assets",
                "investor.risk_portfolio.current_positions",
                "investor.risk_portfolio.portfolio_constraints",
                "investor.data_quality.collection_gaps",
            ],
        ),
    )


def write_research_wiki(root: Path, events: List[Dict[str, Any]]) -> None:
    selected = [
        e for e in events
        if e["kind"] in {"stock_note", "chart_drawing", "custom_panel", "recent_stock", "data_gap"}
    ]
    lines: List[str] = []
    for event in selected:
        data = event["data"]
        if event["kind"] == "recent_stock":
            lines.append(f"- 近期查看：{data.get('market') or ''} {data.get('symbol')} {data.get('name') or ''}".rstrip())
        elif event["kind"] == "data_gap":
            if data.get("gap") in {"stock_notes_empty", "chart_drawings_empty", "custom_panels_empty"}:
                lines.append(f"- {data.get('note')}")
        else:
            lines.append(f"- `{event['kind']}` {data.get('note') or data.get('title') or ''}".rstrip())
    lines.append("")
    write_text(
        root / "decision-framework" / "东方财富研究动作与工作流.md",
        wiki_doc(
            "东方财富研究动作与工作流",
            lines,
            maturity="hint",
            evidence_level="weak_to_medium",
            targets=[
                "investor.research_consumption.workflow",
                "investor.information_sources.news_consumption",
                "investor.decision_framework.monitoring_rules",
            ],
        ),
    )


def validate_output(output_dir: Path) -> Dict[str, Any]:
    errors: List[str] = []
    event_count = 0
    events_path = output_dir / "lake" / COLLECTOR / "events.jsonl"
    evidence_path = output_dir / "investor_wiki_evidence.v1.json"
    if events_path.exists():
        with events_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                event_count += 1
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"events.jsonl:{line_no}: invalid json: {exc}")
                    continue
                kind = event.get("kind")
                if kind not in COLLECTORX_ALLOWED_KINDS:
                    errors.append(f"events.jsonl:{line_no}: non-standard kind: {kind}")
                for target in event.get("wiki_targets") or []:
                    if str(target).startswith("vertical/investor/"):
                        errors.append(f"events.jsonl:{line_no}: legacy wiki target: {target}")
    else:
        errors.append("events.jsonl: missing")
    if not evidence_path.exists():
        errors.append("investor_wiki_evidence.v1.json: missing")
    else:
        try:
            evidence = json.loads(evidence_path.read_text("utf-8"))
            if evidence.get("schema") != "finclaw.investor_wiki_evidence.v1":
                errors.append("investor_wiki_evidence.v1.json: invalid schema")
        except json.JSONDecodeError as exc:
            errors.append(f"investor_wiki_evidence.v1.json: invalid json: {exc}")
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".md"}:
            continue
        text = path.read_text("utf-8", errors="replace")
        for pattern in FORBIDDEN_OUTPUT_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path.name}: forbidden pattern {pattern.pattern}")
    return {
        "ok": not errors,
        "errors": errors,
        "event_count": event_count,
    }


def parse_log_time(line: str) -> Optional[str]:
    match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?\]", line)
    if not match:
        return None
    return parse_time(match.group(1))


def parse_time(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt)
            return dt.replace(tzinfo=TZ).isoformat()
        except ValueError:
            continue
    return None


def extract_first_symbol(text: str) -> Optional[str]:
    match = re.search(r"\b([0368]\d{5})\b", text or "")
    return match.group(1) if match else None


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except FileNotFoundError:
        return ""
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mask_identifier(value: str) -> str:
    if not value:
        return value
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 6:
        return value[0] + "*" * (len(value) - 2) + value[-1]
    return value[:3] + "*" * max(3, len(value) - 5) + value[-2:]


def redacted_path(path: Optional[Path]) -> str:
    if not path:
        return ""
    text = str(path)
    text = re.sub(r"(/Users/)([^/]+)", lambda m: m.group(1) + mask_identifier(m.group(2)), text)
    text = re.sub(r"(\\Users\\)([^\\]+)", lambda m: m.group(1) + mask_identifier(m.group(2)), text)
    text = re.sub(r"/config/user/([^/]+)", lambda m: "/config/user/" + mask_identifier(m.group(1)), text)
    text = re.sub(r"\b\d{7,}\b", lambda m: mask_identifier(m.group(0)), text)
    return text


def scrub_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"(?i)(cookie|token|password|passwd|secret|session|ticket|sign)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    return text


def scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: scrub_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_value(v) for v in value]
    if isinstance(value, tuple):
        return [scrub_value(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

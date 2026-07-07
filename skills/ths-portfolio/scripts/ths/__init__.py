"""ths包"""
from .parser import parse_portfolio_csv
from .stats import calculate_stats, calculate_stock_stats
from .local import (
    build_local_probe_report,
    find_xcs_lscj_files,
    infer_holdings,
    local_source_label,
    parse_xcs_lscj,
    resolve_platform,
)
from .metadata import collect_personal_metadata, metadata_summary_for_wiki
from .gui import collect_gui_snapshot
from .package import (
    build_investor_wiki_evidence,
    sync_package_to_soulmirror,
    write_collection_package,
)

__all__ = [
    "parse_portfolio_csv",
    "parse_xcs_lscj",
    "find_xcs_lscj_files",
    "build_local_probe_report",
    "resolve_platform",
    "local_source_label",
    "collect_personal_metadata",
    "metadata_summary_for_wiki",
    "collect_gui_snapshot",
    "build_investor_wiki_evidence",
    "write_collection_package",
    "sync_package_to_soulmirror",
    "infer_holdings",
    "calculate_stats",
    "calculate_stock_stats",
]

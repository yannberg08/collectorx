"""
ths.events — Convert Tonghuashun trade records to CollectorX events.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR_ID = "ths-portfolio"
DEFAULT_SOURCE = "同花顺交割单 CSV"
CN_TZ = timezone(timedelta(hours=8))


def records_to_events(
    records: Iterable[Dict[str, Any]],
    *,
    source: str = DEFAULT_SOURCE,
    raw_file: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for index, record in enumerate(records, start=2):
        events.append(
            record_to_event(
                record,
                source=source,
                raw_file=raw_file,
                row_number=index,
                collected_at=collected_at,
            )
        )
    return events


def record_to_event(
    record: Dict[str, Any],
    *,
    source: str = DEFAULT_SOURCE,
    raw_file: Optional[str] = None,
    row_number: Optional[int] = None,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    event_time = _event_time(record)
    side = _normalize_side(record.get("direction", ""))
    event_id = _stable_event_id(record, side, row_number)

    raw_ref: Dict[str, Any] = {}
    effective_raw_file = raw_file or record.get("source_file") or record.get("raw_file")
    if effective_raw_file:
        raw_ref["file"] = str(Path(effective_raw_file))
    if row_number is not None:
        raw_ref["row"] = row_number
    if record.get("source_format"):
        raw_ref["format"] = record.get("source_format")
    if record.get("source_symbol"):
        raw_ref["symbol_bucket"] = record.get("source_symbol")
    if record.get("source_date"):
        raw_ref["date_bucket"] = record.get("source_date")
    if record.get("source_index") is not None:
        raw_ref["source_index"] = record.get("source_index")
    if record.get("raw_order_hash"):
        raw_ref["order_hash"] = record.get("raw_order_hash")
    if record.get("raw_execution_hash"):
        raw_ref["execution_hash"] = record.get("raw_execution_hash")

    return {
        "schema": "collectorx.event.v1",
        "id": event_id,
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": "trade",
        "time": event_time,
        "collected_at": collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "data": {
            "account": record.get("account") or "default",
            "symbol": record.get("code", ""),
            "name": record.get("name", ""),
            "side": side,
            "raw_side": record.get("direction", ""),
            "price": record.get("price", 0.0),
            "quantity": record.get("quantity", 0),
            "amount": record.get("amount", 0.0),
            "fee": record.get("fee", 0.0),
            "tax": record.get("tax", 0.0),
        },
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["trade", "money", "portfolio"],
        },
        "wiki_targets": [
            "investor.record_review.decision_log",
            "investor.risk_portfolio.portfolio_constraints",
            "investor.decision_framework.position_sizing",
            "external.capital.assets",
        ],
    }


def holdings_to_events(
    holdings: Iterable[Dict[str, Any]],
    *,
    source: str,
    raw_file: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for holding in holdings:
        events.append(
            holding_to_event(
                holding,
                source=source,
                raw_file=raw_file,
                collected_at=collected_at,
            )
        )
    return events


def holding_to_event(
    holding: Dict[str, Any],
    *,
    source: str,
    raw_file: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    event_id = _stable_holding_event_id(holding)
    raw_ref: Dict[str, Any] = {"derived_from": "historical_trade_events"}
    if raw_file:
        raw_ref["file"] = str(Path(raw_file))

    return {
        "schema": "collectorx.event.v1",
        "id": event_id,
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": "holding",
        "time": collected,
        "collected_at": collected,
        "data": {
            "account": holding.get("account") or "default",
            "symbol": holding.get("symbol", ""),
            "name": holding.get("name", ""),
            "quantity": holding.get("quantity", 0),
            "market_value": holding.get("market_value"),
            "cost": holding.get("cost", 0.0),
            "avg_cost": holding.get("avg_cost", 0.0),
            "unrealized_pnl": holding.get("unrealized_pnl"),
            "snapshot_type": holding.get("snapshot_type"),
            "evidence_level": holding.get("evidence_level"),
            "confidence": holding.get("confidence"),
            "is_confirmed": holding.get("is_confirmed", False),
            "source_trade_count": holding.get("source_trade_count", 0),
            "first_trade_time": holding.get("first_trade_time"),
            "last_trade_time": holding.get("last_trade_time"),
            "limitations": holding.get("limitations", []),
        },
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["trade", "money", "portfolio"],
        },
        "wiki_targets": [
            "investor.risk_portfolio.current_positions",
            "investor.decision_framework.position_sizing",
            "external.capital.assets",
        ],
    }


def gap_status_to_event(
    status: Dict[str, Any],
    *,
    source: str,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    digest = hashlib.sha256(
        json_dumps_stable(status).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "schema": "collectorx.event.v1",
        "id": f"{COLLECTOR_ID}:gap:{digest}",
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": "profile",
        "time": collected,
        "collected_at": collected,
        "data": status,
        "raw_ref": {"derived_from": "local_source_discovery"},
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["trade", "money", "portfolio"],
        },
        "wiki_targets": [
            "investor.data_quality.collection_gaps",
            "investor.risk_portfolio.current_positions",
        ],
    }


def personal_metadata_to_events(
    metadata: Dict[str, Any],
    *,
    source: str,
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    events: List[Dict[str, Any]] = []

    for item in metadata.get("watchlist_items", []):
        events.append(
            _metadata_event(
                source=source,
                kind="watchlist",
                collected=collected,
                data={
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "group": item.get("group_name", ""),
                    "group_id": item.get("group_id", ""),
                    "market": item.get("market", ""),
                    "source_type": item.get("source_type"),
                    "evidence_level": item.get("evidence_level"),
                },
                raw_ref={"file": item.get("source_file", "")},
                wiki_targets=[
                    "investor.opportunity_watchlist.watchlist",
                    "investor.capability_circle.attention_universe",
                ],
            )
        )

    profile_groups = [
        ("strategy_rules", "ths_strategy_rule", "investor.decision_framework.strategy_rules"),
        ("strategy_topics", "ths_strategy_topic", "investor.capability_circle.theme_attention"),
        ("short_term_rules", "ths_short_term_wizard", "investor.decision_framework.monitoring_rules"),
        ("widget_layouts", "ths_widget_layout", "investor.research_consumption.workflow"),
        ("custom_pages", "ths_custom_page", "investor.research_consumption.workflow"),
    ]
    for collection_name, profile_type, wiki_target in profile_groups:
        for item in metadata.get(collection_name, []):
            data = dict(item)
            data["profile_type"] = profile_type
            events.append(
                _metadata_event(
                    source=source,
                    kind="profile",
                    collected=collected,
                    data=data,
                    raw_ref={"file": item.get("source_file", "")},
                    wiki_targets=[wiki_target],
                )
            )

    if metadata.get("strategy_label_summary"):
        events.append(
            _metadata_event(
                source=source,
                kind="profile",
                collected=collected,
                data={
                    "profile_type": "ths_strategy_label_summary",
                    "labels": metadata.get("strategy_label_summary", []),
                    "evidence_level": "weak",
                },
                raw_ref={"derived_from": "KYCStrategyInfo"},
                wiki_targets=[
                    "investor.capability_circle.factor_attention",
                    "investor.decision_framework.strategy_rules",
                ],
            )
        )

    for item in metadata.get("news_read_markers", []):
        data = dict(item)
        data["activity_type"] = "news_read_marker"
        events.append(
            _metadata_event(
                source=source,
                kind="other",
                collected=collected,
                data=data,
                raw_ref={"file": item.get("source_file", "")},
                wiki_targets=["investor.information_sources.news_consumption"],
            )
        )

    events.append(
        _metadata_event(
            source=source,
            kind="profile",
            collected=collected,
            data={
                "profile_type": "ths_personal_metadata_collection_summary",
                "counts": metadata.get("counts", {}),
                "evidence_note": metadata.get("evidence_note", ""),
            },
            raw_ref={"derived_from": "ths_personal_metadata"},
            wiki_targets=["investor.data_quality.collection_gaps"],
        )
    )

    return events


def gui_snapshot_to_events(
    snapshot: Dict[str, Any],
    *,
    source: str,
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    collected = collected_at or snapshot.get("collected_at") or datetime.now(CN_TZ).isoformat(timespec="seconds")
    account = snapshot.get("account", {})
    events: List[Dict[str, Any]] = []

    asset_snapshot = dict(snapshot.get("asset_snapshot", {}))
    if asset_snapshot:
        asset_snapshot["account"] = account
        events.append(
            _gui_event(
                source=source,
                kind="asset_snapshot",
                collected=collected,
                data=asset_snapshot,
                raw_ref={"derived_from": "ths_gui_asset_panel"},
                privacy_contains=["money", "portfolio"],
                wiki_targets=[
                    "investor.risk_portfolio.current_assets",
                    "external.capital.assets",
                ],
            )
        )

    holding_tab = snapshot.get("tabs", {}).get("holding", {})
    holding_screenshot = holding_tab.get("screenshot")
    for row in holding_tab.get("rows", []):
        data = dict(row)
        data.update(
            {
                "account": account,
                "snapshot_type": "broker_gui_current_snapshot",
                "evidence_level": "confirmed_gui",
                "is_confirmed": True,
            }
        )
        events.append(
            _gui_event(
                source=f"{source} / 真实持仓",
                kind="holding",
                collected=collected,
                data=data,
                raw_ref={"file": holding_screenshot, "tab": "持仓"},
                privacy_contains=["money", "portfolio"],
                wiki_targets=[
                    "investor.risk_portfolio.current_positions",
                    "investor.decision_framework.position_sizing",
                    "external.capital.assets",
                ],
            )
        )

    table_specs = [
        ("orders", "委托", "order", ["trade", "portfolio"], ["investor.execution.orders"]),
        ("deals", "成交", "execution", ["trade", "money", "portfolio"], ["investor.record_review.decision_log"]),
        ("funds_detail", "资金明细", "cashflow", ["money", "portfolio"], ["external.capital.cashflows"]),
    ]
    for tab_key, tab_title, kind, privacy_contains, wiki_targets in table_specs:
        tab = snapshot.get("tabs", {}).get(tab_key, {})
        rows = tab.get("rows", [])
        if rows:
            for row in rows:
                data = dict(row)
                data.update(
                    {
                        "account": account,
                        "snapshot_type": "broker_gui_current_snapshot",
                        "evidence_level": "confirmed_gui",
                        "is_confirmed": True,
                    }
                )
                events.append(
                    _gui_event(
                        source=f"{source} / {tab_title}",
                        kind=kind,
                        collected=collected,
                        data=data,
                        raw_ref={"file": tab.get("screenshot"), "tab": tab_title},
                        privacy_contains=privacy_contains,
                        wiki_targets=wiki_targets,
                    )
                )
            continue

        events.append(
            _gui_event(
                source=f"{source} / {tab_title}",
                kind="profile",
                collected=collected,
                data={
                    "profile_type": f"ths_gui_empty_{tab_key}",
                    "account": account,
                    "tab": tab_title,
                    "row_count": 0,
                    "headers": tab.get("headers", []),
                    "snapshot_type": "broker_gui_current_snapshot",
                    "evidence_level": "confirmed_gui",
                    "is_confirmed": True,
                },
                raw_ref={"file": tab.get("screenshot"), "tab": tab_title},
                privacy_contains=privacy_contains,
                wiki_targets=["investor.data_quality.collection_gaps", *wiki_targets],
            )
        )

    return events


def _gui_event(
    *,
    source: str,
    kind: str,
    collected: str,
    data: Dict[str, Any],
    raw_ref: Dict[str, Any],
    privacy_contains: List[str],
    wiki_targets: List[str],
) -> Dict[str, Any]:
    digest = hashlib.sha256(
        json_dumps_stable({"kind": kind, "data": data, "raw_ref": raw_ref}).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "schema": "collectorx.event.v1",
        "id": f"{COLLECTOR_ID}:gui:{digest}",
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": kind,
        "time": collected,
        "collected_at": collected,
        "data": data,
        "raw_ref": {key: value for key, value in raw_ref.items() if value not in (None, "")},
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": sorted(set(privacy_contains)),
        },
        "wiki_targets": wiki_targets,
    }


def _metadata_event(
    *,
    source: str,
    kind: str,
    collected: str,
    data: Dict[str, Any],
    raw_ref: Dict[str, Any],
    wiki_targets: List[str],
) -> Dict[str, Any]:
    digest = hashlib.sha256(
        json_dumps_stable({"kind": kind, "data": data, "raw_ref": raw_ref}).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "schema": "collectorx.event.v1",
        "id": f"{COLLECTOR_ID}:metadata:{digest}",
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": kind,
        "time": collected,
        "collected_at": collected,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["portfolio"],
        },
        "wiki_targets": wiki_targets,
    }


def _stable_event_id(record: Dict[str, Any], side: str, row_number: Optional[int]) -> str:
    body = "|".join(
        [
            COLLECTOR_ID,
            str(record.get("account", "")),
            str(record.get("date", "")),
            str(record.get("time", "")),
            str(record.get("code", "")),
            str(record.get("name", "")),
            side,
            str(record.get("price", "")),
            str(record.get("quantity", "")),
            str(record.get("amount", "")),
            str(record.get("fee", "")),
            str(record.get("tax", "")),
            str(row_number or ""),
        ]
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]
    return f"{COLLECTOR_ID}:{digest}"


def _stable_holding_event_id(holding: Dict[str, Any]) -> str:
    body = "|".join(
        [
            COLLECTOR_ID,
            "holding",
            str(holding.get("account", "")),
            str(holding.get("symbol", "")),
            str(holding.get("quantity", "")),
            str(holding.get("cost", "")),
            str(holding.get("snapshot_type", "")),
            str(holding.get("last_trade_time", "")),
        ]
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]
    return f"{COLLECTOR_ID}:holding:{digest}"


def _normalize_side(direction: str) -> str:
    direction = (direction or "").strip()
    if direction in {"买入", "买", "B", "BUY", "buy"}:
        return "buy"
    if direction in {"卖出", "卖", "S", "SELL", "sell"}:
        return "sell"
    if direction in {"配售中签"}:
        return "allocation"
    if direction in {"红股"}:
        return "bonus_share"
    if direction in {"红股派息"}:
        return "dividend"
    return direction or "unknown"


def _event_time(record: Dict[str, Any]) -> Optional[str]:
    date = str(record.get("date", "") or "").strip()
    time = str(record.get("time", "") or "").strip()
    if not date:
        return None

    if not time:
        time = "00:00:00"

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            dt = datetime.strptime(f"{date} {time}", fmt)
            return dt.replace(tzinfo=CN_TZ).isoformat(timespec="seconds")
        except ValueError:
            continue

    return f"{date}T{time}+08:00"


def json_dumps_stable(value: Dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

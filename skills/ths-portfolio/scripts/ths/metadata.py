"""
ths.metadata — Collect Tonghuashun investor-behavior metadata.

These signals are mostly medium or weak evidence. They help FinClaw understand
watchlists, opportunity discovery, research consumption, and workflow shape,
but they are not broker-confirmed positions or trade instructions.
"""

from __future__ import annotations

import base64
import collections
import plistlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .local import DEFAULT_CONTAINER_DATA, local_file_label, mask_numeric_identifier


STOCK_CODE_RE = re.compile(rb"(?<!\d)(?:0|3|6|8|9)\d{5}(?!\d)")
SKIP_CLOUD_KEYS = {
    "pc_common.ini",
    "pc_iwc_table_header",
    "userid",
    "maxVersion",
    "StockGroupCommon",
}


def collect_personal_metadata(
    container_root: Optional[str] = None,
    *,
    platform: str = "auto",
) -> Dict[str, Any]:
    root = Path(container_root).expanduser() if container_root else DEFAULT_CONTAINER_DATA
    documents = root / "Documents" if (root / "Documents").exists() else root

    watchlist_items, watchlist_groups = collect_watchlist_metadata(documents)
    strategy_rules, strategy_topics, strategy_label_summary = collect_strategy_metadata(documents)
    news_read_markers = collect_news_read_metadata(documents)
    short_term_rules = collect_short_term_wizard_metadata(documents)
    widget_layouts = collect_widget_metadata(documents)
    custom_pages = collect_custom_page_metadata(documents)

    return {
        "schema": "ths.personal_metadata.v1",
        "platform": platform,
        "source_root": _safe_root_label(root),
        "watchlist_items": watchlist_items,
        "watchlist_groups": watchlist_groups,
        "strategy_rules": strategy_rules,
        "strategy_topics": strategy_topics,
        "strategy_label_summary": strategy_label_summary,
        "news_read_markers": news_read_markers,
        "short_term_rules": short_term_rules,
        "widget_layouts": widget_layouts,
        "custom_pages": custom_pages,
        "counts": {
            "watchlist_items": len(watchlist_items),
            "watchlist_groups": len(watchlist_groups),
            "strategy_rules": len(strategy_rules),
            "strategy_topics": len(strategy_topics),
            "strategy_labels": len(strategy_label_summary),
            "news_read_markers": len(news_read_markers),
            "short_term_rules": len(short_term_rules),
            "widget_layouts": len(widget_layouts),
            "custom_pages": len(custom_pages),
        },
        "evidence_note": (
            "watchlist and local settings are personal local evidence; "
            "KYC strategy and short-term wizard settings may include product defaults, "
            "so they should be distilled as weak evidence unless confirmed by user action."
        ),
    }


def collect_watchlist_metadata(documents: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    items: List[Dict[str, Any]] = []
    groups: List[Dict[str, Any]] = []
    for path in sorted(documents.glob("cloud_store/blockstock_*/public/*.dat")):
        decoded_key = decode_cloud_key(path)
        if decoded_key in SKIP_CLOUD_KEYS:
            continue
        top = load_nskeyed_plist(path)
        root = _first_dict_value(top)
        if not isinstance(root, dict):
            continue
        raw_value = root.get("self.value")
        if not isinstance(raw_value, (bytes, bytearray)):
            continue
        if b"[index_code]" in raw_value:
            continue

        parsed = parse_watchlist_value(bytes(raw_value))
        if not parsed["symbols"]:
            continue
        group_id = _bytes_to_group_id(root.get("self.ID")) or decoded_key
        group_name = parsed.get("group_name") or group_id
        source_file = local_file_label(path)
        groups.append(
            {
                "group_id": group_id,
                "group_name": group_name,
                "item_count": len(parsed["symbols"]),
                "source_file": source_file,
                "evidence_level": "medium",
            }
        )
        for index, symbol in enumerate(parsed["symbols"]):
            items.append(
                {
                    "symbol": symbol,
                    "name": "",
                    "group_id": group_id,
                    "group_name": group_name,
                    "position": index,
                    "market": parsed["markets"][index] if index < len(parsed["markets"]) else "",
                    "source_file": source_file,
                    "source_type": "ths_cloud_blockstock",
                    "evidence_level": "medium",
                }
            )
    return items, groups


def parse_watchlist_value(value: bytes) -> Dict[str, Any]:
    symbols = _dedupe([code.decode("ascii") for code in STOCK_CODE_RE.findall(value)])
    markets: List[str] = []
    text = value.decode("latin1", errors="ignore")
    if symbols:
        numeric_parts = re.findall(r"(?:(?<=\|)|(?<=,))(17|33|32|64|128)(?=\|)", text)
        markets = numeric_parts[: len(symbols)]
    return {
        "group_name": _decode_first_base64_chinese(value),
        "symbols": symbols,
        "markets": markets,
    }


def collect_strategy_metadata(documents: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    path = documents / "KYCStrategyLabelsManager" / "KYCStrategyInfo"
    if not path.exists():
        return [], [], []
    top = load_nskeyed_plist(path)
    data = top.get("KYCLocalStrategyInfoFileKey", {})
    if not isinstance(data, dict):
        return [], [], []

    rules: List[Dict[str, Any]] = []
    topics: List[Dict[str, Any]] = []
    label_counter: collections.Counter[str] = collections.Counter()

    for name, payload in sorted(data.items(), key=lambda item: str(item[0])):
        if not isinstance(payload, dict):
            continue
        item_type = payload.get("type")
        labels = [str(label) for label in payload.get("label", []) if str(label).strip()]
        label_counter.update(labels)
        if item_type == 3:
            topics.append(
                {
                    "topic": str(name),
                    "chance_id": str(payload.get("chanceId", "")),
                    "title": str(payload.get("chanceTitle", "")),
                    "url": str(payload.get("chanceUrl", "")),
                    "recommended_symbols": _extract_symbols(payload.get("chanceRecommandStock", [])),
                    "source_file": local_file_label(path),
                    "source_type": "ths_kyc_strategy_topic",
                    "evidence_level": "weak",
                }
            )
        else:
            rules.append(
                {
                    "rule_text": str(name),
                    "rule_type": item_type,
                    "labels": labels,
                    "source_file": local_file_label(path),
                    "source_type": "ths_kyc_strategy_rule",
                    "evidence_level": "weak",
                }
            )

    label_summary = [
        {"label": label, "count": count, "evidence_level": "weak"}
        for label, count in label_counter.most_common()
    ]
    return rules, topics, label_summary


def collect_news_read_metadata(documents: Path) -> List[Dict[str, Any]]:
    path = documents / "ZiXunReadData" / "ZiXunReadDataFileName"
    if not path.exists():
        return []
    top = load_nskeyed_plist(path)
    data = top.get("ZiXunReadDataDecodeKey", {})
    if not isinstance(data, dict):
        return []

    items: List[Dict[str, Any]] = []
    for account, ids in sorted(data.items()):
        if not isinstance(ids, list):
            continue
        counter = collections.Counter(str(item) for item in ids if str(item).strip())
        for marker_id, count in counter.most_common():
            items.append(
                {
                    "marker_id": marker_id,
                    "read_count": count,
                    "account": mask_numeric_identifier(str(account)),
                    "source_file": local_file_label(path),
                    "source_type": "ths_zixun_read_marker",
                    "evidence_level": "medium",
                }
            )
    return items


def collect_short_term_wizard_metadata(documents: Path) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for path in sorted(documents.glob("ShortTermWizard/*/HXShortTermWizardMarketMapKey.text")):
        top = load_nskeyed_plist(path)
        data = top.get("HXShortTermWizardMarketMapKey", {})
        for market, item in _iter_short_term_items(data):
            if item.get("selected") is not True:
                continue
            rules.append(
                {
                    "market": market,
                    "name": str(item.get("name", "")),
                    "section": str(item.get("sectionTitle", "")),
                    "item_id": str(item.get("itemID", "")),
                    "options": _summarize_options(item.get("options", [])),
                    "source_file": local_file_label(path),
                    "source_type": "ths_short_term_wizard",
                    "evidence_level": "weak",
                }
            )
    return rules


def collect_widget_metadata(documents: Path) -> List[Dict[str, Any]]:
    layouts: List[Dict[str, Any]] = []
    for path in sorted(documents.glob("PKLocalSettings/WidgetSettingLocalFileName-*")):
        top = load_nskeyed_plist(path)
        data = top.get("PKWidgetSettingDecodeKey", {})
        if not isinstance(data, dict):
            continue
        for context, value in sorted(data.items()):
            if context == "version" or not isinstance(value, dict):
                continue
            for view_name, sections in sorted(value.items()):
                if not isinstance(sections, list):
                    continue
                for section in sections:
                    if not isinstance(section, dict):
                        continue
                    module = section.get("module", {})
                    displayed = module.get("displayed", []) if isinstance(module, dict) else []
                    layouts.append(
                        {
                            "context": str(context),
                            "view": str(view_name),
                            "title": str(section.get("title", "")),
                            "displayed_modules": [str(item) for item in displayed],
                            "template_used": bool(section.get("templateUsed", False)),
                            "source_file": local_file_label(path),
                            "source_type": "ths_widget_layout",
                            "evidence_level": "weak",
                        }
                    )
    return layouts


def collect_custom_page_metadata(documents: Path) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    for path in sorted(documents.glob("HXCustomizablePageSettings/*/HXCustomizablePageWindowObject")):
        top = load_nskeyed_plist(path)
        data = top.get("HXCustomizablePageWindowObjectKey", {})
        titles = _find_values_by_key_suffix(data, "pageTitle")
        for index, title in enumerate(titles):
            pages.append(
                {
                    "title": str(title),
                    "position": index,
                    "source_file": local_file_label(path),
                    "source_type": "ths_custom_page",
                    "evidence_level": "weak",
                }
            )
    return pages


def load_nskeyed_plist(path: Path) -> Dict[str, Any]:
    raw = plistlib.load(path.open("rb"))
    objects = raw.get("$objects")
    top = raw.get("$top")
    if not objects or not top:
        return raw
    return {key: _decode_archived(value, objects) for key, value in top.items()}


def decode_cloud_key(path: Path) -> str:
    marker = "__public__"
    name = path.stem
    if marker not in name:
        return name
    encoded = name.split(marker, 1)[1]
    try:
        return base64.b64decode(encoded + "===").decode("utf-8")
    except Exception:
        return encoded


def _decode_archived(obj: Any, objects: List[Any], seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()
    if isinstance(obj, plistlib.UID):
        index = obj.data
        if index in seen:
            return f"<cycle:{index}>"
        return _decode_archived(objects[index], objects, seen | {index})
    if isinstance(obj, dict):
        cls = _decode_archived(obj.get("$class"), objects, seen) if "$class" in obj else None
        class_name = cls.get("$classname") if isinstance(cls, dict) else None
        if "NS.keys" in obj and "NS.objects" in obj:
            keys = [_decode_archived(key, objects, seen) for key in obj["NS.keys"]]
            values = [_decode_archived(value, objects, seen) for value in obj["NS.objects"]]
            decoded = dict(zip([str(key) for key in keys], values))
            if class_name and class_name not in {"NSDictionary", "NSMutableDictionary"}:
                decoded["_class"] = class_name
            return decoded
        if "NS.objects" in obj:
            return [_decode_archived(value, objects, seen) for value in obj["NS.objects"]]
        decoded = {
            key: _decode_archived(value, objects, seen)
            for key, value in obj.items()
            if key != "$class"
        }
        if class_name:
            decoded["_class"] = class_name
        return decoded
    if isinstance(obj, list):
        return [_decode_archived(value, objects, seen) for value in obj]
    return obj


def _iter_short_term_items(data: Any, market: str = "") -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(data, dict):
        next_market = market
        if "title" in data and isinstance(data.get("title"), str) and not market:
            next_market = data["title"]
        if "name" in data and "selected" in data:
            yield next_market, data
        for key, value in data.items():
            if key == "itemList" and isinstance(value, list):
                section_title = data.get("sectionTitle")
                for child in value:
                    if isinstance(child, dict) and section_title and "sectionTitle" not in child:
                        child = {**child, "sectionTitle": section_title}
                    yield from _iter_short_term_items(child, next_market)
            else:
                child_market = str(key) if not next_market and isinstance(value, dict) else next_market
                yield from _iter_short_term_items(value, child_market)
    elif isinstance(data, list):
        for value in data:
            yield from _iter_short_term_items(value, market)


def _summarize_options(options: Any) -> List[Dict[str, Any]]:
    if not isinstance(options, list):
        return []
    result: List[Dict[str, Any]] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        result.append(
            {
                "title": option.get("title"),
                "symbol": option.get("symbol"),
                "default_value": option.get("defaultValue"),
                "unit": option.get("unit"),
                "negative": option.get("negative"),
            }
        )
    return result


def _first_dict_value(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
    return value


def _decode_first_base64_chinese(value: bytes) -> str:
    for match in re.findall(rb"[A-Za-z0-9+/]{4,}={0,2}", value[:80]):
        try:
            decoded = base64.b64decode(match + b"===")
        except Exception:
            continue
        for encoding in ("utf-8", "gb18030"):
            text = decoded.decode(encoding, errors="ignore").strip()
            if text and any("\u4e00" <= char <= "\u9fff" for char in text):
                return text
    return ""


def _bytes_to_group_id(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return str(value or "")


def _extract_symbols(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for child in value.values():
            found.extend(_extract_symbols(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_extract_symbols(child))
    elif isinstance(value, str):
        found.extend(re.findall(r"(?<!\d)(?:0|3|6|8|9)\d{5}(?!\d)", value))
    return _dedupe(found)


def _find_values_by_key_suffix(value: Any, suffix: str) -> List[Any]:
    found: List[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).endswith(suffix):
                found.append(child)
            found.extend(_find_values_by_key_suffix(child, suffix))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_values_by_key_suffix(child, suffix))
    return found


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _safe_root_label(path: Path) -> str:
    text = str(path.expanduser())
    home = str(Path.home())
    if text == home:
        text = "~"
    elif text.startswith(home + "/"):
        text = "~/" + text[len(home) + 1 :]
    return re.sub(r"\d{6,}", lambda match: mask_numeric_identifier(match.group(0)), text)


def metadata_summary_for_wiki(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact routing summary for investor Wiki distillation."""
    return {
        "investment_style": {
            "signals": ["trade_history", "watchlist_breadth", "short_term_wizard"],
            "support_level": "medium",
        },
        "risk_preference": {
            "signals": ["estimated_holdings", "watchlist", "widget_layout"],
            "support_level": "medium",
        },
        "capability_circle": {
            "signals": ["watchlist_items", "strategy_labels", "strategy_topics"],
            "support_level": "medium",
        },
        "information_sources": {
            "signals": ["zixun_read_markers", "AI/iwencai GUI presence"],
            "support_level": "weak_to_medium",
        },
        "decision_framework": {
            "signals": ["KYC strategy rules", "short-term wizard selected rules"],
            "support_level": "weak",
        },
        "trading_discipline": {
            "signals": ["trade_history", "gap_status"],
            "support_level": "weak_to_medium",
        },
        "still_missing": [
            "broker_confirmed_current_positions",
            "cash_and_asset_snapshot",
            "orders_cancels_rejections",
            "explicit_buy_sell_reasons",
            "research_notes_and_meeting_minutes",
        ],
        "counts": metadata.get("counts", {}),
    }

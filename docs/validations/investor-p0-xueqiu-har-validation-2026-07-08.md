# P0 Xueqiu HAR Validation - 2026-07-08

This validation records the P0 Xueqiu pass that adds user-authorized browser
network export support to `xueqiu-investor-activity`.

## Scope

- Collector: `xueqiu-investor-activity`
- Version: `0.3.1`
- Input added: `.har` browser network export files selected by the user.
- Evidence role: Xueqiu attention network, opinions, saved pages, follows,
  favorites, comments, posts, watchlists, and model-portfolio activity.
- Explicit non-goal: broker-confirmed trades, orders, holdings, cash movements,
  or platform-wide sentiment.

## Implementation

- `.har` is now a supported input extension, including inside authorized ZIP
  packages.
- The parser reads only entries whose request host is `xueqiu.com` or a
  subdomain.
- For matched entries, the parser reads the response body, supports normal JSON,
  `while(1);` guarded JSON, and JSONP-shaped JSON, then normalizes Snowball-like
  payloads through the existing activity pipeline.
- Event provenance stores only local file path, HAR entry number, row number,
  endpoint path, response status, and parser name.
- Request headers, request cookies, response cookies, Authorization headers, and
  request URL query strings are not written into events, manifest, or Investor
  Wiki evidence.

## Manifest Audit Added

- `authorized_browser_network_export_used`
- `browser_network_export_file_count`
- `har_entry_count`
- `har_xueqiu_entry_count`
- `har_response_record_count`
- `har_skipped_entry_count`
- `har_skip_reason_counts`
- `har_endpoint_counts`
- `har_secret_material_stripped_count`
- `har_query_string_stripped_count`
- `har_secret_material_policy`

## Validation

Command:

```bash
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

Result:

```text
xueqiu-investor-activity tests passed.
```

Fixture coverage:

- A logged-in-like Xueqiu timeline HAR response emits a `post` event.
- `$贵州茅台(SH600519)$` is normalized to `SH600519`.
- User author metadata is preserved from the Xueqiu response body.
- A non-Xueqiu URL is skipped with `non_xueqiu_url`.
- A Xueqiu non-JSON response is skipped with `non_json_response`.
- `Cookie`, `Authorization`, `xq_a_token`, URL query strings, and the secret
  value fixture do not appear in emitted events.

## Remaining Gaps

- Real user HAR samples are still needed to validate endpoint diversity,
  pagination, favorites, comments, follows, watchlists, and portfolio activity.
- This is not a one-click login/session adapter.
- Any automated browser/account adapter must go through a separate rate-limit,
  terms, and read-only permission review before production use.

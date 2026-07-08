# FinClaw Integration Guide

CollectorX is the personal evidence layer for FinClaw. FinClaw should call
CollectorX collectors to get user-owned evidence, then pass the evidence through
SoulMirror/FinClaw distillation into the investor Wiki.

## Flow

```text
FinClaw UI / job runner
  -> CollectorX collector skill
  -> collectorx.event.v1 JSONL
  -> local lake
  -> finclaw.investor_wiki_evidence.v1
  -> investor-portrait distill/organize
  -> Wiki external.investor
```

Collectors do not write the final Wiki directly.

## What FinClaw Should Discover

FinClaw should read collector metadata from:

```text
collectors/finclaw-investor-catalog.json
collectors/finclaw-invocation-contracts.json
collectors/generic/*.yaml
collectors/vertical/*.yaml
collectors/lenses/*.yaml
```

The investor catalog is the product registry: priority, readiness, CLI,
collection scope, exclusions, and production gaps. The invocation contracts file
adds the user-facing precondition layer: authorization mode, product surface,
evidence role, preflight, user step, failure state, and lens upstream
requirements.

Each YAML declares:

- `id`: collector id
- `category`: `generic`, `vertical`, or `lens`
- `skill`: executable skill, if available
- `armed`: whether the user has explicitly enabled it
- `scope.collects`: allowed evidence
- `scope.excludes`: forbidden evidence
- `upstream_collectors`: for lenses

FinClaw should not run collectors with `armed: false` unless the user has just
authorized that collector in the product flow.

## Invocation Contract

A production collector should expose a CLI that can be run by FinClaw and produce
one or more of:

```text
<out-dir>/
├── lake/<collector-id>/events.jsonl
├── manifest.json
├── investor_wiki_evidence.v1.json
└── SUMMARY.md
```

The minimum useful output is `events.jsonl`, where each line is a
`collectorx.event.v1` object.

Before running a catalog entry, FinClaw should look up the same `id` in
`collectors/finclaw-invocation-contracts.json` and show the matching
`user_step`. If the preflight cannot be satisfied, FinClaw should surface the
contract `failure_state` instead of running the collector and treating an empty
result as personal data.

FinClaw can use the helper CLI instead of joining the JSON files itself:

```bash
python3 tools/finclaw_catalog.py list --json
python3 tools/finclaw_catalog.py show ths-watchlist --json
python3 tools/finclaw_catalog.py doctor \
  --priority P0 \
  --out-dir-root /path/to/run \
  --json
python3 tools/finclaw_catalog.py runbook \
  --priority P0 \
  --out-dir-root /path/to/run \
  --json
python3 tools/finclaw_catalog.py batch-manifest \
  --priority P0 \
  --out-dir-root /path/to/run \
  --json
python3 tools/run_finclaw_batch.py \
  --priority P0 \
  --out-dir-root /path/to/run \
  --json
python3 tools/finclaw_catalog.py plan ths-watchlist \
  --set authorized-ths-watchlist-root=/path/to/tonghuashun/root \
  --out-dir /path/to/out \
  --json \
  --require-ready
```

The `plan` output includes `ready_to_run`, unresolved placeholders, the display
`command`, executable `argv`, `package_validation`, `next_action`,
`blocked_reason`, `user_step`, `preflight`, `failure_state`, product surface,
and evidence role. The `doctor` output gives the same fields for every selected
catalog entry, plus summary counts by priority, category, runner, and
`next_action`; FinClaw should use it to render collector setup and authorization
checklists.

For batch collection, FinClaw should use `runbook --json`. The runbook keeps the
same item shape as `doctor` but groups entries into product execution stages:

- `ready_collectors`: source collectors that can run now.
- `ready_lenses`: investor lenses whose upstream Lake paths have been supplied.
- `needs_upstream_lake`: lenses that should wait until upstream Lake events
  exist.
- `needs_user_input`: collectors that need authorized files, folders, accounts,
  or placeholder values.
- `soulmirror_runner`: collectors that must be delegated to the SoulMirror
  runner.

By default, `runbook` auto-fills deterministic lens inputs named
`<upstream-id-events-jsonl>` when the upstream collector is also selected,
ready to run, and has a known output package directory. For example, a P0
runbook with `--out-dir-root /path/to/run` will point `email-research` at
`/path/to/run/email/lake/email/events.jsonl` after `email` is collected. Use
`--no-auto-link-upstream` when the product needs to force explicit upstream Lake
selection.

For the actual product runner, `batch-manifest --json` is the compact execution
contract. It keeps the same filtering and auto-linking behavior as `runbook`,
but emits:

- `ready_steps`: ordered command steps with `argv`, dependency ids, output
  directory, expected `lake_events_jsonl`, optional `input_events_jsonl`, and
  `post_run_validation`.
- `blocked_steps`: non-runnable entries with `next_action`,
  `missing_placeholders`, `requires_upstream`, `user_step`, `preflight`, and
  `failure_state`.
- `auto_upstream_links`: the deterministic Lake paths the helper filled in for
  lens inputs.

FinClaw should execute only `ready_steps[*].argv`, in listed order, and run
`ready_steps[*].post_run_validation.argv` before treating that step's output as
Lake-ready. `display_command` is for UI and audit display only.

FinClaw may delegate that loop to `tools/run_finclaw_batch.py`. The runner can
read an existing manifest with `--manifest <path>` or build one with the same
filters as `batch-manifest`. It defaults to dry-run mode and reports the steps
that would run without touching local user data. Add `--execute` only after the
user has granted the required authorization. In execute mode, the runner stops
on the first failed collector or failed package validation unless
`--continue-on-error` is supplied. A collector command that succeeds without a
ready post-run validation command is still reported as a validation failure. Use
`--skip-validation` only for debugging; production runs should keep the post-run
validation gate enabled.

Product runners should use `--require-ready` before ordinary shell execution.
If the helper exits with status `2`, FinClaw should parse the same JSON
response and follow `next_action` instead of running the command:

- `run_command`: execute the rendered `argv` list without shell reparsing, then
  run `package_validation.argv` when `package_validation.ready=true`. The
  `command` string is for display and audit only.
- `fill_placeholders`: ask the user for the missing authorized file, folder,
  account precondition, or output path shown in `missing_placeholders`.
- `wait_for_upstream_lake`: run or select the upstream collectors shown in
  `requires_upstream`, then provide the resulting Lake `events.jsonl` path.
- `use_soulmirror_runner`: hand the request to the SoulMirror-managed runner
  instead of treating the catalog command as a shell command.

SoulMirror-owned collectors such as TickTick report `runner=soulmirror` and
`blocked_reason=soulmirror_runner_required`, so the product does not treat them
as ordinary shell commands. Lens collectors with missing upstream inputs report
`next_action=wait_for_upstream_lake`, so the product does not ask the user to
upload arbitrary files when it should first run the upstream Lake collector.

## Package Gate

After any collector finishes, FinClaw should validate the output directory
before adding it to the durable Lake or running a downstream lens. Product
runners should prefer the `package_validation.argv` emitted by `plan` or
`doctor`, because it already contains the package directory, collector id, JSON
output flag, and `--require-evidence` when needed.

Generic collector example:

```bash
python3 tools/validate_collector_package.py \
  <out-dir> \
  --collector <collector-id> \
  --json
```

For vertical collectors or investor lenses that are expected to produce Wiki
evidence, the generated package-validation argv requires the evidence package
at the same gate:

```bash
python3 tools/validate_collector_package.py \
  <out-dir> \
  --collector <collector-id> \
  --require-evidence \
  --json
```

The package gate checks:

- `manifest.json` is present and readable.
- `lake/<collector-id>/events.jsonl` exists and contains valid JSONL.
- Every event uses `collectorx.event.v1` and has the required event, privacy,
  raw-reference, and data fields.
- If `investor_wiki_evidence.v1.json` is present, it passes the Investor Wiki
  evidence contract.

FinClaw should treat a failed package gate as "collection incomplete" and show
the user the next action from `manifest.json` when available. It should not
silently distill a failed package into the investor Wiki.

SoulMirror-style snapshot collectors, such as `ticktick`, are one step earlier
in the pipeline: the skill returns a JSON array to AgentRunner, then the
SoulMirror daemon diffs the snapshot and writes `lake/<collector-id>/events.jsonl`.
Run the package gate after the daemon has written that Lake output.

## Investor Wiki Evidence Contract

If a collector emits `investor_wiki_evidence.v1.json`, FinClaw should validate
it before running the investor-portrait distillation step:

```bash
python3 tools/validate_investor_wiki_evidence.py \
  <out-dir>/investor_wiki_evidence.v1.json
```

Strict validation requires:

- schema `finclaw.investor_wiki_evidence.v1`
- `wiki_write_policy.collector_writes_wiki_directly=false`
- `wiki_write_policy.raw_json_writes_wiki_directly=false`
- the required flow `collectorx.event.v1 -> finclaw.investor_wiki_evidence.v1
  -> SoulMirror investor-portrait distill/organize`
- canonical `external.investor / 7 dimensions / 20 subdimensions` coverage
- per-subdimension support level, evidence count, route targets, signals, gaps,
  and privacy metadata

Collectors may still enter the Lake with only `events.jsonl`, but route-only
evidence packages should not be distilled into the investor Wiki unless they
pass this contract or are explicitly run with a migration exception.

## Current Runnable Examples

### 东方财富

```bash
python3 skills/eastmoney-portfolio/scripts/eastmoney_query.py \
  --collect-local \
  --auto-trade-ui \
  --sync-soulmirror \
  --output <out-dir>
```

Preconditions:

- User has installed and logged into EastMoney.
- For strong trade tables, the trading account must be manually unlocked by the user.
- macOS Accessibility permission is required for read-only UI capture.

Do not ask for or store trading password, login password, cookie, token, session,
signature, or device fingerprint.

### 同花顺

```bash
python3 skills/ths-portfolio/scripts/ths_query.py \
  --local-scan \
  --include-metadata-events \
  --include-gui-events \
  --output <out-dir> \
  --sync-soulmirror
```

Preconditions:

- User has authorized local app/file access.
- GUI snapshot requires the relevant trading page to be visible/unlocked.

### 同花顺自选股

```bash
python3 skills/ths-watchlist/scripts/ths_watchlist.py collect \
  --local-scan \
  --container-root <authorized-ths-watchlist-root> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized Tonghuashun local watchlist files or exports into
  `ths-watchlist` `watchlist` events.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, TXT, and ZIP
  packages through `--input`, and local discovery through `--local-scan`.
- Captures symbol, name, market, group, industry, tags, note/reason, and
  added time when present.
- `manifest.collection_audit` records requested inputs, missing inputs,
  resolved files, local-scan platform/root/candidate files, skipped files,
  skipped reasons, path-level parse results, ZIP member provenance, unsafe ZIP
  member skips, and limit truncation.
- `manifest.field_coverage` and `manifest.ths_watchlist_boundary_proof` tell
  FinClaw what watchlist fields are present and explicitly keep holdings,
  executions, orders, fund flows, and complete attention-universe claims false.
- Recursively filters credential-like raw keys.
- Writes `investor_wiki_evidence.v1.json` with canonical 7/20 Investor Wiki
  coverage for attention-universe subdimensions.
- This is attention-universe evidence only. It does not prove holdings, trades,
  orders, or fund flows; use `ths-portfolio` for strong trading evidence.

### 微信聊天

```bash
python3 skills/wechat-export/scripts/wechat_query.py \
  --collect \
  --days 30 \
  --out-dir <out-dir>
```

Current status:

- Converts authorized WeChat 4.x local query results into a standard
  CollectorX package: `lake/wechat/events.jsonl`, `manifest.json`, and
  `SUMMARY.md`.
- The legacy `--out <file>` compact JSON array remains available for older
  automation, but FinClaw should prefer `--out-dir`.
- Captures owner-relevant private chats plus explicitly included or recently
  owner-active groups, with chat name, sender, time, text, sender ownership,
  field coverage, filter policy, source audit, and generic-to-lens evidence
  policy.
- Does not output WeChat encryption keys, passwords, cookies, tokens, raw
  database pages, or direct investment conclusions.
- This is a generic communication collector. Feed `lake/wechat/events.jsonl`
  into `wechat-investment-dialogue` before using any result as investor Wiki
  evidence.

Preconditions:

- User has authorized local WeChat access.
- macOS WeChat 4.x needs per-database keys from the documented extractor; on
  the current Mac, real-source validation is still blocked by the key/SIP
  precondition.
- Windows/Linux need the supported local database path and authorized key or
  decrypted database setup.

### QQ 聊天

```bash
python3 skills/qq-export/scripts/qq_query.py \
  --db-dir <authorized-qq-db-dir> \
  collect \
  --out-dir <out-dir>
```

Current status:

- Converts authorized readable QQ message databases into a standard CollectorX
  package: `lake/qq/events.jsonl`, `manifest.json`, `qq.collect.json`, and
  `SUMMARY.md`.
- Captures owner-relevant private chats plus explicitly included or recently
  owner-active groups, with chat, sender, time, text, sender ownership, field
  coverage, filter policy, source audit, communication surface summary, and
  generic-to-lens evidence policy.
- If no readable QQ database is available, writes an explicit gap package with
  `collection_readiness.status=needs_readable_qq_db`, so FinClaw can guide the
  user instead of mistaking the run for a complete collection.
- Does not output QQ passphrases, decrypted keys, passwords, cookies, tokens,
  raw database pages, or direct investment conclusions.
- This is a generic communication collector. Feed `lake/qq/events.jsonl` into
  an investor communication lens before using any result as investor Wiki
  evidence.

Preconditions:

- User has authorized local QQ access.
- For QQ NT, the user must provide or prepare a readable/decrypted database
  through the documented read-only flow. On the current Mac, passphrase capture
  is still blocked by the local LLDB/SIP precondition.
- Windows/Linux need the supported local database path or authorized decrypted
  database setup.

### 本地文件

```bash
python3 skills/filesystem-collector/scripts/filesystem_query.py collect \
  --root ~/Documents \
  --out-dir <out-dir>
```

Preconditions:

- User selects scan roots.

Boundary:

- This collector is metadata-only. It records path, extension, size, and mtime.
- It does not read file content. Research content reading belongs to the
  explicit `research-documents` lens step below.
- `manifest.source_audit` records requested/resolved roots, scanned/emitted
  file counts, extension coverage, skipped file/directory counts, skipped
  reasons, size policy, ignored directories, and per-root scan results.
- The manifest records the macOS/Windows/Linux default-root plan for product
  preflight, but FinClaw should still pass explicit user-authorized roots when
  possible.

### 研报 / 财报 / 估值表内容

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source research-documents \
  --input <authorized-research-folder> \
  --include-content \
  --include-image-ocr \
  --out-dir <out-dir>
```

Current status:

- Reads content only when `--include-content` is explicitly supplied.
- Supports Markdown/TXT/HTML, CSV/TSV, XLSX/XLSM, legacy XML/HTML/text `.xls`,
  renamed OOXML `.xls`, binary BIFF `.xls` through optional `xlrd`, PPTX,
  DOCX, and PDF extraction.
- Binary BIFF `.xls` without `xlrd` emits `content_extract.status:
  extract_failed`, parser `xlrd-biff`, and an explicit error instead of
  fabricating content.
- Extracted text is capped and carries parser/status metadata.
- `manifest.collection_audit` records requested inputs, missing inputs, per-file
  parse results, candidate counts, filtered counts, skipped reasons, extension
  coverage, parser counts, content-read counts, limit truncation, and the active
  content policy.
- `manifest.research_corpus_boundary_proof` and `manifest.lens_surface_summary`
  summarize which authorized research corpus was actually covered, including
  report/financial-statement/valuation/announcement/review/screenshot/table
  surfaces, parser coverage, metadata-only files, content reads, and OCR reads.
- Screenshots/images stay metadata-only by default. OCR is performed only when
  `--include-image-ocr` is explicitly supplied and a local `tesseract` engine is
  available through `PATH` or `COLLECTORX_TESSERACT_CMD`.
- If OCR is requested but unavailable or fails, the run keeps metadata-only
  evidence and records the OCR status in `manifest.collection_audit` and
  per-file `path_results`.
- Broad file-title hints such as a lone "股票" or "基金" do not enter Wiki
  evidence without stronger research context.
- Generic `filesystem` remains metadata-only; investment routing stays in the
  `research-documents` lens.

### 邮件研报

```bash
python3 skills/email-collector/scripts/email_api.py collect \
  --account all \
  --out-dir <out-dir>
```

Fallback for authorized local mail roots:

```bash
python3 skills/email-collector/scripts/email_api.py import \
  --local-scan \
  --container-root <authorized-email-root> \
  --out-dir <out-dir>
```

Fallback for local authorized exports:

```bash
python3 skills/email-collector/scripts/email_api.py import \
  --input <authorized-email-export-or-folder> \
  --out-dir <out-dir>
```

Current status:

- IMAP `collect --out-dir`, local `import --local-scan --out-dir`, and local
  `import --input --out-dir` all write
  `lake/email/events.jsonl`, `manifest.json`, and `SUMMARY.md`.
- Manifest output records account/folder audit, field coverage, body policy,
  attachment policy, mailbox boundary proof, and the generic-to-lens evidence
  boundary.
- Local scan/import supports user-authorized EML, Apple Mail EMLX, Maildir,
  MBOX, Thunderbird no-extension mbox, JSON/JSONL/NDJSON, CSV/TSV, and ZIP
  packages. Maildir detection is limited to RFC822-like files under `cur/` and
  `new/`; Thunderbird detection is limited to `Mail/`/`ImapMail/` mbox files
  or files with `.msf` sidecar proof, and `.msf` indexes are recorded as
  skipped index files.
- Local scan/import manifests record requested inputs, local-scan platform/root
  and candidate files, missing inputs, per-file parse results, extension
  coverage, skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  Apple Mail/Maildir/Thunderbird counts, local-scan root status, archive
  provenance, and `--limit` truncation.
- Local scan probe, manifest, and raw refs mask path email addresses and long
  numeric account fragments.
- `manifest.mailbox_boundary_proof` tells FinClaw which account/folder/time
  window or local export boundary was actually collected and explicitly keeps
  complete-mailbox-history claims false.
- Full bodies are excluded by default and require explicit `--event-include-body`.
- Attachment bodies are never written; only filename, content type, and size are
  retained.
- If no mailbox is registered, IMAP authorization fails, or the selected folders
  have no matching mail, the collector writes an explicit gap event and next
  action instead of pretending the mailbox was collected.
- Feed `lake/email/events.jsonl` into `email-research` before using broker
  research, IR, roadshow, or research-attachment evidence in the investor Wiki.
- `email-research` writes `manifest.lens_surface_summary` and
  `manifest.email_research_boundary_proof` for morning meetings, broker
  research, roadshow invitations, company IR threads, earnings/announcement
  alerts, research attachment refs, sender domains, body-preview coverage, and
  attachment boundaries. It keeps complete-mailbox claims, full-body Wiki
  inclusion, and attachment-body collection false.

### 雪球投资活动

```bash
python3 skills/xueqiu-watchlist/scripts/xueqiu_query.py collect \
  --input <authorized-xueqiu-watchlist-export-or-folder> \
  --out-dir <out-dir>
```

Current status for `xueqiu-watchlist`:

- Converts authorized Xueqiu watchlist exports into `xueqiu-watchlist`
  `watchlist` events.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, TXT, and ZIP
  packages.
- Captures symbol, code, market, name, group, industry, tags, note/reason, and
  followed time when present; ZIP packages preserve `archive.zip::member`
  provenance and skip path-traversal members.
- Manifest records source audit, extension coverage, ZIP member/skipped-member
  counts, parsed/filtered record counts, and watchlist field coverage.
- Recursively filters credential-like raw keys.
- Writes `investor_wiki_evidence.v1.json` with canonical 7/20 Investor Wiki
  coverage for attention-universe subdimensions.
- This is attention-universe evidence only. It does not prove holdings, trades,
  orders, or fund flows.

```bash
python3 skills/xueqiu-investor-activity/scripts/xueqiu_activity.py collect \
  --input <authorized-xueqiu-export-har-or-browser-history-copy> \
  --out-dir <out-dir> \
  --sync-soulmirror
```

Current status:

- Parses authorized JSON/JSONL/CSV/TSV/XLSX/XLSM/HTML/TXT/ZIP exports for
  watchlists, follows, posts, comments, favorites, saved pages, and owner
  portfolio/rebalance records.
- Also accepts user-authorized browser network `.har` exports and only reads
  `xueqiu.com` response bodies. Request headers, cookies, Authorization values,
  and URL query strings are stripped before events, manifest, or Wiki evidence
  are written.
- Also accepts user-authorized copied Chromium `History`, Safari `History.db`,
  `.sqlite`, `.sqlite3`, or `.db` browser history files. Only `xueqiu.com` and
  subdomain visits are emitted; source browser app, visit count, typed count,
  and transition type are retained when present.
- Normalizes Snowball-like `statuses/list/data/items/stocks/cubes` payloads,
  preserves ZIP member provenance, strips credential-like keys from retained raw
  metadata, and writes a standard `investor_wiki_evidence.v1.json`.
- Manifest records source audit, extension coverage, ZIP member/skipped-member
  counts, HAR entry/endpoint/skip-reason coverage, browser-history boundary
  proof, parsed records, pagination marker fields, activity field coverage,
  source-surface coverage, `activity_boundary_proof`, and pagination
  completeness.
- Saved HTML pages are parsed as `saved_page` activity and stay non-trade
  evidence.
- `activity_boundary_proof` reports whether watchlist, followed users,
  followed portfolios, portfolio activity, comments, favorites, posts, and saved
  pages were observed. Pagination completeness remains partial and never claims
  a complete timeline without real account validation.
- Not yet a one-click login/session collector; the HAR and browser-history
  paths are authorized local baselines for user-owned account usage evidence.
- Not a broker-confirmed trade source.

### 中国基金理财资产

```bash
python3 skills/china-wealth-assets/scripts/china_wealth.py collect \
  --input <authorized-fund-or-wealth-export> \
  --out-dir <out-dir> \
  --sync-soulmirror
```

Current status:

- Parses authorized CSV/TSV/JSON/JSONL/XLSX/XLSM/legacy `.xls`/HTML table/PDF statement/TXT/ZIP exports for fund
  holdings, wealth holdings, cash-management holdings, subscriptions,
  redemptions, dividends, and asset snapshots.
- PDF statements are parsed locally with `pdfplumber`; manifests record PDF
  file/page/table/record counts and keep OCR disabled unless a future explicit
  OCR adapter is added.
- Also accepts user-authorized browser network `.har` exports for whitelisted
  Alipay, Tiantian Fund, Danjuan, Qieman, and bank wealth domains. Only response
  bodies are parsed; request headers, cookies, Authorization values, and URL
  query strings are stripped before events, manifest, or Wiki evidence are
  written.
- Normalizes platform names for Alipay, Tiantian Fund, Danjuan, Qieman, and
  bank wealth exports, preserves numeric asset/trade fields from workbook,
  legacy `.xls`, Excel XML, HTML table, and PDF statement exports, records ZIP member
  provenance, and strips credential-like raw keys.
- Per-platform one-click adapters for Alipay/Tiantian/Danjuan/Qieman/banks still
  need real validation; the HAR path is an authorized browser export baseline
  for real-account responses.
- Any parsed input is treated as partial authorized input until platform/account
  coverage is verified.
- `manifest.platform_coverage` tells FinClaw which expected P0 platforms were
  observed in the authorized input and which are still missing.
- `manifest.field_coverage` and `manifest.asset_value_summary` tell FinClaw
  which key asset fields are present and summarize this run's authorized values
  by platform.
- `manifest.asset_boundary_proof` tells FinClaw whether each platform/account
  has named account refs, asset snapshots, holding surfaces, transaction
  surfaces, and numeric value fields. Levels are `strong_partial`,
  `medium_partial`, or `weak_partial`; none of them claim complete account
  coverage without real account/read-only-screen validation.
- `manifest.collection_audit` records input count, resolved files, extension
  coverage, HAR entry/platform/endpoint/skip-reason coverage, ZIP
  member/skipped-member counts, parsed record count, emitted event count, and
  path-level parse results.

### 笔记

```bash
python3 skills/notes-collector/scripts/notes_api.py obsidian \
  --vault <authorized-obsidian-vault> \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

For authorized exports from Youdao, Evernote/Yinxiang, Notion exports,
Markdown/HTML/TXT folders, JSON/CSV/TSV note exports, or ZIP export packages:

```bash
python3 skills/notes-collector/scripts/notes_api.py import \
  --input <authorized-notes-export-or-folder> \
  --source-app auto \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

When the user only authorizes a specific source, notebook/folder, or tag scope,
pass explicit source-policy filters before Lake output:

```bash
python3 skills/notes-collector/scripts/notes_api.py import \
  --input <authorized-notes-export-or-folder> \
  --source-app auto \
  --allow-source-app notion \
  --allow-path "Notion Export" \
  --allow-tag 投资 \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

Current status:

- Emits generic `notes` events and a standard package.
- Supports authorized local import for Markdown, Obsidian Canvas, HTML, TXT,
  JSON/JSONL, CSV/TSV table exports, Evernote ENEX, and ZIP packages containing
  those formats. CSV/TSV rows are converted into note events so Notion
  databases, rules tables, review tables, and research checklists can enter the
  notes lake; `.canvas` files preserve text nodes, linked files, linked URLs,
  node counts, and edge counts.
- Writes `manifest.platform_coverage` with expected P1 note platforms
  (`obsidian`, `notion`, `youdao`, `evernote`), observed platforms, missing
  platforms, event counts, and `real_account_validation`.
- Writes `manifest.field_coverage`, `source_audit`, and `content_policy` so
  FinClaw can tell whether title/path/content preview/tags/time fields are
  present, whether per-input parse results and ZIP member provenance exist,
  which files or archive members were skipped and why, how many table files and
  rows were imported, how many Canvas files/notes were imported, whether
  source-app/path/tag authorization filters were applied, how many candidate
  notes were filtered by policy, and whether the run used preview-only or
  full-content authorization.
- Does not claim investment-note status directly.
- Feed `lake/notes/events.jsonl` into `investment-notes` lens for investor Wiki
  evidence.
- The `investment-notes` lens writes `manifest.investment_note_boundary_proof`
  with source-app, preview/full-content, tag/path/URL, candidate/matched/filtered,
  and note-type boundaries. It does not claim a complete notes vault.

### 滴答清单 / 任务

```bash
python3 skills/ticktick-cli/scripts/auth.py status --json
python3 skills/ticktick-cli/scripts/collect_for_soulmirror.py
```

Current status:

- The primary live path follows SoulMirror's original shape:
  `collectors/generic/ticktick.yaml` + AgentRunner + `ticktick-cli` skill.
- `collect_for_soulmirror.py` is dependency-light and returns one JSON array
  snapshot for the daemon to diff.
- The SoulMirror daemon, not the skill, owns durable
  `lake/ticktick/events.jsonl` writes and snapshot state.
- If auth is missing, the collector fails clearly with
  `ticktick_auth_required`; it must not return `[]` because that would falsely
  mean the authorized account has no tasks.
- Authorization is a separate user-facing action. During scheduled or immediate
  collection, AgentRunner must not start OAuth, open a browser, or run
  `auth.py connect` / `auth.py register` / `auth.py authorize`.
- When auth is missing, any structured error belongs to stderr only; AgentRunner
  should leave the snapshot/result file empty or absent and show
  `TICKTICK_AUTH_REQUIRED 需要先通过“连接滴答清单”完成 OAuth 授权。`
- The snapshot captures active tasks plus recent completed tasks, with stable
  ids, title, project, project id, status, priority, tags, due/start time, and
  raw task fields. It also exposes timezone, repeat/reminder fields, and
  checklist counts when the API returns checklist/subtask items.
- `auth.py connect` supports a FinClaw-managed OAuth Broker through
  `TICKTICK_OAUTH_BROKER_URL` so ordinary users do not need to create their own
  Dida365 developer app.
- Local tests cover missing-auth behavior and an authorized fake OpenAPI server
  for active/completed tasks, project-name mapping, inbox handling, dedupe, and
  no token leakage in snapshot output.
- `ticktick_events.py collect` remains available only for offline authorized
  JSON/JSONL/ZIP export conversion and writes `exports/ticktick/events.jsonl`
  to avoid confusing that helper with SoulMirror daemon-owned Lake writes.

Offline conversion helper:

```bash
python3 skills/ticktick-cli/scripts/ticktick_events.py collect \
  --input <authorized-ticktick-task-json-or-zip> \
  --allow-project 投资研究 \
  --allow-tag 投资 \
  --out-dir <out-dir>
```

Offline helper status:

- Writes `manifest.platform_coverage` with `ticktick`/`dida365` source
  coverage, missing sources, event counts, and `real_account_validation`.
- Optional source-app/project/tag/keyword allow/deny filters are applied before
  offline package output. `manifest.source_audit.task_scope_policy` records the
  configured filters, candidate task count, filtered task count, filter reason
  counts, and `policy_does_not_assert_investment_relevance=true`.
- If authorized input exists but every candidate task is outside the selected
  scope, readiness reports `scope_policy_filtered_all`.
- Writes `manifest.field_coverage`, `time_status_summary`, `source_audit`, and
  `evidence_policy` so FinClaw can inspect title/project/status/start/due/
  completion/timezone/all-day/recurrence/reminder/checklist coverage, overdue
  counts, invalid start/due ranges, repeat-frequency counts, checklist item
  totals/completed/pending counts, ZIP provenance, total/skipped ZIP members,
  skip reasons, per-input parse results, and the required
  `task-calendar-investor` lens boundary.
- Filters credential-like raw keys such as password, cookie, token, session,
  secret, authorization, and credential.
- Does not claim investment-task status directly.
- Feed daemon-written `lake/ticktick/events.jsonl` into
  `task-calendar-investor` lens for trading plans, research tasks, and review
  reminders.
- Real account validation still requires deploying the managed OAuth Broker and
  running against an authorized user account.

### 日历

```bash
python3 skills/calendar-collector/scripts/calendar_query.py collect \
  --input <authorized-calendar-ics-json-csv-or-zip> \
  --allow-calendar 投资日历 \
  --allow-keyword 复盘 \
  --out-dir <out-dir>
```

Current status:

- Converts authorized ICS, JSON/JSONL, CSV, TSV, and ZIP exports into generic
  `calendar` events.
- Captures title, start/end time, all-day status, location, meeting links,
  organizer, attendees, recurrence, reminders, duration, multi-day status, and
  invalid time ranges.
- Writes `manifest.platform_coverage` with expected P1 calendar platforms
  (Apple, Google, Outlook, Feishu, DingTalk, WeCom, Tencent Meeting), observed
  platforms, missing platforms, event counts, and `real_account_validation`.
- Optional source-platform/calendar/attendee/keyword allow/deny filters are
  applied before Lake output. `manifest.source_audit.calendar_scope_policy`
  records the configured filters, candidate event count, filtered event count,
  filter reason counts, and `policy_does_not_assert_investment_relevance=true`.
- If authorized input exists but every candidate calendar event is outside the
  selected scope, readiness reports `scope_policy_filtered_all`.
- Writes `manifest.field_coverage`, `time_surface_summary`, `source_audit`, and
  `evidence_policy` so FinClaw can inspect start/end, meeting URL, attendees,
  recurrence, reminders, duration coverage, all-day/multi-day events, invalid
  time ranges, same-calendar conflict pairs, ZIP provenance, total/skipped ZIP
  members, skip reasons, per-input parse results, and the required lens
  boundary.
- Does not claim investment-calendar status directly.
- Feed `lake/calendar/events.jsonl` into `task-calendar-investor` lens for
  trading plans, earnings events, research meetings, and review reminders.
- The `task-calendar-investor` lens writes
  `manifest.task_calendar_boundary_proof` with authorized input counts,
  upstream task/calendar source counts, candidate/matched/filtered counts,
  time/reminder/meeting-link/timezone/repeat coverage, task checklist execution
  structure, calendar time-quality fields, and an explicit
  no-complete-task-list/no-complete-calendar boundary.

### 飞书通用授权导入

```bash
python3 skills/feishu/scripts/feishu_api.py collect \
  --input <authorized-feishu-export> \
  --out-dir <out-dir>
```

Current status:

- Preserves the legacy Feishu OAuth/API utility commands while adding a
  CollectorX package path for authorized local exports.
- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, and ZIP
  Feishu exports into generic `feishu` events.
- Captures messages, chats, contacts, documents, file refs, folders, meeting
  refs, recording refs, participants, links, document refs, content previews,
  and source provenance.
- Writes `manifest.field_coverage`, `feishu_surface_summary`, `source_audit`,
  and `evidence_policy` so FinClaw can inspect message/document/file/meeting
  coverage, ZIP provenance, total/skipped ZIP members, skip reasons,
  per-input parse results, and required downstream lenses.
- Filters credential-like raw keys including app secrets, cookies, access
  tokens, refresh tokens, authorization, session, and password fields.
- Does not claim investment evidence directly.
- Feed `lake/feishu/events.jsonl` into downstream investor lenses such as
  `meeting-minutes`, `research-documents`, and future collaboration dialogue
  lenses.
- Real Feishu account/API collection still requires user authorization and
  tenant-permission validation.

### 钉钉 / 企业微信协作导出

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform dingtalk \
  --input <authorized-dingtalk-export> \
  --allow-chat <authorized-investment-chat-or-group> \
  --deny-keyword <out-of-scope-keyword> \
  --out-dir <out-dir>
```

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform wecom \
  --input <authorized-wecom-export> \
  --allow-chat <authorized-investment-chat-or-group> \
  --deny-keyword <out-of-scope-keyword> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, and ZIP
  collaboration exports into `dingtalk` or `wecom` events.
- Captures messages, chats, contacts, file refs, meeting refs, sender, receiver,
  department, participants, meeting links, file names, tags, and content
  previews.
- Optional source-platform, record-kind, chat, sender, participant, and keyword
  allow/deny filters run before Lake output. `manifest.source_audit`
  includes `collaboration_scope_policy`, candidate count, filtered count,
  reason counts, and `scope_policy_filtered_all` when all candidates are
  outside the authorized scope.
- Writes `manifest.field_coverage`, `collaboration_surface_summary`,
  `source_audit`, and `evidence_policy` so FinClaw can inspect message/meeting/
  file/contact coverage, ZIP provenance, total/skipped ZIP members, skip
  reasons, per-input parse results, and required downstream lenses.
- Filters credential-like raw keys and keeps file bodies out of the generic
  collaboration collector.
- Does not claim investment collaboration directly.
- Feed `lake/dingtalk/events.jsonl` and `lake/wecom/events.jsonl` into
  downstream investor lenses such as `meeting-minutes`, future collaboration
  dialogue lenses, and research-document routing.

### 会议产物

```bash
python3 skills/meeting-artifacts/scripts/meeting_artifacts.py collect \
  --input <authorized-meeting-minutes-transcript-folder-or-zip> \
  --allow-source-platform <feishu|dingtalk|wecom|tencent-meeting> \
  --allow-keyword <authorized-investment-meeting-keyword> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized local minutes/transcript/subtitle files, ZIP packages,
  and common platform export files into generic `meeting-artifacts` events.
- Supported export shapes include Markdown, TXT, HTML, JSON/JSONL/NDJSON,
  CSV/TSV, VTT, and SRT.
- Normalizes Feishu, DingTalk, WeCom, and Tencent Meeting platform evidence
  into stable platform values and captures participants, organizer, meeting
  links, start/end time, text preview, participant-role hints, action items,
  decision points, risk items, mentioned symbols, attachment refs, and
  recording refs where present.
- Optional source-platform, participant, and keyword allow/deny filters run
  before Lake output. `manifest.source_audit` includes
  `meeting_scope_policy`, candidate count, filtered count, reason counts, and
  `scope_policy_filtered_all` when every candidate meeting is outside the
  authorized scope.
- Writes `manifest.platform_coverage` with expected P1 meeting platforms,
  observed platforms, missing platforms, event counts, and
  `real_account_validation`.
- Writes `manifest.field_coverage`, `meeting_surface_summary`, `source_audit`,
  and `evidence_policy` so FinClaw can inspect text, participants, organizer,
  participant roles, meeting URL, attachments, recording refs, action items,
  decision points, risk items, mentioned symbols, duration, start/end time,
  requested inputs, missing paths, unsupported file extensions, ZIP
  provenance, total/skipped ZIP members, skip reasons, per-input parse
  results, and the required `meeting-minutes` lens boundary.
- Filters credential-like raw keys such as password, cookie, token, session,
  secret, authorization, and credential.
- Does not claim investment-meeting status directly.
- Feed `lake/meeting-artifacts/events.jsonl`, `lake/feishu/events.jsonl`,
  `lake/dingtalk/events.jsonl`, or `lake/wecom/events.jsonl` into the
  `meeting-minutes` lens for roadshow, research, IC, expert-call,
  earnings-call, decision-point, risk-discussion, and follow-up surfaces.
- The `meeting-minutes` lens writes `manifest.meeting_minutes_boundary_proof`
  with authorized input counts, upstream meeting/collaboration source counts,
  candidate/matched/filtered counts, participant coverage, meeting-link
  coverage, participant-role coverage, decision/action/risk item coverage,
  attachment/recording reference coverage, time coverage, and an explicit
  no-complete-meeting-history/no-complete-workspace boundary.
- Feishu/DingTalk/WeCom/Tencent Meeting account API adapters still require
  real authorization validation.

### 微信收藏 / 公众号文章

```bash
python3 skills/wechat-favorites/scripts/wechat_favorites.py collect \
  --input <authorized-wechat-favorites-saved-article-folder-or-zip> \
  --allow-source-account <authorized-public-account-or-author> \
  --allow-domain mp.weixin.qq.com \
  --deny-keyword <out-of-scope-keyword> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL, CSV/TSV, HTML, Markdown, TXT, and ZIP
  saved-article records into generic `wechat-favorites` events.
- Writes `manifest.action_coverage` with expected user actions: favorite,
  read, share, and saved file.
- Writes `manifest.field_coverage`, `manifest.article_surface_summary`,
  `manifest.article_behavior_summary`, `manifest.source_audit`,
  `manifest.content_policy`, and `manifest.evidence_policy` so Lake can see
  which article/source/behavior fields are actually present before the investor
  lens runs.
- Optional source-account, source-account-type, action, tag, domain, and
  keyword allow/deny filters run before Lake output. `manifest.source_audit`
  includes `wechat_favorites_scope_policy`, candidate count, filtered count,
  reason counts, and `scope_policy_filtered_all` when every candidate record
  is outside the authorized scope.
- `manifest.source_audit` records requested inputs, missing inputs,
  per-file parse results, extension coverage, skipped file reasons, ZIP member
  counts, skipped ZIP member reasons, and path-safety flags.
- Captures ZIP member provenance, source account type, article ID, favorite
  reason, share target, read duration/progress, symbol hints, engagement
  counters, source account count, text length, and filters credential-like raw
  keys.
- Does not claim investment-article status directly.
- Feed `lake/wechat-favorites/events.jsonl` into `wechat-article-favorites`
  lens for investment public-account articles, saved/read/share/saved-file
  action surfaces, source-account types, and broker/fundamental/strategy/
  industry/valuation/portfolio/risk/macro article surfaces.
- The `wechat-article-favorites` lens writes
  `manifest.wechat_article_boundary_proof` with authorized input counts,
  upstream WeChat-favorites source counts, candidate/matched/filtered counts,
  favorite/read/share/saved-file action counts, source-account type counts,
  URL/article-ID/tag/text/time coverage, behavior boundary counts
  (favorite reason, share target, read duration/progress, engagement, symbols),
  and explicit no-complete-favorites, no-complete-read-history, and
  no-public-account-crawl boundaries.
- Real WeChat favorites database/public-account read-history adapters still
  require version-specific validation.

### 财经资讯使用痕迹

```bash
python3 skills/financial-news-usage/scripts/financial_news_usage.py collect \
  --input <authorized-cls-wallstreetcn-gelonghui-usage-export-or-zip-or-history-copy> \
  --out-dir <out-dir>
```

Optional authorization scope filters:

```bash
python3 skills/financial-news-usage/scripts/financial_news_usage.py collect \
  --input <authorized-cls-wallstreetcn-gelonghui-usage-export-or-zip-or-history-copy> \
  --out-dir <out-dir> \
  --allow-platform cls \
  --allow-action favorite \
  --allow-topic industry_theme \
  --deny-keyword 非投资
```

Current status:

- Converts authorized JSON/JSONL, CSV/TSV, HTML, Markdown, TXT, ZIP packages,
  direct Chromium `History`, direct Safari `History.db`, and ZIP-packaged
  browser-history members into
  `financial-news-usage` events.
- Captures user actions: read, favorite, subscribe, search, and alert.
- Writes `manifest.platform_coverage` for CLS, WallstreetCN, and Gelonghui,
  plus `manifest.action_coverage` for expected user actions.
- Writes usage-topic surfaces for macro policy, market strategy, industry
  themes, company fundamentals, HK/US markets, risk events, trading
  opportunities, and portfolio alerts.
- Writes `manifest.field_coverage`, `manifest.usage_surface_summary`,
  `manifest.usage_behavior_summary`, `manifest.source_audit`,
  `manifest.content_policy`, and `manifest.evidence_policy` so Lake can tell
  which usage fields, behavior fields, browser history sources/source-app
  counts, ZIP members, and evidence boundaries are actually present.
- Writes `manifest.usage_boundary_proof` so FinClaw can inspect authorized
  inputs, platform/action/topic coverage, browser-history domain filtering, ZIP
  safety, content pointers, and the explicit no-complete-usage-history /
  no-public-news-crawl / no-public-article-mirror boundaries.
- Optional scope filters narrow authorized records by platform, action,
  source app, domain, usage topic, or keyword before Lake output.
- `manifest.source_audit.financial_news_scope_policy`,
  `scope_policy_filtered_record_count`, `scope_policy_filter_reason_counts`,
  and `financial_news_scope_policy_filtered_all` explain what the authorization
  policy kept or excluded; `collection_readiness.status=scope_policy_filtered_all`
  means the collector ran successfully but the user's policy excluded every
  candidate record.
- `manifest.source_audit` records requested inputs, missing inputs, per-file
  parse results, extension coverage, skipped file reasons, ZIP member counts,
  skipped ZIP member reasons, browser-history source apps/source-app counts,
  and path-safety flags.
- For browser history, filters to CLS, WallstreetCN, and Gelonghui domains
  before writing events.
- Captures domain, source app, URL, title, visit time, visit count, typed
  count, Safari load status, query terms, subscription target, alert condition,
  notification channel, trigger source, referrer, session ID, dwell seconds,
  browser transition type, tags, symbols, and article ID where present.
- Preserves file/ZIP member provenance in `raw_ref.path`, `source_archive`,
  and `archive_member`.
- Recursively filters credential-like raw keys.
- Outputs `investor_wiki_evidence.v1.json` for information-consumption and
  monitoring-rule evidence.
- Does not crawl public news or platform-wide content.
- Real CLS/WallstreetCN/Gelonghui app caches, account APIs, subscription
  stores, real Safari/macOS history samples, and Windows/Linux browser-history
  paths still require account/device-level validation.

### 港美股券商

```bash
python3 skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect \
  --input <authorized-futu-tiger-ibkr-readonly-export-or-zip> \
  --out-dir <out-dir>
```

Optional authorization scope filters:

```bash
python3 skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect \
  --input <authorized-futu-tiger-ibkr-readonly-export-or-zip> \
  --out-dir <out-dir> \
  --allow-broker futu \
  --allow-account F-1 \
  --allow-subtype position \
  --allow-market US \
  --allow-currency USD
```

Current status:

- Converts authorized CSV/TSV/JSON/JSONL/NDJSON/XLSX/XLSM/ZIP exports into
  `hk-us-brokerage` events.
- Expands multi-section JSON packages, including assets, positions, executions,
  orders, cashflows, dividends, and FX; ZIP packages preserve source archive
  and member provenance.
- Captures strong brokerage fields: assets, positions, executions, orders,
  cashflows, dividends, FX, margin, tax, settlement dates, order type, time in
  force, net liquidation, and multi-currency amounts.
- Writes broker, trade-surface, and recommended strong-field coverage manifests
  so FinClaw can see missing brokers/tables/fields before treating the package
  as a full brokerage boundary.
- Writes `manifest.strong_trade_surface_summary`,
  `manifest.account_boundary_summary`, `manifest.currency_market_summary`,
  `manifest.fee_tax_margin_summary`, `manifest.asset_value_summary`,
  `manifest.cashflow_activity_summary`, `manifest.income_return_summary`,
  `manifest.order_execution_summary`,
  `manifest.brokerage_boundary_proof`, `manifest.source_audit`, and
  `manifest.evidence_policy` so Lake can see account/currency/market/amount/
  tax/margin availability, reported asset totals by currency, cashflow,
  dividend/FX, income/fee/tax drag, order execution status, export package
  provenance, and read-only boundaries.
- Optional scope filters narrow authorized records by broker, account, strong
  trade subtype, symbol, market, currency, or keyword before Lake output.
- `manifest.source_audit.brokerage_scope_policy`,
  `scope_policy_filtered_record_count`, `scope_policy_filter_reason_counts`,
  and `brokerage_scope_policy_filtered_all` explain what the authorization
  policy kept or excluded; `collection_readiness.status=scope_policy_filtered_all`
  means the collector ran successfully but the user's policy excluded every
  candidate record.
- `manifest.brokerage_boundary_proof` gives FinClaw a single gate for the
  authorized input boundary, broker coverage, strong trade surfaces, account
  IDs, asset values, multi-currency, fee/tax/margin, cashflow activity, income
  return, order execution, Wiki flow, and explicit false claims such as no
  complete brokerage history, no trading password, no order mutation, and no
  direct Wiki write.
- `manifest.source_audit` records requested inputs, missing inputs, per-file
  parse results, extension coverage, skipped file reasons, ZIP member counts,
  skipped ZIP member reasons, parsed/emitted counts, and path-safety flags.
- Preserves business numbers needed by the investor avatar.
- Does not ask for passwords and does not place, cancel, or modify orders.
- Real Futu/Tiger/IBKR account exports or read-only screens still require
  account-level validation.

### 专业金融终端使用痕迹

```bash
python3 skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect \
  --input <authorized-wind-choice-ifind-workflow-export-or-zip> \
  --out-dir <out-dir> \
  --allow-terminal wind \
  --allow-activity download \
  --allow-dataset FA \
  --allow-field Revenue
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  TXT, INI/CONF, LOG, and ZIP workflow records into `pro-terminal-usage`
  events.
- Expands multi-section workflow packages, including workspaces, dashboards,
  watchlists, searches, downloads, exports, templates, models, factors, and
  indicators; ZIP packages preserve source archive and member provenance.
- Captures workspaces, watchlists, searches, downloads, model templates, and
  factor attention.
- Captures workflow metadata such as function codes, menu paths, projects,
  strategy names, datasets, fields, frequency, date ranges, download formats,
  file names, symbols, industries, markets, and regions.
- Captures workflow intensity and lineage metadata such as query terms,
  query/filter parameters, export paths, row counts, workspace IDs, template
  IDs, securities/fields/datasets/factors counts, watchlist sizes, and stable
  lineage refs.
- Optional scope filters can narrow Lake output by terminal, activity,
  workspace, project, dataset, field, or keyword through allow/deny arguments.
  `manifest.source_audit.pro_terminal_scope_policy` records the policy and
  filtered counts; if every candidate record is excluded, readiness becomes
  `scope_policy_filtered_all`.
- Adds per-event `workflow_topics`, `primary_workflow_topic`, and
  `workflow_topic_terms` so FinClaw can map terminal behavior to macro,
  strategy, industry, fundamental, valuation, credit, factor, portfolio,
  data-export, and HK/US research themes.
- Writes terminal, activity, and workflow-field coverage manifests so FinClaw
  can see missing platforms, activity types, or research-workflow metadata.
- Writes `manifest.workflow_surface_summary`, `manifest.source_audit`,
  `manifest.workflow_intensity_summary`, `manifest.workflow_boundary_proof`,
  `manifest.license_policy`, and `manifest.evidence_policy` so Lake can see
  workflow metadata, topic availability, query/export/object-count intensity,
  ZIP/section provenance, and license-safe boundaries before using the evidence.
- `manifest.workflow_boundary_proof` gives FinClaw a single gate for authorized
  input presence, terminal/activity/field/topic coverage, workflow surfaces,
  authorization scope, source audit, license safety, Wiki flow, and explicit
  false claims such as no complete terminal history, no vendor database mirror,
  no licensed content body mirror, no credentials, no license keys, and no
  direct Wiki write.
- `manifest.source_audit` records requested inputs, missing inputs, per-file
  parse results, extension coverage, skipped file reasons, ZIP member counts,
  skipped ZIP member reasons, parsed/emitted counts, and path-safety flags.
- Outputs workflow evidence for capability circle, research workflow, monitoring
  rules, and information-source dimensions.
- Does not copy vendor databases, public market data, reports, or licensed
  content bodies.
- Real Wind/Choice/iFinD/Bloomberg native exports still require license-safe
  account-level validation.

### 社交平台用户活动

```bash
python3 skills/social-activity/scripts/social_activity.py collect \
  --input <authorized-weibo-bilibili-xiaohongshu-activity-export-or-browser-history-copy> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  TXT, Chromium/Safari browser history copies, and ZIP activity records into
  generic `social-activity` events.
- Expands multi-section activity packages such as follows, likes, favorites,
  watch history, comments, shares, and reposts; ZIP packages preserve source
  archive and member provenance.
- Captures follows, likes, favorites, watch/view history, comments, shares, and
  saved pages.
- Captures creator IDs, creator URLs, domains, item IDs, tags, topics, symbols,
  engagement counts, watch progress, and comment/content previews.
- Captures browser-history source apps, visit counts, typed counts, and browser
  transition types after filtering to Weibo/Bilibili/Xiaohongshu domains.
- Adds per-event `social_topics`, `primary_social_topic`, and
  `social_topic_terms` so FinClaw can map weak influence signals to macro,
  strategy, industry, fundamental, fund/wealth, trading review, risk control,
  portfolio watch, creator education, and HK/US themes.
- Every emitted event marks itself as `weak_influence_signal`,
  `investment_claim_allowed: false`, and `requires_corroboration: true`.
- Writes platform, action, weak-signal-field coverage and weak-evidence-policy
  manifests.
- Writes `manifest.influence_surface_summary`, `manifest.source_audit`, and
  `manifest.content_policy` so Lake can see creator/URL/topic/symbol/engagement
  and social-topic availability, requested inputs, missing inputs, per-file
  parse results, extension coverage, skipped file reasons, ZIP member counts,
  skipped ZIP member reasons, browser-history input/event counts, limit
  truncation, export package provenance, and preview-only content boundaries.
- Writes `manifest.social_activity_boundary_proof` so FinClaw can inspect the
  authorized social-activity input boundary, platform/action/topic coverage,
  weak-signal field coverage, source audit, content-preview policy, required
  `social-investment-influence` lens flow, and explicit no-investment-conclusion
  / no-platform-wide-scrape / no-full-creator-profile claims.
- Does not claim investment influence directly.
- Feed `lake/social-activity/events.jsonl` into `social-investment-influence`
  lens. The lens mirrors social-topic/platform/action/creator summaries and
  writes `social_influence_boundary_proof`, but resulting evidence remains weak
  influence evidence unless corroborated by stronger sources.

### 投资 Lens / 分类工具

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py list-sources
```

Lenses should consume already-collected generic lake events. They should not
directly reconnect to WeChat, email, notes, or calendar accounts.

Example lens collection:

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source wechat-investment-dialogue \
  --input <wechat-collector-json-or-jsonl> \
  --allow-chat <investment-contact-or-group> \
  --deny-sender <noisy-sender> \
  --out-dir <out-dir>
```

Default behavior:

- Generic-channel lenses only emit investment-matched evidence.
- Each emitted event includes `data.classification.confidence`,
  `data.classification.reasons`, `matched_terms`, and `matched_symbols`.
- The default relevance threshold is `--min-score 0.30`.
- Use `--include-non-matches` only for audit/backtest runs, not normal Wiki
  ingestion.
- Use `--allow-chat`, `--deny-chat`, `--allow-sender`, and `--deny-sender` to
  restrict WeChat investment-dialogue runs to user-approved contacts, groups,
  and senders. These filters narrow scope only; they do not make a normal chat
  investment evidence by themselves.
- `manifest.wechat_dialogue_boundary_proof` and `manifest.lens_surface_summary`
  report the actual dialogue boundary: chats, senders, owner/non-owner message
  counts, group/private chat coverage, source-policy filtering, and dialogue
  surfaces such as trade intention, buy/sell reasons, position sizing, risk
  emotion, consultation network, research discussion, and review reflection.
- If input is readable but not investment-related, the manifest status is
  `no_investment_evidence_matched` and Wiki coverage stays empty.
- If all candidates are excluded by source policy, the manifest status is
  `source_policy_filtered_all`.

## Frontend / Product Preconditions

Before calling a collector, FinClaw should show the user:

1. Source name and category.
2. What will be collected.
3. What will not be collected.
4. Whether secrets/passwords are never requested.
5. Where output will be stored.
6. Whether the collector is production-ready, beta, baseline, lens-only, or placeholder.

The UI should only expose one-click collection for collectors at
`production-candidate`, `deep-beta`, or `baseline` levels. Placeholder collectors
should appear as roadmap items, not runnable actions.

## Platform Rules

Each collector must report platform status separately:

- `macos`: real-device, code-level, unsupported, or unknown
- `windows`: real-device, code-level, unsupported, or unknown
- `linux`: real-device, code-level, unsupported, or unknown

GUI automation claims require real screenshot/UI/readiness validation on that
platform. Parser-only code-level simulation is not enough to claim production.

## Security Rules

- Store user evidence locally by default.
- Never store passwords, payment passwords, trading passwords, cookies, tokens,
  sessions, signatures, device fingerprints, or raw network payloads.
- Do not turn public market data into personal evidence.
- Keep raw sensitive evidence in lake/raw refs; Wiki should receive distilled
  facts and evidence indexes.

## FinClaw Readiness Gate

FinClaw should inspect `manifest.json` when available:

- `collection_readiness.status`
- `event_count`
- `classification_summary` for lens collectors
- required strong table/materialization flags for broker collectors
- gap events and missing authorization states

If a collector only emits a gap/preflight event, FinClaw should show the missing
authorization/input, not treat it as collected personal data.

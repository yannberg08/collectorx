# P0 Email Local Client E2E Validation - 2026-07-09

This validation records the offline G2 evidence for the P0 generic `email`
collector feeding the downstream `email-research` investor lens.

## Scope

- Generic collector: `email`
- Investor lens: `email-research`
- Local client formats covered by fixture:
  - Apple Mail `.emlx`
  - Maildir `cur/` and `new/`
  - Thunderbird no-extension mbox with `.msf` summary-index skip proof
- Fixture root:
  `examples/fixtures/email-local-e2e/`

## Offline Fixture

The fixture is synthetic and contains no real mailbox data, credentials,
tokens, cookies, or private email bodies.

```text
examples/fixtures/email-local-e2e/
  Library/Mail/V10/ResearchMailbox/AppleMail/101.emlx
  Maildir/cur/1720000100.M1P1Q1.fixture_2_S
  Maildir/new/1720000200.M2P2Q2.fixture
  Thunderbird/Profiles/abcd.default-release/Mail/pop.friend.example/Inbox
  Thunderbird/Profiles/abcd.default-release/Mail/pop.friend.example/Inbox.msf
```

The checked-in Maildir `cur/` fixture uses a Windows-safe `_2_S` suffix instead
of the common `:2,S` flag suffix, so the repository can be checked out on
Windows while still exercising the collector's `cur/`/`new/` Maildir boundary.

## Test Coverage Added

`skills/email-collector/tests/test_events.py` now includes
`test_local_email_client_e2e_feeds_email_research_lens_and_blocks_gap_wiki_facts`.

The test verifies:

- `email_api.py import --local-scan` emits 4 generic email events from the
  local client fixture.
- Manifest/audit counts include:
  - `apple_mail_emlx_file_count=1`
  - `maildir_message_file_count=2`
  - `thunderbird_mbox_file_count=1`
  - `local_scan_skipped_reason_counts={"thunderbird_summary_index": 1}`
- Generic email package passes `validate_collector_package --collector email`.
- The generated `lake/email/events.jsonl` is accepted as authorized input by
  `email-research`.
- Normal `email-research` package emits 3 usable events, passes
  `validate_collector_package --collector email-research --require-evidence`,
  and records `proof_level=authorized_email_research_with_research_attachment_refs`.
- A deliberately over-restrictive `email-research` run becomes a gap-only
  package with `email_research_event_count=0`,
  `can_feed_investor_wiki_evidence=false`, and no Wiki facts.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/scripts/email_collector/events.py \
  skills/email-collector/tests/test_events.py

.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py

.venv/bin/python skills/email-collector/tests/test_events.py

.venv/bin/python skills/email-collector/scripts/email_api.py import \
  --local-scan \
  --platform mac \
  --container-root examples/fixtures/email-local-e2e \
  --probe-export /tmp/collectorx-email-local-e2e-validation.1V4Xnr/probe.json \
  --out-dir /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email \
  --collected-at 2026-07-09T13:00:00+08:00

.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email \
  --collector email \
  --json

.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source email-research \
  --input /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email/lake/email/events.jsonl \
  --out-dir /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email-research \
  --collected-at 2026-07-09T13:10:00+08:00

.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email-research \
  --collector email-research \
  --require-evidence \
  --json

.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source email-research \
  --input /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email/lake/email/events.jsonl \
  --out-dir /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email-research-gap \
  --allow-email-sender-domain missing.example \
  --collected-at 2026-07-09T13:20:00+08:00

.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-email-local-e2e-validation.1V4Xnr/email-research-gap \
  --collector email-research \
  --require-evidence \
  --json
```

## Results

- Syntax checks passed.
- `skills/email-collector/tests/test_events.py` passed.
- Generic email package:
  - `event_count=4`
  - `usable_event_count=4`
  - `gap_event_count=0`
  - package validation `valid=true`
- Normal `email-research` lens package:
  - `event_count=3`
  - `usable_event_count=3`
  - `email_research_event_count=3`
  - evidence package present
  - package validation `valid=true`
- Gap-only `email-research` lens package:
  - `event_count=1`
  - `usable_event_count=0`
  - `gap_event_count=1`
  - `email_research_event_count=0`
  - `collection_readiness.can_feed_investor_wiki_evidence=false`
  - `investor_wiki_evidence.generated_from.event_count=0`
  - `investor_wiki_evidence.coverage_summary.usable_for_wiki_now=[]`
  - package validation `valid=true`

## Remaining G3 Gaps

- Run against real user-authorized Apple Mail, Thunderbird, Maildir, Outlook,
  Foxmail/QQ/163, and enterprise mail exports on macOS, Windows, and Linux.
- Verify incremental/dedup behavior across large local mailboxes and repeated
  scans.
- Backtest real broker, IR, roadshow, alert, and newsletter traffic with
  production allow/deny policies.
- Add user-facing authorization UX evidence for selecting local mailbox roots
  and explaining full-body/attachment-body exclusions.

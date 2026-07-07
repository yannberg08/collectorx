# P0 Email Local Import Validation

Date: 2026-07-08

## Scope

This pass adds a local authorized import path to the generic `email` collector so
FinClaw can collect mailbox evidence even before a user registers IMAP access.

The collector remains generic:

- It collects email evidence.
- It does not decide which emails are investment research.
- `email-research` performs the broker research, roadshow, IR, and announcement
  filtering.

## Inputs Covered

Fixture validation covers:

- EML files.
- JSON email export packages.
- CSV email export rows.
- Attachment metadata from EML and structured exports.
- Missing-input gap behavior.
- Existing IMAP event conversion and fake multi-folder IMAP collection.

The import command also supports MBOX, JSONL/NDJSON, and TSV by code path.

## Output Contract

The standard local import command writes:

- `lake/email/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

Each event uses `collectorx.event.v1`, collector `email`, kind `email`.

## Privacy Boundary

Default events include:

- Mailbox/folder.
- Sender/recipients/cc.
- Subject/date/message ID.
- `body_preview`.
- Attachment refs: filename, content type, and size when available.

Default events do not include:

- Full body.
- Attachment bodies.
- Mailbox/app passwords.
- OAuth tokens or cookies.

Full body requires explicit `--event-include-body` authorization.

This pass also tightens new IMAP registration so `register` no longer writes a
password or app password into the local state file. New enabled accounts must
use `--password-env`; old state files remain readable only for compatibility.

## Validation Result

Status: `completed-baseline`

Gate reached: G1/G2 local authorized export baseline.

Not claimed:

- Real mailbox IMAP validation.
- Complete mailbox boundary.
- Investment-research classification by the generic collector.

Next gates:

- Register and validate a real mailbox with user authorization.
- Run the `email-research` lens against real imported and IMAP-collected
  events.
- Backtest broker/IR sender matching, attachment refs, and no-full-body Wiki
  leakage.

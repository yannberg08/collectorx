# P1 Collaboration Exports Validation - 2026-07-08

This validation records the first productization pass for DingTalk and WeCom
generic collaboration exports.

## Collaboration Exports Collector

Collector path:

- Generic sources: `dingtalk`, `wecom`
- Skill: `skills/collaboration-exports`

Result:

- Added a runnable shared skill for DingTalk and WeCom authorized local exports.
- CLI contract:
  - `collaboration_exports.py collect --platform dingtalk`
  - `collaboration_exports.py collect --platform wecom`
- Replaced YAML-only placeholder status for `dingtalk` and `wecom`.
- Supported inputs:
  - JSON
  - JSONL/NDJSON
  - CSV/TSV
  - HTML
  - Markdown/TXT
- Captured collaboration surfaces:
  - messages
  - chats
  - contacts
  - file refs
  - meeting refs
  - sender/receiver
  - departments
  - participants
  - meeting links
  - file names
  - tags
  - content previews
- Generic events route to internal collaboration targets and do not claim
  investment meaning directly.

Fixture validation:

- DingTalk multi-section JSON emits message, contact, and file events.
- DingTalk HTML meeting export emits a meeting event.
- WeCom CSV emits message and meeting events.
- Gap events are emitted when no authorized input is provided.
- Credential-like test data is removed from emitted raw snapshots.

Current gate:

- Authorized local export parsing: G1/G2 baseline.
- Real DingTalk account/export validation: not done.
- Real WeCom account/export validation: not done.
- Investment dialogue / research meeting filtering remains downstream lens work.

Remaining before production:

- Validate real DingTalk export/account surfaces for messages, files, meetings,
  and contacts.
- Validate real WeCom export/account surfaces for messages, files, meetings,
  and contacts.
- Add source allowlists for enterprise/workspace boundaries.
- Add identity normalization across mobile, email, open user IDs, and local
  display names.
- Add a collaboration-dialogue investor lens if WeChat investment dialogue rules
  are not enough for enterprise chat semantics.

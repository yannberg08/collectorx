# P1 Meeting Platform Export Validation - 2026-07-08

This validation records the second productization pass for `meeting-artifacts`.

## Platform Export Import

Collector path:

- Generic source: `meeting-artifacts`
- Skill: `skills/meeting-artifacts`

Result:

- Upgraded `meeting-artifacts` to `0.2.0`.
- Added platform-export parsing for:
  - HTML/HTM meeting pages
  - CSV/TSV meeting tables
  - JSON/JSONL/NDJSON meeting packages
  - Markdown/TXT minutes
  - VTT/SRT transcripts
- Normalizes platform evidence into stable values:
  - `feishu`
  - `dingtalk`
  - `wecom`
  - `tencent-meeting`
  - `local-file`
- Captures meeting title, artifact type, platform, start/end time, organizer,
  participants, meeting URL, text preview, attachment refs, and sanitized raw
  fields when present.
- Filters credential-like raw keys before lake output, including password,
  cookie, token, session, secret, authorization, and credential.

Fixture validation:

- DingTalk-style JSON export is converted into `collectorx.event.v1`.
- WeCom-style CSV export is converted into `collectorx.event.v1`.
- Tencent Meeting-style HTML export is converted into `collectorx.event.v1`.
- Platform counts are written into `manifest.json`.
- Credential-like test data does not leak into emitted events.

Current gate:

- Authorized local/platform-export files: G1/G2 baseline.
- Meeting-minutes lens routing: prior G2 baseline.
- Real Feishu/DingTalk/WeCom/Tencent Meeting account API validation: not done.

Remaining before production:

- Validate real authorized exports from each meeting platform.
- Build or port account adapters where the platform provides user-authorized
  APIs or export surfaces.
- Normalize participant identities across email, phone, open user IDs, and
  local display names without storing credentials.
- Expand false-positive review on non-investment company meetings before lens
  evidence is promoted into investor Wiki conclusions.

---
name: doubao-chat-export
description: "Export chat history from the Doubao (豆包, doubao.com) desktop app. Lists all conversations and pulls full multi-turn message text (user and bot) for any or every conversation, output as normalized JSON. A single self-contained binary (no runtime dependencies) decrypts the locally logged-in session cookie and calls Doubao's own backend API, with no browser and no a_bogus/msToken signature. This skill should be used when the user wants to export, back up, archive, collect, or read their Doubao chat history or conversations, or pipe Doubao chats into another system. Triggers: 导出豆包, 豆包聊天记录, 备份豆包对话, 采集豆包, doubao chat export, 豆包对话导出."
version: 0.1.0
---

# Doubao Chat Export

Export the user's own Doubao (豆包) desktop chat history via Doubao's backend
API, using only the already-logged-in local session. Ships as a **single
self-contained binary** per OS — no Node, no Python, no Go toolchain, no browser,
and no request signing. The only credential is the cookie from the installed
Doubao desktop app.

## When to use

Use when the user wants to export / back up / archive / collect / read their
Doubao conversations, or feed Doubao chats into another tool or knowledge base.

## Dependencies — none to install

The tool is a prebuilt, statically-linked binary (the SQLite reader is compiled
in). It needs **no** Node, Python, Go, or `sqlite3`. Requirement is only:
- The **Doubao desktop app** installed and **logged in** (the data source).

## How to use

Run the binary for the current platform from `scripts/bin/`. **Detect the
platform first** (e.g. `uname -sm`) and pick the matching file:

| OS / arch | binary |
|---|---|
| macOS Apple Silicon (`Darwin arm64`) | `scripts/bin/doubao-export-darwin-arm64` |
| macOS Intel (`Darwin x86_64`) | `scripts/bin/doubao-export-darwin-amd64` |
| Windows x64 | `scripts/bin/doubao-export-windows-amd64.exe` |
| Linux x64 | `scripts/bin/doubao-export-linux-amd64` |

The binary handles its own OS-specific cookie decryption internally. Subcommands:

```bash
# List all conversations (id, name, message count) as JSON
<binary> list

# Pull one conversation's full message history as JSON
<binary> pull <conversation_id>

# Export everything: list + every conversation -> JSON files in <outDir>
<binary> export ./doubao-export

# Search message text for a keyword across all conversations (or one) -> JSON
<binary> search <关键词> [conversation_id]
```

`search` returns matches as `{conversation_id, conversation_name, role, snippet,
text, create_time, index_in_conv}`. Since conversation content lives server-side,
search pulls each conversation's history and matches locally. To stay fast it
**caches** each conversation under `UserCacheDir/doubao-export/<id>.json` and on
later runs only pulls **new** messages incrementally — so the first search of a
huge conversation (tens of thousands of messages) takes ~30s, but repeat searches
are near-instant (~0.5s). Pass a `conversation_id` to scope the search. Prefer
`search` over manually running `export` then grepping.

Progress/diagnostics go to stderr; JSON goes to stdout. Typical flow: run `list`
to show the user their conversations, then `pull` the ones they want (or
`export` for a full backup).

**On macOS, the first run triggers a Keychain prompt** ("… wants to access
Doubao Safe Storage"). Tell the user to click **Always Allow** — it is needed to
decrypt the cookie locally and is read-only.

### Output shape

`list` → array of `{conversation_id, name, bot_id, conversation_type, message_index}`.

`pull` → messages sorted oldest→newest, deduped by `message_id`:
`{message_id, conversation_id, role, text, content_type, index_in_conv, create_time}`,
`role` ∈ `user | assistant | system`.

`export` → `conversations.json` plus one `<conversation_id>.json` per
conversation (each `{...meta, messages:[...]}`).

## Important notes & limitations

- **Self-discovering.** The binary locates the Doubao profile, decrypts cookies,
  and harvests device query params (`device_id`, `web_id`, `fp`, …) from the
  user's own local netlog — nothing is hardcoded to one machine. A fresh install
  with an empty netlog falls back to a minimal param set; opening Doubao once fixes it.
- **Cookie expiry.** The login cookie (`sid_guard`) lasts ~1 month. If requests
  start failing with an auth/empty error, have the user reopen/relogin Doubao.
- **Platform status.** macOS and **Windows are both verified on real hardware**
  (DPAPI + AES-256-GCM cookie decryption, list + pull of real conversation text).
  Linux is best-effort / unverified.
- **Windows + Doubao running (file lock).** Newer Doubao Windows clients lock the
  cookie DB so strictly that a normal read fails while Doubao is open. The binary
  handles this automatically: it first tries a shared open, and on a sharing
  violation falls back to a **VSS snapshot copy via the built-in `esentutl /vss`**
  — which **requires running elevated (as admin)**. So: with Doubao closed it
  works without admin; with Doubao open it needs an elevated session. If the VSS
  fallback fails (not elevated), the error tells the user to close Doubao and retry.
- **Message types.** Plain-text conversations export fully. Image / card / tool
  messages (`content_type` ≠ 9999) fall back to whatever text/brief is present.
- **Rate limiting.** `export` paces requests (~400ms) and pages serially.
- **Privacy / own data.** The cookie is a live login; the binary keeps it in
  memory only. Intended for a user exporting their own account.
- **Unsigned binaries.** Built locally, not code-signed. If macOS Gatekeeper
  quarantines a copied binary, `xattr -d com.apple.quarantine <binary>` clears it.

## How it works & rebuilding

- Reverse-engineering details (API contract, the `712012002` / `712010702`
  gotchas, frontier IM envelope, enums, paging): `references/reverse-engineering.md`.
- Cookie decryption per OS + device-param harvesting: `references/cookies-and-params.md`.
- Full Go source is in `scripts/src/` with `scripts/src/BUILD.md` for the
  cross-compile commands (`CGO_ENABLED=0`). Read these before modifying behavior
  or debugging a new gateway error code.

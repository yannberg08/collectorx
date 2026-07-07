# Doubao chat export — reverse-engineering notes

How the Doubao (doubao.com) desktop app stores and serves chat history, and the
exact API contract used by `scripts/doubao_export.mjs`. Read this when modifying
the script or debugging a new gateway error code.

## 1. What the Doubao desktop app actually is

The macOS app (`/Applications/Doubao.app`, bundle `com.bot.pc.doubao.browser`) is
a **Chromium wrapper** of the web app at `https://www.doubao.com`. Its data dir is
a standard Chromium profile:

```
~/Library/Application Support/Doubao/
├── Default/Cookies         # Chromium SQLite, encrypted cookie values (v10)
├── Default/History         # SQLite; conversation URLs /chat/<id> + titles
├── Default/IndexedDB/…     # only caches previews/index — NOT full message text
└── sdk_storage/log/saman_*.log  # netlog with real API request URLs (param source)
```

Key consequence: **there is no clean local SQLite chat table** (unlike WeChat).
Conversation text lives server-side; the client fetches it. So extraction is an
*online API* job, not a local-DB read.

## 2. Authentication: cookie only

The backend authenticates by **cookie alone**. The anti-bot signatures
`a_bogus` / `msToken` that the web app normally appends are **NOT required** for
these read endpoints — sending just the logged-in cookies returns real data.
(Verified: `thread/list` returns `code:0` and `im/chain/single` returns
`status_code:0` with cookies and no signature.)

Required cookies come from the Chromium profile (`sessionid`, `sid_guard`,
`ttwid`, `s_v_web_id`, `passport_csrf_token`, …). See
`cookies-and-params.md` for decryption.

## 3. Endpoints

Host: `https://www.doubao.com`. All requests are `POST` with a JSON body and a
shared query string of device params (see `cookies-and-params.md` §params).

### 3a. Conversation list — `/samantha/thread/list` (plain JSON)

```
POST /samantha/thread/list?<params>
body: {"count":30,"cursor":""}
→ {"code":0,"data":{"thread_list":[{thread_id, conversation:{conversation_id,
     name, bot_id, conversation_type, message_index, ...}}, ...], has_more, next_cursor}}
```

Page with `cursor`/`next_cursor` until `has_more` is false. The list can repeat
items across pages — de-dup by `conversation_id`.

### 3b. Messages — `/im/chain/single` (frontier IM, JSON↔protobuf via AGW)

This is the crux. `/im/chain/single` is a ByteDance **frontier IM** endpoint that
natively speaks protobuf. **You do NOT need to encode protobuf yourself** — the
**AGW gateway converts JSON↔protobuf server-side** when you send the right headers.

Required headers (these two are what trigger the conversion):
```
Content-Type: application/json; encoding=utf-8     # NOT plain application/json
Agw-Js-Conv: str
```
plus `Cookie`, a Doubao Electron `User-Agent`, `Origin`, `Referer`.

Request envelope (frontier "uplink"):
```json
{
  "cmd": 3100,
  "sequence_id": "<uuid>",
  "channel": 2,
  "version": "1",
  "uplink_body": {
    "pull_singe_chain_uplink_body": {
      "conversation_id": "<id>",
      "anchor_index": 0,
      "conversation_type": 3,
      "direction": 3,
      "limit": 50
    }
  }
}
```
- The field name is literally `pull_singe_chain_uplink_body` — **"singe", not "single"** (matches the wire field).
- **Do NOT include `filter` or `ext`.** The web bundle builds `filter:{index_list,bot_id}`, but sending it triggers `712010702 系统内部异常`. Omit them entirely; normal paging does not need them.

Response:
```json
{ "status_code": 0,
  "downlink_body": { "pull_singe_chain_downlink_body": {
      "messages": [ {message_id, user_type, content_type, content,
                     content_block:[{content:{text_block:{text}}}],
                     brief, tts_content, index_in_conv, create_time, ...}, ... ],
      "has_more": true } } }
```

### Enums
- `cmd` PULL_SINGLE_CHAIN = `3100`
- `ConversationType.ONE_TO_BOT_CHAT = 3` (use 3 in the pull regardless of the
  list's `conversation_type` value — it works for all chat conversations)
- `MessageDirection`: `OLDER=1`, `NEWER=2`, `FROM_LATEST=3`
- `user_type`: `1=human(user)`, `2=aibot(assistant)`, `3=system`

### Extracting message text
Priority: concatenate `content_block[].content.text_block.text` → else `content`
→ else `brief` → else `tts_content`. Rich-text bodies use `content_type=9999`
with the text in `content_block`.

## 4. Paging (full backfill + incremental)

- **First page:** `direction=3 (FROM_LATEST)`, `anchor_index=0`.
- **Older history:** `direction=1 (OLDER)`, `anchor_index = min(index_in_conv)` of
  the page just received. Repeat while `has_more`.
- **Incremental (new since last run):** `direction=2 (NEWER)`,
  `anchor_index = last max index_in_conv` stored from the previous export.
- `index_in_conv` is an int64-as-string and is **sparse** (gaps are normal);
  use it as the anchor and for ordering. De-dup by `message_id`.

## 5. Gateway error codes seen

- `712012002 不支持编码类型` → wrong `Content-Type`. Must be
  `application/json; encoding=utf-8` (with `Agw-Js-Conv: str`).
- `712010702 系统内部异常` → uplink included `filter`/`ext`. Remove them.
- non-zero `code` on `thread/list` or auth errors → cookie likely expired; relogin.

## 6. Where this was found in the app bundle

The desktop bundle is unpacked under
`~/Library/Application Support/Doubao/gecko_cache/<hash>/biz/0_unzip/`:
- `static/js/async/launcher2_page.*.js` — defines the `/im/chain/single` call,
  `getUnlinkMessage` (adds `sequence_id/channel:2/version:"1"`), and the enums.
- `static/js/launcher2.*.js` — `imGatewayClient` sets `Content-Type:
  application/json; encoding=utf-8`; `getCommonHeaders` injects `Agw-Js-Conv: str`.

If Doubao changes the protocol, re-derive from these chunks (grep for
`chain/single`, `IMCMD`, `pull_singe_chain`, `imGatewayClient`).

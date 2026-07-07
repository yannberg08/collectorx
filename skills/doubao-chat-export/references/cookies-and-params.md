# Cookie decryption & device-param harvesting

How `scripts/doubao_export.mjs` obtains the two things every request needs:
the **cookie jar** and the **device query-param string**. Both are read from the
user's own local Doubao install — nothing is hardcoded.

## Dependencies (all preinstalled on macOS — nothing to `npm install`)

- **Node.js** — uses only built-ins: `crypto`, `fetch` (Node 18+), `fs`,
  `child_process`. No third-party packages.
- **`sqlite3`** CLI — ships with macOS; used to read the Chromium cookie DB.
- **`security`** CLI — ships with macOS; reads the Keychain key.

## Cookie decryption (macOS / Chromium "v10")

Doubao stores cookies in a Chromium profile, AES-encrypted:
`~/Library/Application Support/Doubao/Default/Cookies` (SQLite, `cookies` table,
`encrypted_value` blobs prefixed `v10`).

Steps (implemented in `cookieJar()` / `decryptCookie()`):
1. **Copy** the Cookies DB to a temp file first — the live DB is locked while
   Doubao runs.
2. Dump rows with `sqlite3`: `select name, hex(encrypted_value) from cookies
   where host_key like '%doubao%'`.
3. **Get the AES key** from the Keychain:
   `security find-generic-password -s "Doubao Safe Storage" -w`
   → derive `key = PBKDF2-HMAC-SHA1(password, salt="saltysalt", iters=1003, len=16)`.
   (First call pops a Keychain GUI prompt → user clicks **Always Allow**.)
4. **Decrypt** each value: strip the 3-byte `v10`/`v11` prefix, AES-128-CBC with
   `IV = 16 × 0x20` (spaces), no auto-padding, then strip PKCS7 padding.
5. **Newer macOS Chromium** prepends a 32-byte SHA256 domain hash to the
   plaintext — if the first 32 bytes contain control chars, drop them.

The login is valid if `sessionid` / `sid_guard` decrypt to non-empty values.

### Other platforms (not implemented)
- **Windows:** cookies under `%LOCALAPPDATA%\Doubao\User Data\...`; key is
  DPAPI-protected inside `Local State` (`os_crypt.encrypted_key`, `CryptUnprotectData`),
  values are AES-256-GCM (`v10` prefix, 12-byte nonce, 16-byte tag).
- **Linux:** AES-128-CBC with key from gnome-keyring/kwallet (or the hardcoded
  `peanuts` fallback).
Porting means swapping only the key-retrieval + cipher in `decryptCookie`.

## Device query params (§params)

Every API call carries a query string of device/build params
(`device_id`, `web_id`, `fp`, `aid=582478`, `version_code`, `pc_version`,
`chromium_version`, …). Only `aid` is a true constant; `device_id`/`web_id`/`fp`
are **per-install** and must come from the user's machine — hardcoding them
breaks distribution.

`queryParams()` harvests a known-good string by scanning the user's own netlog
(`~/Library/Application Support/Doubao/sdk_storage/log/saman_*.log`) for any real
`www.doubao.com/(samantha|im)/...?<query>` request and reusing its query string
(minus the per-tab `web_tab_id`). This guarantees valid params for that machine.

Fallback (fresh install with empty netlog): a minimal constant set with `aid` but
no `device_id`. This may be rejected; opening the Doubao app once populates the
netlog and fixes it.

> None of these params are an auth credential — auth is the cookie alone. They are
> build/telemetry fields the gateway expects to be present and well-formed.

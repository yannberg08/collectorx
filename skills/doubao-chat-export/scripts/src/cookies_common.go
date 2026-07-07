package main

import (
	"database/sql"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"

	_ "modernc.org/sqlite" // pure-Go SQLite driver (no CGO, no sqlite3 CLI)
)

// readCookieRows opens the Chromium cookie SQLite DB and returns the raw
// (name, encrypted_value) pairs for doubao hosts. The live DB is locked while
// Doubao runs, so we copy it to a temp file first.
//
// The returned values are the raw encrypted_value blobs; per-platform
// decryptValue turns each into plaintext.
func readCookieRows(cookiesDB string) (map[string][]byte, error) {
	if _, err := os.Stat(cookiesDB); err != nil {
		return nil, fmt.Errorf("找不到 Cookies 数据库: %s (%v)", cookiesDB, err)
	}
	tmp, err := copyToTemp(cookiesDB)
	if err != nil {
		return nil, err
	}
	defer os.Remove(tmp)

	// immutable=1 lets us read even a WAL-mode DB copy without sidecar files.
	db, err := sql.Open("sqlite", "file:"+tmp+"?mode=ro&immutable=1")
	if err != nil {
		return nil, fmt.Errorf("打开 cookie DB: %w", err)
	}
	defer db.Close()

	rows, err := db.Query(`SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%doubao%'`)
	if err != nil {
		return nil, fmt.Errorf("查询 cookies: %w", err)
	}
	defer rows.Close()

	out := map[string][]byte{}
	for rows.Next() {
		var name string
		var enc []byte
		if err := rows.Scan(&name, &enc); err != nil {
			return nil, err
		}
		out[name] = enc
	}
	return out, rows.Err()
}

func copyToTemp(src string) (string, error) {
	// openShared is platform-specific: on Windows it opens with full share flags
	// so it can read the DB even while Doubao holds it locked; elsewhere os.Open.
	in, err := openShared(src)
	if err != nil {
		return "", fmt.Errorf("打开 Cookies 失败: %w", err)
	}
	defer in.Close()
	f, err := os.CreateTemp("", "dbk_*.sqlite")
	if err != nil {
		return "", err
	}
	defer f.Close()
	if _, err := io.Copy(f, in); err != nil {
		os.Remove(f.Name())
		return "", err
	}
	return f.Name(), nil
}

// hasControlChar reports whether b contains an ASCII control char in [0x00,0x08].
// Used to detect the 32-byte SHA256 domain-hash prefix some Chromium builds add.
func hasControlChar(b []byte) bool {
	for _, c := range b {
		if c <= 0x08 {
			return true
		}
	}
	return false
}

// stripPKCS7 removes PKCS7 padding (used by CBC-mode platforms).
func stripPKCS7(b []byte) []byte {
	if len(b) == 0 {
		return b
	}
	pad := int(b[len(b)-1])
	if pad > 0 && pad <= 16 && pad <= len(b) {
		return b[:len(b)-pad]
	}
	return b
}

// ---------------------------------------------------------------------------
// device query-param harvesting (cross-platform; reads the local netlog)
// ---------------------------------------------------------------------------

var apiQueryRe = regexp.MustCompile(`www\.doubao\.com/(?:samantha|im)/[^?"\s]+\?([^"\s\\]{40,})`)
var webTabIDRe = regexp.MustCompile(`&?web_tab_id=[^&]*`)

// queryParams harvests a known-good device query string from the user's own
// netlog so the tool is not pinned to one machine. Falls back to a minimal set.
func queryParams(dir string) string {
	logDir := filepath.Join(dir, "sdk_storage", "log")
	best := ""
	entries, err := os.ReadDir(logDir)
	if err == nil {
		for _, e := range entries {
			if e.IsDir() || len(e.Name()) < 6 || e.Name()[:6] != "saman_" {
				continue
			}
			data, err := os.ReadFile(filepath.Join(logDir, e.Name()))
			if err != nil {
				continue
			}
			for _, m := range apiQueryRe.FindAllSubmatch(data, -1) {
				if len(m[1]) > len(best) {
					best = string(m[1])
				}
			}
		}
	}
	if best != "" {
		return webTabIDRe.ReplaceAllString(best, "")
	}
	logf("netlog 无可用 query 参数, 使用最小回退集 (可能被网关拒绝; 打开一次豆包桌面版可修复)")
	return "version_code=20800&language=zh&device_platform=web&aid=582478&real_aid=582478" +
		"&pkg_type=release_version&region=CN&sys_region=CN&samantha_web=1&use-olympus-account=1" +
		"&runtime=web&client_platform=pc_client"
}

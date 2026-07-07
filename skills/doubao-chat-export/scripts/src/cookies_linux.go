//go:build linux

package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha1"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"golang.org/x/crypto/pbkdf2"
)

// NOTE: best-effort, NOT verified on a real Linux machine. Linux Chromium uses
// AES-128-CBC; the key comes from the desktop secret-service (gnome-keyring /
// kwallet) and falls back to the hardcoded "peanuts" password. TODO: a proper
// libsecret/D-Bus integration; here we try the `secret-tool` CLI then fall back.

func dataDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Join(home, ".config", "Doubao"),
		filepath.Join(home, ".config", "doubao"),
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c, nil
		}
	}
	return "", fmt.Errorf("找不到豆包数据目录(尝试过: %v)\n请确认已安装并登录豆包桌面版。", candidates)
}

func cookieJar(dir string) (map[string]string, error) {
	dbCandidates := []string{
		filepath.Join(dir, "Default", "Network", "Cookies"),
		filepath.Join(dir, "Default", "Cookies"),
		filepath.Join(dir, "Cookies"),
	}
	var cookiesDB string
	for _, c := range dbCandidates {
		if _, err := os.Stat(c); err == nil {
			cookiesDB = c
			break
		}
	}
	if cookiesDB == "" {
		return nil, fmt.Errorf("找不到 Cookies 数据库 (尝试过: %v)", dbCandidates)
	}
	rows, err := readCookieRows(cookiesDB)
	if err != nil {
		return nil, err
	}

	keyV10 := deriveKey(secretServicePassword())
	keyPeanuts := deriveKey([]byte("peanuts"))

	jar := map[string]string{}
	for name, enc := range rows {
		v, err := decryptValue(enc, keyV10, keyPeanuts)
		if err != nil {
			logf("  跳过 cookie %s: %v", name, err)
			continue
		}
		jar[name] = v
	}
	return jar, nil
}

func deriveKey(pw []byte) []byte {
	return pbkdf2.Key(pw, []byte("saltysalt"), 1, 16, sha1.New)
}

// secretServicePassword tries `secret-tool` to fetch the "Doubao Safe Storage"
// password from the desktop keyring; returns "peanuts" on failure.
func secretServicePassword() []byte {
	out, err := exec.Command("secret-tool", "lookup",
		"application", "Doubao").Output()
	if err == nil {
		if s := strings.TrimRight(string(out), "\r\n"); s != "" {
			return []byte(s)
		}
	}
	return []byte("peanuts")
}

// decryptValue: Linux Chromium AES-128-CBC, IV = 16 spaces, PKCS7. Tries the
// secret-service-derived key first, then the peanuts fallback.
func decryptValue(enc []byte, keyV10, keyPeanuts []byte) (string, error) {
	if len(enc) < 3 {
		return string(enc), nil
	}
	tag := string(enc[:3])
	if tag != "v10" && tag != "v11" {
		return string(enc), nil // not encrypted
	}
	ct := enc[3:]
	if len(ct) == 0 || len(ct)%aes.BlockSize != 0 {
		return "", fmt.Errorf("密文长度非法 (%d)", len(ct))
	}
	for _, key := range [][]byte{keyV10, keyPeanuts} {
		if s, ok := tryCBC(ct, key); ok {
			return s, nil
		}
	}
	return "", fmt.Errorf("两个候选密钥都解密失败")
}

func tryCBC(ct, key []byte) (string, bool) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", false
	}
	iv := make([]byte, 16)
	for i := range iv {
		iv[i] = 0x20
	}
	pt := make([]byte, len(ct))
	cipher.NewCBCDecrypter(block, iv).CryptBlocks(pt, ct)
	pt = stripPKCS7(pt)
	if len(pt) >= 32 && hasControlChar(pt[:32]) {
		pt = pt[32:]
	}
	// crude validity check: printable-ish ASCII/UTF-8 with no early NULs.
	if len(pt) > 0 && hasControlChar(pt[:min(8, len(pt))]) {
		return "", false
	}
	return string(pt), true
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

//go:build darwin

package main

import (
	"crypto/aes"
	"crypto/cipher"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"golang.org/x/crypto/pbkdf2"
	"crypto/sha1"
)

// dataDir locates the Doubao Chromium profile root on macOS.
func dataDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	d := filepath.Join(home, "Library", "Application Support", "Doubao")
	if _, err := os.Stat(d); err != nil {
		return "", fmt.Errorf("找不到豆包数据目录: %s\n请确认已安装并登录豆包桌面版(Doubao.app)。", d)
	}
	return d, nil
}

// cookieJar reads + decrypts all doubao cookies (macOS v10/v11, AES-128-CBC).
func cookieJar(dir string) (map[string]string, error) {
	cookiesDB := filepath.Join(dir, "Default", "Cookies")
	rows, err := readCookieRows(cookiesDB)
	if err != nil {
		return nil, err
	}
	key, err := safeStorageKey()
	if err != nil {
		return nil, err
	}
	jar := map[string]string{}
	for name, enc := range rows {
		v, err := decryptValue(enc, key)
		if err != nil {
			logf("  跳过 cookie %s: %v", name, err)
			continue
		}
		jar[name] = v
	}
	return jar, nil
}

// safeStorageKey reads the AES key from the macOS Keychain and derives it.
// First call may pop a Keychain GUI prompt -> user clicks "Always Allow".
func safeStorageKey() ([]byte, error) {
	out, err := exec.Command("security", "find-generic-password",
		"-s", "Doubao Safe Storage", "-w").Output()
	if err != nil {
		return nil, fmt.Errorf("从钥匙串读取 'Doubao Safe Storage' 失败: %w (请在弹窗里点\"始终允许\")", err)
	}
	pw := out
	// trim trailing newline
	for len(pw) > 0 && (pw[len(pw)-1] == '\n' || pw[len(pw)-1] == '\r') {
		pw = pw[:len(pw)-1]
	}
	return pbkdf2.Key(pw, []byte("saltysalt"), 1003, 16, sha1.New), nil
}

// decryptValue decrypts a single macOS Chromium cookie value.
// Format: 3-byte "v10"/"v11" prefix + AES-128-CBC(IV = 16 x 0x20), PKCS7.
// Newer builds prepend a 32-byte SHA256 domain hash to the plaintext.
func decryptValue(enc []byte, key []byte) (string, error) {
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
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
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
	return string(pt), nil
}

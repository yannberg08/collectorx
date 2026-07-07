//go:build windows

package main

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
)

// NOTE: The Windows implementation was written by code inspection (Chromium
// DPAPI + AES-256-GCM "v10" cookie format) and has NOT been verified on a real
// Windows machine. See BUILD.md.

// openShared opens a file with FILE_SHARE_READ|WRITE|DELETE so it can be read
// even while Doubao holds the Cookies DB locked (Chromium opens it deny-share by
// default, which makes a plain os.Open fail with a sharing violation).
func openShared(path string) (*os.File, error) {
	p, err := windows.UTF16PtrFromString(path)
	if err != nil {
		return nil, err
	}
	h, err := windows.CreateFile(p, windows.GENERIC_READ,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE|windows.FILE_SHARE_DELETE,
		nil, windows.OPEN_EXISTING, windows.FILE_ATTRIBUTE_NORMAL, 0)
	if err == nil {
		return os.NewFile(uintptr(h), path), nil
	}
	// Newer Doubao clients lock the cookie DB so strictly that even full share
	// flags get a sharing violation. Fall back to a VSS snapshot copy via the
	// built-in esentutl (needs admin / an elevated session), which reads the
	// locked file from a point-in-time shadow.
	vss := filepath.Join(os.TempDir(), "dbk_vss.sqlite")
	os.Remove(vss)
	if out, e := exec.Command("esentutl", "/y", path, "/d", vss, "/vss").CombinedOutput(); e != nil {
		return nil, fmt.Errorf("豆包正在运行且锁定了数据,VSS 拷贝失败(需管理员权限运行): %v: %s", e, out)
	}
	return os.Open(vss)
}

// dataDir locates the Doubao User Data root on Windows. Tries the common
// candidates in order.
func dataDir() (string, error) {
	var candidates []string
	if la := os.Getenv("LOCALAPPDATA"); la != "" {
		candidates = append(candidates,
			filepath.Join(la, "Doubao", "User Data"),
			filepath.Join(la, "Doubao"),
		)
	}
	if ad := os.Getenv("APPDATA"); ad != "" {
		candidates = append(candidates, filepath.Join(ad, "Doubao"))
	}
	for _, c := range candidates {
		// A valid profile root has a "Local State" file next to "Default".
		if _, err := os.Stat(filepath.Join(c, "Local State")); err == nil {
			return c, nil
		}
		if _, err := os.Stat(filepath.Join(c, "Default")); err == nil {
			return c, nil
		}
	}
	return "", fmt.Errorf("找不到豆包数据目录(尝试过: %v)\n请确认已安装并登录豆包桌面版。", candidates)
}

// cookieJar reads + decrypts all doubao cookies on Windows (AES-256-GCM v10).
func cookieJar(dir string) (map[string]string, error) {
	// Cookies DB location: prefer the newer Network subdir.
	dbCandidates := []string{
		filepath.Join(dir, "Default", "Network", "Cookies"),
		filepath.Join(dir, "Default", "Cookies"),
		filepath.Join(dir, "Network", "Cookies"),
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
	key, err := masterKey(dir)
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

// masterKey reads os_crypt.encrypted_key from Local State, base64-decodes it,
// strips the 5-byte "DPAPI" prefix, and unprotects it via DPAPI to a 32-byte key.
func masterKey(dir string) ([]byte, error) {
	lsPath := filepath.Join(dir, "Local State")
	data, err := os.ReadFile(lsPath)
	if err != nil {
		return nil, fmt.Errorf("读取 Local State 失败: %w", err)
	}
	var ls struct {
		OSCrypt struct {
			EncryptedKey string `json:"encrypted_key"`
		} `json:"os_crypt"`
	}
	if err := json.Unmarshal(data, &ls); err != nil {
		return nil, fmt.Errorf("解析 Local State 失败: %w", err)
	}
	if ls.OSCrypt.EncryptedKey == "" {
		return nil, fmt.Errorf("Local State 中没有 os_crypt.encrypted_key")
	}
	raw, err := base64.StdEncoding.DecodeString(ls.OSCrypt.EncryptedKey)
	if err != nil {
		return nil, fmt.Errorf("base64 解码 encrypted_key 失败: %w", err)
	}
	if len(raw) < 5 || string(raw[:5]) != "DPAPI" {
		return nil, fmt.Errorf("encrypted_key 缺少 DPAPI 前缀")
	}
	return dpapiUnprotect(raw[5:])
}

// dpapiUnprotect wraps CryptUnprotectData (CurrentUser scope).
func dpapiUnprotect(in []byte) ([]byte, error) {
	var inBlob windows.DataBlob
	inBlob.Size = uint32(len(in))
	if len(in) > 0 {
		inBlob.Data = &in[0]
	}
	var outBlob windows.DataBlob
	if err := windows.CryptUnprotectData(&inBlob, nil, nil, 0, nil, 0, &outBlob); err != nil {
		return nil, fmt.Errorf("CryptUnprotectData 失败: %w", err)
	}
	defer windows.LocalFree(windows.Handle(unsafe.Pointer(outBlob.Data)))
	out := make([]byte, outBlob.Size)
	copy(out, unsafe.Slice(outBlob.Data, outBlob.Size))
	return out, nil
}

// decryptValue decrypts a single Windows Chromium cookie value.
// Format: 3-byte "v10" prefix + 12-byte nonce + ciphertext + 16-byte GCM tag
// (AES-256-GCM with the DPAPI-unprotected master key).
// Older values may be raw DPAPI blobs without the v10 prefix.
func decryptValue(enc []byte, key []byte) (string, error) {
	if len(enc) >= 3 && (string(enc[:3]) == "v10" || string(enc[:3]) == "v11") {
		body := enc[3:]
		if len(body) < 12+16 {
			return "", fmt.Errorf("密文太短 (%d)", len(body))
		}
		nonce := body[:12]
		ct := body[12:]
		block, err := aes.NewCipher(key)
		if err != nil {
			return "", err
		}
		gcm, err := cipher.NewGCM(block)
		if err != nil {
			return "", err
		}
		pt, err := gcm.Open(nil, nonce, ct, nil)
		if err != nil {
			return "", fmt.Errorf("GCM 解密失败: %w", err)
		}
		// Some Chromium builds prepend a 32-byte domain-hash prefix.
		if len(pt) >= 32 && hasControlChar(pt[:32]) {
			pt = pt[32:]
		}
		return string(pt), nil
	}
	// Fallback: legacy DPAPI-protected value (pre-v10).
	pt, err := dpapiUnprotect(enc)
	if err != nil {
		return "", err
	}
	return string(pt), nil
}

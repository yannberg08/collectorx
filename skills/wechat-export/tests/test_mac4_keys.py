#!/usr/bin/env python3
"""Mac WeChat 4.x per-DB key 提取 + 查询重构的回归测试（0.9.0）。

背景：微信升级到 4.x 后，Mac 与 Windows 一样是「每个库一把独立 enc_key」，
且新版微信内存里扫不到明文 key —— 改用 lldb hook CCKeyDerivationPBKDF 提取
（wechat_extract_mac.py），提取出的 key 用「第 1 页 HMAC-SHA512 校验」对回各库。
查询侧把「读库」抽到共享基类 V4QueryBase，Windows/Mac 4.x 都继承它。

本测试是合成 fixture，不依赖真实微信 / lldb / root，可在任何平台跑：
  - 用 SQLCipher4 的 HMAC 参数亲手造一个「能被某 key 校验通过」的第 1 页，
    验证 verify_key_page1 + 提取器的 key→库 匹配逻辑；
  - 验证重构后的类层次、别名、per-DB keys 文件解析。
"""
import hashlib
import hmac as hmac_mod
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import wechat_extract_mac as ext  # noqa: E402
import wechat_query as wq          # noqa: E402


def _make_page1(enc_key: bytes, salt: bytes) -> bytes:
    """造一个能被 enc_key 通过 SQLCipher4 第 1 页 HMAC 校验的 4096 字节头页。

    复刻 verify_key_page1 的校验式：mac_key = pbkdf2_sha512(enc_key, salt^0x3a, 2)；
    stored_hmac = HMAC-SHA512(mac_key, page1[16 : PAGE-80+16] || LE32(1))。
    我们先填随机 body，再把算出的 stored_hmac 放到页尾 64 字节。
    """
    PAGE, SALT, IV, HMAC, RES = 4096, 16, 16, 64, 80
    body = bytes((i * 7 + 3) & 0xFF for i in range(PAGE - SALT - RES))  # 确定性伪随机
    reserve_head = bytes((i * 5 + 1) & 0xFF for i in range(RES - HMAC))  # IV(16)
    page = bytearray(PAGE)
    page[:SALT] = salt
    page[SALT:PAGE - RES] = body
    page[PAGE - RES:PAGE - HMAC] = reserve_head
    mac_salt = bytes(b ^ 0x3a for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=32)
    hm = hmac_mod.new(mac_key, bytes(page[SALT:PAGE - RES + IV]), hashlib.sha512)
    hm.update(struct.pack('<I', 1))
    page[PAGE - HMAC:PAGE] = hm.digest()
    return bytes(page)


class TestKeyVerify(unittest.TestCase):
    def test_verify_roundtrip(self):
        enc = bytes(range(32))                 # 已知 32 字节 key
        salt = bytes((i * 11 + 2) & 0xFF for i in range(16))
        page1 = _make_page1(enc, salt)
        self.assertTrue(ext.verify_key_page1(enc, page1))

    def test_verify_rejects_wrong_key(self):
        enc = bytes(range(32))
        salt = bytes((i * 11 + 2) & 0xFF for i in range(16))
        page1 = _make_page1(enc, salt)
        wrong = bytes((b ^ 0xFF) for b in enc)
        self.assertFalse(ext.verify_key_page1(wrong, page1))

    def test_verify_rejects_bad_lengths(self):
        page1 = _make_page1(bytes(range(32)), bytes(16))
        self.assertFalse(ext.verify_key_page1(b'\x00' * 31, page1))   # key 短
        self.assertFalse(ext.verify_key_page1(bytes(range(32)), b'\x00' * 100))  # 页短


class TestKeyToDbMatching(unittest.TestCase):
    """提取器逻辑：一批候选 enc_key + 一堆库的 page1 → 正确对回每个库。"""

    def test_match_candidates_to_dbs(self):
        # 两个库，各自一把 key（含一个干扰候选）
        k_a = bytes((i + 1) & 0xFF for i in range(32))
        k_b = bytes((i * 3 + 9) & 0xFF for i in range(32))
        salt_a = bytes((i + 5) & 0xFF for i in range(16))
        salt_b = bytes((i * 2 + 1) & 0xFF for i in range(16))
        db_files = {
            "message/message_0.db": {"page1": _make_page1(k_a, salt_a)},
            "contact/contact.db":   {"page1": _make_page1(k_b, salt_b)},
        }
        cands = {k_a.hex(), k_b.hex(), (b'\xAA' * 32).hex()}  # 第三个是噪声

        matched = {}
        for enc in cands:
            eb = bytes.fromhex(enc)
            for rel, info in db_files.items():
                if ext.verify_key_page1(eb, info["page1"]):
                    matched[os.path.normpath(rel)] = enc

        self.assertEqual(matched.get(os.path.normpath("message/message_0.db")), k_a.hex())
        self.assertEqual(matched.get(os.path.normpath("contact/contact.db")), k_b.hex())
        self.assertEqual(len(matched), 2)  # 噪声候选没匹配上任何库


class TestQueryRefactor(unittest.TestCase):
    """读库层重构：generation-based 类层次 + 旧名别名 + per-DB keys 解析。"""

    def test_class_hierarchy(self):
        # 4.x 两个端都继承共享基类；Mac4 不再是 Windows 的子类（去掉旧的纠缠）
        self.assertTrue(issubclass(wq.MacV4Query, wq.V4QueryBase))
        self.assertTrue(issubclass(wq.WindowsV4Query, wq.V4QueryBase))
        self.assertFalse(issubclass(wq.MacV4Query, wq.WindowsV4Query))

    def test_backward_compat_aliases(self):
        self.assertIs(wq.WindowsWeChatQuery, wq.WindowsV4Query)
        self.assertIs(wq.MacV4WeChatQuery, wq.MacV4Query)
        # 微信 3.x 下线（v0.9.1）后，MacV3Query / MacWeChatQuery / WeChatExporter
        # 别名已随类一并移除；确认它们确实不再导出。
        self.assertFalse(hasattr(wq, "MacV3Query"))
        self.assertFalse(hasattr(wq, "MacWeChatQuery"))
        self.assertFalse(hasattr(wq, "WeChatExporter"))

    def test_load_mac4_keys_plain_form(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "keys.json")
            with open(p, "w") as f:
                json.dump({"db_dir": "/x", "keys": {
                    "message/message_0.db": "aa" * 32,
                    "contact/contact.db": "bb" * 32,
                }}, f)
            got = wq.MacV4Query._load_mac4_keys(object.__new__(wq.MacV4Query), p)
            self.assertEqual(got[os.path.normpath("message/message_0.db")], "aa" * 32)
            self.assertEqual(len(got), 2)

    def test_load_mac4_keys_windows_shaped_form(self):
        # 兼容 {rel: {"enc_key": hex}}（与 windows_all_keys.json 同构）
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "keys.json")
            with open(p, "w") as f:
                json.dump({"contact/contact.db": {"enc_key": "cc" * 32, "salt": "00" * 16}}, f)
            got = wq.MacV4Query._load_mac4_keys(object.__new__(wq.MacV4Query), p)
            self.assertEqual(got[os.path.normpath("contact/contact.db")], "cc" * 32)

    def test_load_mac4_keys_missing_file(self):
        got = wq.MacV4Query._load_mac4_keys(object.__new__(wq.MacV4Query),
                                            "/nonexistent/keys.json")
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()

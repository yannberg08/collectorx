"""wexport.keycrypto 共享加密/命名逻辑单测（Mac4 + Win4 提取器共用的那份）。"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))

from wexport import keycrypto as kc  # noqa: E402


class TestDeriveAndVerify(unittest.TestCase):
    def test_derive_mac_key_shape_and_determinism(self):
        enc = bytes(range(32))
        salt = bytes(range(16))
        k1 = kc.derive_mac_key(enc, salt)
        k2 = kc.derive_mac_key(enc, salt)
        self.assertEqual(len(k1), kc.KEY_SZ)
        self.assertEqual(k1, k2)                    # 确定性
        self.assertNotEqual(k1, kc.derive_mac_key(enc, bytes(16)))  # salt 影响结果

    def _make_valid_page1(self, enc_key, salt):
        """按 SQLCipher4 布局造一页，其第 1 页 HMAC 用 enc_key 算得正确，供 verify 命中。"""
        import hashlib
        import hmac as hmac_mod
        body = os.urandom(kc.PAGE_SZ - kc.SALT_SZ - kc.RESERVE_SZ)  # salt 后、reserve 前
        iv = os.urandom(kc.IV_SZ)
        mac_key = kc.derive_mac_key(enc_key, salt)
        hm = hmac_mod.new(mac_key, body + iv, hashlib.sha512)
        hm.update(struct.pack('<I', 1))
        page = salt + body + iv + hm.digest()
        assert len(page) == kc.PAGE_SZ, len(page)
        return page

    def test_verify_key_page1_accept_and_reject(self):
        enc_key = os.urandom(kc.KEY_SZ)
        salt = os.urandom(kc.SALT_SZ)
        page1 = self._make_valid_page1(enc_key, salt)
        self.assertTrue(kc.verify_key_page1(enc_key, page1))
        self.assertFalse(kc.verify_key_page1(os.urandom(kc.KEY_SZ), page1))  # 错 key
        self.assertFalse(kc.verify_key_page1(enc_key, page1[:100]))          # 页不完整


class TestCollectDbFiles(unittest.TestCase):
    def test_collect_returns_salt_and_page1(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, 'message')
            os.makedirs(sub)
            full = os.path.join(sub, 'message_0.db')
            salt = bytes(range(16))
            with open(full, 'wb') as f:
                f.write(salt + os.urandom(kc.PAGE_SZ - kc.SALT_SZ))  # 满一页
            with open(os.path.join(d, 'tiny.db'), 'wb') as f:
                f.write(salt + b'\x00' * 8)                          # 只有 salt，无整页
            # 干扰文件应被跳过
            open(os.path.join(d, 'message_0.db-wal'), 'wb').close()
            db_files, salt_to_dbs = kc.collect_db_files(d)
            rels = {os.path.normpath(k) for k in db_files}
            self.assertIn(os.path.normpath('message/message_0.db'), rels)
            self.assertIn('tiny.db', db_files)
            self.assertNotIn('message_0.db-wal', db_files)
            # 满页的有 page1，salt 短的没有
            full_rel = [k for k in db_files if k.endswith('message_0.db')][0]
            self.assertIn('page1', db_files[full_rel])
            self.assertNotIn('page1', db_files['tiny.db'])
            self.assertEqual(db_files[full_rel]['salt'], salt.hex())
            self.assertIn(salt.hex(), salt_to_dbs)


class TestKeysNaming(unittest.TestCase):
    def test_keys_path_is_unified(self):
        self.assertTrue(kc.keys_path('/x/data').endswith('all_keys.json'))

    def test_resolve_prefers_unified_then_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(kc.resolve_keys_file(d))
            # 只有旧名 → 兜底命中
            legacy = os.path.join(d, 'windows_all_keys.json')
            open(legacy, 'w').close()
            self.assertEqual(kc.resolve_keys_file(d), legacy)
            # 出现统一名 → 优先统一名
            unified = os.path.join(d, 'all_keys.json')
            open(unified, 'w').close()
            self.assertEqual(kc.resolve_keys_file(d), unified)


if __name__ == '__main__':
    unittest.main()

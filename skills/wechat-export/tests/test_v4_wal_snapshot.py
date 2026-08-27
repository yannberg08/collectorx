#!/usr/bin/env python3
"""Synthetic SQLCipher WAL coverage for Windows/Linux snapshot decryption."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import wechat_query as wq  # noqa: E402
from wexport import keycrypto as kc  # noqa: E402

try:
    import sqlcipher3
    from Crypto.Cipher import AES  # noqa: F401
except ImportError:
    sqlcipher3 = None


@unittest.skipIf(sqlcipher3 is None, 'sqlcipher3/pycryptodome test dependencies unavailable')
class TestV4WalSnapshot(unittest.TestCase):
    KEY = 'cd' * 32

    def _open_encrypted_wal_db(self, path):
        conn = sqlcipher3.connect(path)
        cur = conn.cursor()
        for sql in (
            f'PRAGMA key="x\'{self.KEY}\'"',
            'PRAGMA cipher_page_size=4096',
            'PRAGMA kdf_iter=256000',
            'PRAGMA cipher_hmac_algorithm=HMAC_SHA512',
            'PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512',
            'PRAGMA journal_mode=WAL',
            'PRAGMA wal_autocheckpoint=0',
        ):
            cur.execute(sql)
        cur.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, text TEXT)')
        conn.commit()
        cur.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return conn, cur

    def test_manual_decrypt_applies_last_committed_wal(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, 'message_0.db')
            out = os.path.join(d, 'plain.db')
            conn, cur = self._open_encrypted_wal_db(db)
            cur.execute('INSERT INTO messages(text) VALUES (?)', ('from-wal',))
            conn.commit()

            ok, detail = kc.decrypt_database(db, out, self.KEY)
            self.assertTrue(ok, detail)
            self.assertIn('committed WAL frames', detail)
            with sqlite3.connect(out) as plain:
                self.assertEqual(
                    plain.execute('SELECT text FROM messages').fetchall(),
                    [('from-wal',)],
                )
            conn.close()

    def test_page_one_update_in_wal_is_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, 'page1.db')
            out = os.path.join(d, 'plain.db')
            conn, cur = self._open_encrypted_wal_db(db)
            cur.execute('PRAGMA user_version=42')
            conn.commit()

            ok, detail = kc.decrypt_database(db, out, self.KEY)
            self.assertTrue(ok, detail)
            with sqlite3.connect(out) as plain:
                self.assertEqual(plain.execute('PRAGMA user_version').fetchone()[0], 42)
            conn.close()

    def test_invalid_wal_tail_does_not_hide_last_valid_commit(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, 'message_0.db')
            snapshots = os.path.join(d, 'snapshots')
            out = os.path.join(d, 'plain.db')
            conn, cur = self._open_encrypted_wal_db(db)
            cur.execute('INSERT INTO messages(text) VALUES (?)', ('valid-commit',))
            conn.commit()

            snapshot_db, _ = wq._copy_database_bundle(db, snapshots)
            with open(snapshot_db + '-wal', 'ab') as wal:
                wal.write(b'\x00' * (24 + kc.PAGE_SZ))
            ok, detail = kc.decrypt_database(snapshot_db, out, self.KEY)
            self.assertTrue(ok, detail)
            with sqlite3.connect(out) as plain:
                self.assertEqual(
                    plain.execute('SELECT text FROM messages').fetchall(),
                    [('valid-commit',)],
                )
            conn.close()

    def test_query_filter_skips_non_query_databases(self):
        for path in (
                'message/message_fts.db', 'message/media_0.db',
                'message/message_resource.db',
                'message/message_0.db.factory/old/message_0.db'):
            self.assertTrue(wq._skip_v4_query_database(path), path)
        self.assertFalse(wq._skip_v4_query_database('message/message_0.db'))

    def test_windows_path_snapshots_and_wal_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, 'live')
            cache = os.path.join(d, 'cache')
            message_dir = os.path.join(live, 'message')
            os.makedirs(message_dir)
            os.makedirs(cache)
            db = os.path.join(message_dir, 'message_0.db')
            conn, cur = self._open_encrypted_wal_db(db)
            cur.execute('INSERT INTO messages(text) VALUES (?)', ('first-wal',))
            conn.commit()

            keys_file = os.path.join(d, 'all_keys.json')
            with open(keys_file, 'w', encoding='utf-8') as f:
                json.dump({'message/message_0.db': {'enc_key': self.KEY}}, f)

            query = object.__new__(wq.V4QueryBase)
            query.db_dir = live
            with mock.patch.object(wq, '_get_decrypt_cache_dir',
                                   return_value=cache), \
                    mock.patch.object(wq, 'decrypt_database',
                                      wraps=wq.decrypt_database) as decrypt:
                query._decrypt_keys_file_snapshots(keys_file)
                self.assertEqual(decrypt.call_count, 1)
                query._decrypt_keys_file_snapshots(keys_file)
                self.assertEqual(decrypt.call_count, 1)

                cur.execute('INSERT INTO messages(text) VALUES (?)', ('second-wal',))
                conn.commit()
                query._decrypt_keys_file_snapshots(keys_file)
                self.assertEqual(decrypt.call_count, 2)

            plaintext = os.path.join(cache, 'message', 'message_0.db')
            with sqlite3.connect(plaintext) as plain:
                self.assertEqual(
                    plain.execute('SELECT text FROM messages ORDER BY id').fetchall(),
                    [('first-wal',), ('second-wal',)],
                )
            conn.close()


if __name__ == '__main__':
    unittest.main()

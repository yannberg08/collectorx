#!/usr/bin/env python3
"""Regression tests for Mac 4.x snapshot-first decryption.

All files are synthetic and live under TemporaryDirectory.  No real WeChat
database, key, or process is accessed.
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import wechat_query as wq  # noqa: E402


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        if sql.startswith('ATTACH DATABASE'):
            self.conn.plaintext_path = params[0]
        elif 'sqlcipher_export' in sql:
            with open(self.conn.plaintext_path, 'wb') as f:
                f.write(b'fake plaintext sqlite')
        return self


class _FakeConnection:
    def __init__(self, path):
        self.path = path
        self.plaintext_path = None

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        return None


class _FakeSQLCipher(types.ModuleType):
    def __init__(self, live_root):
        super().__init__('sqlcipher3')
        self.live_root = os.path.realpath(live_root)
        self.opened = []

    def connect(self, path):
        real_path = os.path.realpath(path)
        self.opened.append({
            'path': real_path,
            'has_wal': os.path.exists(path + '-wal'),
            'has_shm': os.path.exists(path + '-shm'),
        })
        if os.path.commonpath([real_path, self.live_root]) == self.live_root:
            raise AssertionError('SQLCipher attempted to open the live WeChat DB')
        return _FakeConnection(path)


def _make_query(rel):
    query = object.__new__(wq.MacV4Query)
    query.db_keys = {os.path.normpath(rel): 'aa' * 32}
    query.full_key = ''
    return query


class TestMac4Snapshot(unittest.TestCase):
    def test_bundle_state_changes_when_only_wal_changes(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, 'message_0.db')
            with open(db, 'wb') as f:
                f.write(b'db')
            with open(db + '-wal', 'wb') as f:
                f.write(b'wal-1')
            before = wq._database_bundle_state(db)
            with open(db + '-wal', 'ab') as f:
                f.write(b'-new-message')
            after = wq._database_bundle_state(db)
            self.assertEqual(before[''], after[''])
            self.assertNotEqual(before['-wal'], after['-wal'])

    def test_decrypt_opens_snapshot_and_wal_refreshes_cache(self):
        with tempfile.TemporaryDirectory() as d:
            live_root = os.path.join(d, 'live')
            cache_root = os.path.join(d, 'cache')
            message_dir = os.path.join(live_root, 'message')
            os.makedirs(message_dir)
            os.makedirs(cache_root)
            db = os.path.join(message_dir, 'message_0.db')
            for suffix, content in (
                    ('', b'encrypted-db'),
                    ('-wal', b'encrypted-wal'),
                    ('-shm', b'encrypted-shm')):
                with open(db + suffix, 'wb') as f:
                    f.write(content)

            rel = os.path.join('message', 'message_0.db')
            query = _make_query(rel)
            fake_sqlcipher = _FakeSQLCipher(live_root)
            with mock.patch.dict(sys.modules, {'sqlcipher3': fake_sqlcipher}), \
                    mock.patch.object(wq, '_get_decrypt_cache_dir',
                                      return_value=cache_root):
                query._decrypt_mac4(live_root)
                self.assertEqual(len(fake_sqlcipher.opened), 1)
                self.assertTrue(fake_sqlcipher.opened[0]['has_wal'])
                self.assertTrue(fake_sqlcipher.opened[0]['has_shm'])

                # Unchanged DB/WAL/SHM reuses the plaintext cache.
                query._decrypt_mac4(live_root)
                self.assertEqual(len(fake_sqlcipher.opened), 1)

                # A WAL-only update invalidates the cache and opens a new snapshot.
                with open(db + '-wal', 'ab') as f:
                    f.write(b'-new-message')
                query._decrypt_mac4(live_root)
                self.assertEqual(len(fake_sqlcipher.opened), 2)

    def test_unstable_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, 'message_0.db')
            snapshots = os.path.join(d, 'snapshots')
            with open(db, 'wb') as f:
                f.write(b'db')

            real_copy2 = wq.shutil.copy2

            def copy_then_change_source(src, dst):
                result = real_copy2(src, dst)
                with open(src, 'ab') as f:
                    f.write(b'x')
                return result

            with mock.patch.object(wq.shutil, 'copy2',
                                   side_effect=copy_then_change_source):
                with self.assertRaisesRegex(RuntimeError,
                                            'could not create stable database snapshot'):
                    wq._copy_database_bundle(db, snapshots, max_attempts=2)


if __name__ == '__main__':
    unittest.main()

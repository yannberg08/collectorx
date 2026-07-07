#!/usr/bin/env python3
"""
Unit tests for wechat-export v0.5.0 标签查询功能。

无需 pytest；直接 `python3 test_wechat_tags.py` 即跑。

覆盖：
  1. _parse_label_id_list 各种格式
  2. WindowsWeChatQuery 标签加载（camelCase schema + snake_case schema）
  3. list_tags / query_by_tag / get_contact_tags
  4. --tag 空查询 / 标签不存在
  5. SQL 注入防护（参数化查询）
  6. Mac 4.x 标签契约（4.x 本地标签可用，3.x 路径已下线）
  7. --contact 输出附带 tags 字段
"""
import os
import sys
import sqlite3
import tempfile
import shutil
import unittest
import importlib.util

# ── 加载被测模块（避免污染 sys.path） ────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.join(HERE, 'wechat_query.py')
spec = importlib.util.spec_from_file_location('wechat_query', MOD_PATH)
wq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wq)


class TestParseLabelIdList(unittest.TestCase):
    """Test the _parse_label_id_list helper that decodes the raw LabelIDList column."""

    def test_comma_wrapped(self):
        # camelCase schema classic: ',1,2,5,'
        self.assertEqual(wq._parse_label_id_list(',1,2,5,'), [1, 2, 5])

    def test_plain_csv(self):
        self.assertEqual(wq._parse_label_id_list('1,2,5'), [1, 2, 5])

    def test_json_array(self):
        self.assertEqual(wq._parse_label_id_list('[1,2,5]'), [1, 2, 5])

    def test_empty(self):
        self.assertEqual(wq._parse_label_id_list(''), [])
        self.assertEqual(wq._parse_label_id_list(None), [])
        self.assertEqual(wq._parse_label_id_list(','), [])

    def test_bytes(self):
        self.assertEqual(wq._parse_label_id_list(b',1,2,'), [1, 2])

    def test_malformed(self):
        # garbage values should be silently skipped
        self.assertEqual(wq._parse_label_id_list('1,abc,2,'), [1, 2])

    def test_whitespace(self):
        self.assertEqual(wq._parse_label_id_list(' 1 , 2 , 3 '), [1, 2, 3])


class TestExportFormatting(unittest.TestCase):
    """Export should be compact by default and avoid raw XML/card payloads."""

    def test_compact_export_is_single_line(self):
        msg = {
            'time': 1710000000,
            'message': '第一行\n第二行',
            'is_received': True,
            'sender': 'Alice',
            'chat_name': '项目群',
            'is_group': True,
        }

        line = wq.format_export_message(msg)

        self.assertEqual(line.count('\n'), 0)
        self.assertIn('项目群·Alice', line)
        self.assertIn('第一行 第二行', line)

    def test_compact_export_sanitizes_xml_payload(self):
        msg = {
            'time': 1710000000,
            'message': '<msg><emoji cdnurl="https://example.invalid/huge" md5="abc"/></msg>',
            'is_received': True,
            'sender': 'Bob',
            'chat_name': 'Bob',
            'is_group': False,
        }

        line = wq.format_export_message(msg)

        self.assertIn('[表情/图片]', line)
        self.assertNotIn('<msg>', line)
        self.assertNotIn('cdnurl', line)

    def test_compact_export_uses_link_title(self):
        msg = {
            'time': 1710000000,
            'message': '<msg><appmsg><title><![CDATA[项目更新]]></title><des><![CDATA[简短摘要]]></des></appmsg></msg>',
            'is_received': True,
            'sender': 'Carol',
            'chat_name': 'Carol',
            'is_group': False,
        }

        line = wq.format_export_message(msg)

        self.assertIn('[链接] 项目更新 - 简短摘要', line)
        self.assertNotIn('<appmsg>', line)

    def test_compact_export_omits_unknown_xml_payload(self):
        msg = {
            'time': 1710000000,
            'message': '<sysmsg><template>内部结构</template><pass_ticket>secret</pass_ticket></sysmsg>',
            'is_received': True,
            'sender': 'Dave',
            'chat_name': 'Dave',
            'is_group': False,
        }

        line = wq.format_export_message(msg)

        self.assertEqual(line, '')


class TestOwnerRelevantFiltering(unittest.TestCase):
    """Owner relevance keeps private chats and only groups the owner joined."""

    def test_detect_active_groups_ignores_received_group_noise(self):
        all_groups = {'潜水群', '活跃群'}
        messages = [
            {'chat_name': '潜水群', 'is_group': True, 'is_received': True, 'message': '别人刷屏'},
            {'chat_name': '活跃群', 'is_group': True, 'is_received': False, 'message': '我参与了'},
            {'chat_name': '撤回群', 'is_group': True, 'is_received': False, 'message': '撤回了一条消息'},
            {'chat_name': '张三', 'is_group': False, 'is_received': True, 'message': '私聊'},
        ]

        active = wq._detect_active_groups(messages, all_groups)

        self.assertEqual(active, {'活跃群'})

    def test_filter_keeps_private_and_active_groups(self):
        all_groups = {'潜水群', '活跃群'}
        messages = [
            {'chat_name': '张三', 'is_group': False, 'message': '私聊'},
            {'chat_name': '潜水群', 'is_group': True, 'message': '别人刷屏'},
            {'chat_name': '活跃群', 'is_group': True, 'message': '群内事项'},
        ]

        kept = wq._filter_owner_relevant_messages(
            messages,
            all_groups,
            exclude_set=set(),
            group_whitelist={'活跃群'},
        )

        self.assertEqual([m['chat_name'] for m in kept], ['张三', '活跃群'])

    def test_filter_respects_exclude_and_include_groups(self):
        all_groups = {'指定群'}
        messages = [
            {'chat_name': '张三', 'is_group': False, 'message': '私聊'},
            {'chat_name': '指定群', 'is_group': True, 'message': '显式保留'},
        ]

        kept = wq._filter_owner_relevant_messages(
            messages,
            all_groups,
            exclude_set={'张三'},
            group_whitelist={'指定群'},
        )

        self.assertEqual([m['chat_name'] for m in kept], ['指定群'])


class TestCollectPayloadFormatting(unittest.TestCase):
    """Collect JSON should default to compact output to avoid line-count bloat."""

    def test_collect_payload_defaults_to_compact_json(self):
        records = [
            {'id': 'wx-1', 'data': {'chat': '张三', 'sender': '张三', 'time': '2026-06-28 09:00:00', 'text': '第一条'}},
            {'id': 'wx-2', 'data': {'chat': '项目群', 'sender': '我', 'time': '2026-06-28 09:01:00', 'text': '第二条'}},
        ]

        payload = wq._dump_collect_payload(records)

        self.assertEqual(payload.count('\n'), 0)
        self.assertEqual(wq._json.loads(payload), records)
        self.assertNotIn(': ', payload)

    def test_collect_payload_can_pretty_print_when_requested(self):
        records = [{'id': 'wx-1', 'data': {'chat': '张三', 'sender': '张三', 'time': '2026-06-28 09:00:00', 'text': '第一条'}}]

        payload = wq._dump_collect_payload(records, pretty=True)

        self.assertGreater(payload.count('\n'), 1)
        self.assertEqual(wq._json.loads(payload), records)

    def test_collect_source_for_private_chat(self):
        source = wq._format_collect_source('张三', False, '2026-06-28 09:00:00')

        self.assertEqual(source, '跟张三在 2026-06-28 的微信聊天')

    def test_collect_source_for_group_chat(self):
        source = wq._format_collect_source('项目群', True, '2026-06-28 09:00:00')

        self.assertEqual(source, '微信群「项目群」· 2026-06-28 的聊天')


def _make_windows_contact_db(tmpdir, schema='camel'):
    """Build a fake Windows contact.db with either camelCase or snake_case schema."""
    contact_dir = os.path.join(tmpdir, 'contact')
    os.makedirs(contact_dir, exist_ok=True)
    db_path = os.path.join(contact_dir, 'contact.db')

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if schema == 'camel':
        cur.execute(
            """CREATE TABLE ContactLabel (
                LabelID INTEGER PRIMARY KEY,
                LabelName TEXT
            )"""
        )
        cur.execute(
            """CREATE TABLE Contact (
                username TEXT PRIMARY KEY,
                remark TEXT,
                nick_name TEXT,
                LabelIDList TEXT
            )"""
        )
        cur.executemany(
            "INSERT INTO ContactLabel (LabelID, LabelName) VALUES (?, ?)",
            [(1, '客户'), (2, '供应商'), (3, '同事'), (4, '家人')],
        )
        cur.executemany(
            "INSERT INTO Contact (username, remark, nick_name, LabelIDList) VALUES (?, ?, ?, ?)",
            [
                ('wxid_alice', 'Alice利氪', 'Alice', ',1,3,'),     # 客户 + 同事
                ('wxid_bob', 'Bob麦杰', 'Bob', ',1,'),             # 客户
                ('wxid_carol', 'Carol', 'Carol', ',2,'),           # 供应商
                ('wxid_dave', 'Dave', 'Dave', ''),                 # no labels
                ('wxid_eve', 'Eve', 'Eve', ',1,2,3,4,'),          # all tags
            ],
        )
    elif schema == 'snake':
        cur.execute(
            """CREATE TABLE contact_label (
                label_id INTEGER PRIMARY KEY,
                label_name TEXT
            )"""
        )
        cur.execute(
            """CREATE TABLE contact (
                username TEXT PRIMARY KEY,
                remark TEXT,
                nick_name TEXT,
                label_id_list TEXT
            )"""
        )
        cur.executemany(
            "INSERT INTO contact_label (label_id, label_name) VALUES (?, ?)",
            [(10, 'VIP客户'), (20, '竞品'), (30, '朋友')],
        )
        cur.executemany(
            "INSERT INTO contact (username, remark, nick_name, label_id_list) VALUES (?, ?, ?, ?)",
            [
                ('wxid_alice', 'Alice', 'Alice', '10,30'),
                ('wxid_bob', 'Bob', 'Bob', '20'),
                ('wxid_carol', 'Carol', 'Carol', ''),
            ],
        )

    conn.commit()
    conn.close()
    return db_path


class _FakeWindowsQuery(wq.WindowsWeChatQuery):
    """Test harness — skip __init__'s decryption + message loading."""

    def __init__(self, workdir):
        self.sqlite3 = sqlite3
        self._work_dir = workdir
        self.db_dir = workdir
        self.contacts = {}
        self.group_names = {}
        self.sender_id_to_name = {}
        self._temp_dir = None
        self.labels = {}
        self.label_name_to_id = {}
        self.contact_labels = {}
        self._labels_schema = None
        # populate self.contacts from the fake contact.db
        contact_db = os.path.join(workdir, 'contact', 'contact.db')
        if os.path.exists(contact_db):
            conn = sqlite3.connect(contact_db)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0].lower(): r[0] for r in cur.fetchall()}
            cname = tables.get('contact')
            if cname:
                cur.execute(f"PRAGMA table_info({cname})")
                cols = [c[1] for c in cur.fetchall()]
                col_set = set(c.lower() for c in cols)
                uname_col = 'username' if 'username' in col_set else None
                remark_col = 'remark' if 'remark' in col_set else None
                nick_col = 'nick_name' if 'nick_name' in col_set else None
                if uname_col:
                    q = f"SELECT {uname_col}"
                    q += f", {remark_col}" if remark_col else ", NULL"
                    q += f", {nick_col}" if nick_col else ", NULL"
                    q += f" FROM {cname}"
                    cur.execute(q)
                    for uname, remark, nick in cur.fetchall():
                        name = remark if remark else nick
                        if name:
                            self.contacts[uname] = name
            conn.close()
        self._load_labels()


class TestWindowsLabelLoading(unittest.TestCase):
    """Validate _load_labels() on both schema variants."""

    def test_camel_schema(self):
        tmp = tempfile.mkdtemp(prefix='wq_test_')
        try:
            _make_windows_contact_db(tmp, schema='camel')
            q = _FakeWindowsQuery(tmp)
            self.assertEqual(q._labels_schema, 'camel')
            self.assertEqual(len(q.labels), 4)
            self.assertEqual(q.labels[1], '客户')
            self.assertEqual(q.labels[2], '供应商')
            self.assertEqual(q.label_name_to_id['客户'], 1)
            self.assertIn('wxid_alice', q.contact_labels)
            self.assertEqual(sorted(q.contact_labels['wxid_alice']), [1, 3])
            self.assertEqual(sorted(q.contact_labels['wxid_eve']), [1, 2, 3, 4])
            self.assertNotIn('wxid_dave', q.contact_labels)
        finally:
            shutil.rmtree(tmp)

    def test_snake_schema(self):
        tmp = tempfile.mkdtemp(prefix='wq_test_')
        try:
            _make_windows_contact_db(tmp, schema='snake')
            q = _FakeWindowsQuery(tmp)
            self.assertEqual(q._labels_schema, 'snake')
            self.assertEqual(len(q.labels), 3)
            self.assertEqual(q.labels[10], 'VIP客户')
            self.assertEqual(q.label_name_to_id['vip客户'], 10)
            self.assertEqual(q.contact_labels['wxid_alice'], [10, 30])
        finally:
            shutil.rmtree(tmp)

    def test_missing_contact_db(self):
        """No contact.db → labels empty, no crash."""
        tmp = tempfile.mkdtemp(prefix='wq_test_')
        try:
            q = _FakeWindowsQuery(tmp)
            self.assertEqual(q.labels, {})
            self.assertEqual(q.contact_labels, {})
            self.assertIsNone(q._labels_schema)
        finally:
            shutil.rmtree(tmp)


class TestWindowsLabelQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='wq_test_')
        _make_windows_contact_db(cls.tmp, schema='camel')
        cls.q = _FakeWindowsQuery(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_list_tags_returns_all(self):
        tags = self.q.list_tags()
        self.assertEqual(len(tags), 4)
        for t in tags:
            self.assertIn('id', t)
            self.assertIn('name', t)
            self.assertIn('count', t)
        kh = next(t for t in tags if t['name'] == '客户')
        self.assertEqual(kh['count'], 3)
        jiaren = next(t for t in tags if t['name'] == '家人')
        self.assertEqual(jiaren['count'], 1)
        names = [t['name'] for t in tags]
        self.assertEqual(names, sorted(names))

    def test_query_by_tag_existing(self):
        contacts = self.q.query_by_tag('客户')
        self.assertEqual(len(contacts), 3)
        names = sorted(c['name'] for c in contacts)
        self.assertEqual(names, ['Alice利氪', 'Bob麦杰', 'Eve'])
        alice = next(c for c in contacts if c['name'] == 'Alice利氪')
        self.assertIn('客户', alice['tags'])
        self.assertIn('同事', alice['tags'])

    def test_query_by_tag_case_insensitive(self):
        tmp = tempfile.mkdtemp(prefix='wq_test_')
        try:
            _make_windows_contact_db(tmp, schema='snake')
            q = _FakeWindowsQuery(tmp)
            contacts = q.query_by_tag('vip客户')
            self.assertEqual(len(contacts), 1)
            self.assertEqual(contacts[0]['name'], 'Alice')
        finally:
            shutil.rmtree(tmp)

    def test_query_by_tag_not_found(self):
        contacts = self.q.query_by_tag('不存在的标签')
        self.assertEqual(contacts, [])

    def test_get_contact_tags_by_name(self):
        tags = self.q.get_contact_tags('Alice')
        self.assertIn('客户', tags)
        self.assertIn('同事', tags)
        self.assertNotIn('供应商', tags)

    def test_get_contact_tags_by_wxid(self):
        tags = self.q.get_contact_tags('wxid_bob')
        self.assertEqual(tags, ['客户'])

    def test_get_contact_tags_unknown(self):
        tags = self.q.get_contact_tags('不存在的人')
        self.assertEqual(tags, [])

    def test_sql_injection_tag_name(self):
        """Malicious tag name shouldn't crash or drop anything."""
        malicious = "'; DROP TABLE ContactLabel; --"
        result = self.q.query_by_tag(malicious)
        self.assertEqual(result, [])
        self.assertEqual(len(self.q.labels), 4)

    def test_list_tag_contacts_usernames(self):
        """Helper method should return wxid strings of tag members."""
        usernames = self.q.list_tag_contacts_usernames('客户')
        self.assertEqual(sorted(usernames), ['wxid_alice', 'wxid_bob', 'wxid_eve'])
        # Non-existent tag returns empty list
        self.assertEqual(self.q.list_tag_contacts_usernames('不存在'), [])


class TestMac4LabelContract(unittest.TestCase):
    """Mac 4.x shares the V4 label implementation with Windows 4.x.

    The old Mac 3.x SQLCipher3 path was removed in v0.9.1; tests should guard
    that contract instead of expecting Mac labels to degrade.
    """

    def test_mac4_compat_alias_exists(self):
        self.assertIs(wq.MacV4WeChatQuery, wq.MacV4Query)

    def test_mac3_query_class_is_removed(self):
        self.assertFalse(hasattr(wq, 'MacWeChatQuery'))


class TestVersionAndConstants(unittest.TestCase):
    def test_version(self):
        version_path = os.path.join(HERE, '..', 'VERSION')
        with open(version_path, encoding='utf-8') as f:
            expected = f.read().strip()
        self.assertEqual(wq.__version__, expected)

    def test_mac_not_supported_msg_has_guidance(self):
        msg = wq._LABEL_NOT_SUPPORTED_MAC
        self.assertIn('4.x', msg)
        self.assertIn('--contact', msg)
        self.assertIn('Kevin', msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)

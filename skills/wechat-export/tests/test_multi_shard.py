#!/usr/bin/env python3
"""Regression test for the multi-shard message_*.db bug (fixed in 0.6.4).

Windows WeChat 4.x splits messages across message_0.db .. message_N.db, and one
chat's Msg_ table may sit in — or be split across — any shard. v0.6.3 and earlier
only ever opened message_0.db, so any contact whose table lived in another shard
returned 0 results.

This is a synthetic-fixture test — it builds fake shards in a temp dir and needs
no real WeChat install. It can run on any platform.
"""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import wechat_query  # noqa: E402


def _msg_ddl(tname):
    return (f"CREATE TABLE {tname} "
            "(create_time INTEGER, message_content TEXT, real_sender_id INTEGER)")


def _build_fixture(root):
    """4 shards. Alice's table sits ONLY in message_3.db (the reported bug);
    Bob's table is split across message_0.db + message_2.db."""
    msg_dir = os.path.join(root, "message")
    contact_dir = os.path.join(root, "contact")
    os.makedirs(msg_dir)
    os.makedirs(contact_dir)

    alice, bob = "wxid_alice", "wxid_bob"
    t_alice = "Msg_" + hashlib.md5(alice.encode()).hexdigest()
    t_bob = "Msg_" + hashlib.md5(bob.encode()).hexdigest()

    c = sqlite3.connect(os.path.join(contact_dir, "contact.db"))
    c.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT)")
    c.executemany("INSERT INTO contact VALUES (?,?,?)", [
        (alice, "Alice", "alice_nick"),
        (bob, "Bob", "bob_nick"),
    ])
    c.commit()
    c.close()

    shards = {}
    for i in range(4):
        conn = sqlite3.connect(os.path.join(msg_dir, f"message_{i}.db"))
        conn.execute("CREATE TABLE Name2Id (user_name TEXT)")
        shards[i] = conn

    # Alice — table ONLY in message_3.db
    shards[3].execute(_msg_ddl(t_alice))
    shards[3].executemany(f"INSERT INTO {t_alice} VALUES (?,?,?)", [
        (3000, "alice msg in shard 3 — about 蒸馏", 2),
        (3100, "alice second msg shard 3", 1),
        (3200, "alice third msg shard 3", 2),
    ])

    # Bob — same table split across message_0.db (old) + message_2.db (recent)
    shards[0].execute(_msg_ddl(t_bob))
    shards[0].executemany(f"INSERT INTO {t_bob} VALUES (?,?,?)", [
        (1000, "bob old msg in shard 0", 1),
        (1100, "bob old msg 2 shard 0", 2),
    ])
    shards[2].execute(_msg_ddl(t_bob))
    shards[2].executemany(f"INSERT INTO {t_bob} VALUES (?,?,?)", [
        (5000, "bob recent msg in shard 2", 2),
        (5100, "bob recent msg 2 shard 2", 1),
    ])

    for conn in shards.values():
        conn.commit()
        conn.close()


def main():
    failures = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    tmp = tempfile.mkdtemp(prefix="wx_multishard_test_")
    try:
        _build_fixture(tmp)
        q = wechat_query.WindowsWeChatQuery(db_dir=tmp)

        # A. the reported bug — Alice's table only lives in message_3.db
        alice = q.query_messages(contact="Alice", limit=50)
        alice_text = " | ".join(m["message"] for m in alice)
        check("contact in non-zero shard: Alice returns 3 msgs", len(alice) == 3)
        check("contact in non-zero shard: shard-3 content present", "蒸馏" in alice_text)

        # B. split table — Bob spans message_0.db + message_2.db
        bob = q.query_messages(contact="Bob", limit=50)
        bob_text = " | ".join(m["message"] for m in bob)
        check("split table: Bob returns all 4 msgs across 2 shards", len(bob) == 4)
        check("split table: old shard-0 content present", "bob old msg" in bob_text)
        check("split table: new shard-2 content present", "bob recent msg" in bob_text)

        # C. smart --recent reaches non-zero shards
        recent_text = " | ".join(m["message"] for m in q.query_messages(limit=20))
        check("smart --recent: reaches shard-3 (Alice)", "alice" in recent_text.lower())
        check("smart --recent: reaches shard-2 (Bob recent)", "bob recent" in recent_text)

        # D. --search scans every shard
        found = q.query_messages(search="蒸馏", limit=None)
        check("--search: finds keyword living in shard-3", len(found) == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): {failures}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()

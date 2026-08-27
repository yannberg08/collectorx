#!/usr/bin/env python3
"""Regression tests for WeChat 4.x group-message sender detection."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import wechat_query  # noqa: E402


def main():
    failures = []

    def check(name, condition):
        print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
        if not condition:
            failures.append(name)

    query = wechat_query.WindowsWeChatQuery.__new__(wechat_query.WindowsWeChatQuery)
    query.contacts = {
        "wxid_group_member": "群成员甲",
        "custom_wechat_id": "群成员乙",
    }

    # Mac/Windows 4.x can assign a non-0/1 real_sender_id to owner-sent rows.
    owner, _ = query._parse_row((1000, "好的，我排到计划里面去", 37), True)
    check("owner group message ignores unstable real_sender_id", not owner["is_received"])
    check("owner group message has no fake sender", owner["sender"] is None)

    received, _ = query._parse_row(
        (1001, "wxid_group_member:\n你看下", 9), True)
    check("known wxid prefix marks received group message", received["is_received"])
    check("known wxid prefix resolves member name", received["sender"] == "群成员甲")
    check("known wxid prefix is removed from body", received["message"] == "你看下")

    custom, _ = query._parse_row(
        (1002, "custom_wechat_id:\r\n收到", 11), True)
    check("known custom account id is accepted", custom["sender"] == "群成员乙")
    check("CRLF group prefix is removed", custom["message"] == "收到")

    ordinary, _ = query._parse_row((1003, "计划:\n明天继续", 23), True)
    check("ordinary colon text remains owner-sent", not ordinary["is_received"])
    check("ordinary colon text is preserved", ordinary["message"] == "计划:\n明天继续")

    private_received, _ = query._parse_row(
        (1004, "私聊消息", 2), False, {2: "私聊联系人"})
    check("private direction logic remains unchanged", private_received["is_received"])
    check("private sender map remains unchanged", private_received["sender"] == "私聊联系人")

    print()
    if failures:
        print(f"FAILED ({len(failures)}): {failures}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
雪球关注列表CSV解析测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from xueqiu.parser import parse_watchlist_csv


def test_parse_csv():
    """测试CSV解析"""
    test_csv = Path("/tmp/test_xueqiu.csv")
    test_csv.write_text("""代码,名称,行业,备注
600519,贵州茅台,白酒,核心持仓
000858,五粮液,白酒,观察
""")
    
    records = parse_watchlist_csv(str(test_csv))
    
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    assert records[0]["code"] == "600519"
    assert records[1]["code"] == "000858"
    
    print("test_parse_csv: PASSED")


if __name__ == "__main__":
    test_parse_csv()
    print("\nAll tests passed!")

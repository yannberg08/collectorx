#!/usr/bin/env python3
"""
同花顺交割单CSV解析测试
"""
import sys
from pathlib import Path

# 添加当前目录到sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ths.parser import parse_portfolio_csv


def test_parse_csv():
    """测试CSV解析"""
    # 创建测试CSV
    test_csv = Path("/tmp/test_portfolio.csv")
    test_csv.write_text("""成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税
2024-01-15 09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00
2024-01-16 10:00:00,600519,贵州茅台,卖出,1850.00,100,185000.00,55.50,185.00
""")
    
    records = parse_portfolio_csv(str(test_csv))
    
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    assert records[0]["code"] == "600519"
    assert records[0]["direction"] == "买入"
    assert records[1]["direction"] == "卖出"
    
    print("test_parse_csv: PASSED")


def test_parse_empty_csv():
    """测试空CSV"""
    test_csv = Path("/tmp/test_empty.csv")
    test_csv.write_text("成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税\n")
    
    records = parse_portfolio_csv(str(test_csv))
    
    assert len(records) == 0, f"Expected 0 records, got {len(records)}"
    
    print("test_parse_empty_csv: PASSED")


if __name__ == "__main__":
    test_parse_csv()
    test_parse_empty_csv()
    print("\nAll tests passed!")

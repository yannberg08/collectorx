#!/bin/bash
# 测试所有采集器

echo "========================================="
echo "CollectorX 采集器测试"
echo "========================================="

# 测试邮箱采集器
echo ""
echo "1. 测试邮箱采集器..."
python3 ~/.hermes/skills/email-collector/scripts/email_api.py status

# 测试QQ采集器
echo ""
echo "2. 测试QQ采集器..."
python3 ~/.hermes/skills/qq-export/scripts/qq_query.py --help | head -5

# 测试笔记采集器
echo ""
echo "3. 测试笔记采集器..."
python3 ~/.hermes/skills/notes-collector/scripts/notes_api.py status

# 测试同花顺采集器
echo ""
echo "4. 测试同花顺交割单采集器..."
python3 ~/.hermes/skills/ths-portfolio/scripts/ths_query.py --help | head -5

# 测试东方财富采集器
echo ""
echo "5. 测试东方财富交割单采集器..."
python3 ~/.hermes/skills/eastmoney-portfolio/scripts/eastmoney_query.py --help | head -5

# 测试雪球采集器
echo ""
echo "6. 测试雪球关注列表采集器..."
python3 ~/.hermes/skills/xueqiu-watchlist/scripts/xueqiu_query.py --help | head -5

echo ""
echo "========================================="
echo "测试完成"
echo "========================================="

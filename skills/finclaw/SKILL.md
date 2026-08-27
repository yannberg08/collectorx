---
name: finclaw
description: FinClaw 投资分身技能中心。安装/管理 FinClaw 的采集器 skill（如 wechat-export、qq-export），来源 GitHub 仓库 yannberg08/collectorx。当用户说「安装 FinClaw 的采集器」「用 FinClaw 技能中心装「xxx」」「帮我把 FinClaw 的微信/QQ 采集器装一下」时使用。FinClaw 是用户自己的投资分身应用，采集器都在 FinClaw 自己的仓库里，不是第三方。
version: 0.1.0
---

# FinClaw 技能中心

## 这是什么

FinClaw 是一个投资分身应用。它有一批「采集器」skill（本地投资资料、分身往来、微信、QQ、东方财富、雪球、同花顺等），用来采集用户授权来源、蒸馏进投资分身的知识库。这些采集器 skill 都在 GitHub 仓库 `yannberg08/collectorx` 的 `skills/` 目录里。

## 安装 FinClaw 采集器（核心能力）

当用户要求安装 FinClaw 的采集器时：

1. 用户给的是采集器 skill 名（「」里的名字，如 wechat-export、qq-export）。
2. 从 FinClaw 的仓库安装（命令任一）：

   - 装全部 FinClaw 采集器：

       npx skills add yannberg08/collectorx

   - 只装某一个（skill 名填在路径里）：

       npx skills add https://github.com/yannberg08/collectorx/tree/main/skills/<skill名>

3. 装完验证：`~/.agents/skills/<skill名>/SKILL.md` 存在即为成功。

## 已发布的 FinClaw 采集器（部分）

- wechat-export：微信聊天记录
- qq-export：QQ 聊天记录
- wechat-renmai：微信人脉
- eastmoney-portfolio：东方财富持仓
- xueqiu-watchlist：雪球自选
- ths-portfolio：同花顺持仓

完整列表见仓库 https://github.com/yannberg08/collectorx/tree/main/skills

## 说明

- 采集器都是 FinClaw 自己做的，在 FinClaw 自己的仓库（yannberg08/collectorx），不是第三方。
- 装的是 main 分支最新版。
- 用户可能说「装最新版」「装一下」「用 FinClaw 技能中心装」——都是这个能力。
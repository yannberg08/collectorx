# FinClaw 投资分身修复方案（深度版）

> 目标代码：`~/Library/Application Support/FinClaw/avatar-core-tools/finclaw_avatar_core.py`（11841 行，蒸馏引擎）
> 与 `finclaw_avatar_server.py`（4492 行，采集/HTTP）
> 采集器：`~/Library/Application Support/FinClaw/hermes-home/collectorx/skills/filesystem-collector/…`
> 诊断结论：引擎骨架完整，但 (a) 采集边界会全量扫云盘超时；(b) 默认蒸馏是关键词路由器、LLM 理解层被 env 关掉且只吃摘要不吃正文；(c) 防注水的 reason 闸按"采集器身份"判定而非"内容作者"，被转发内容绕过；(d) 缺"用户产出的推理"数据源。

---

## 贯穿性架构判断（先看这一条）

整条链路是：
```
filesystem_query.py collect（真读正文，content_read）
  → sync 到 avatar-core lake（finclaw.lake.event.v1）
  → route_avatar()：确定性关键词路由 → 候选 leaf-signal + maturity_factor_assessment 打分
  → distill_avatar_with_finclaw_hermes()：env 开关，默认走 write_strict_fallback（纯规则）
  → organize_avatar() → wiki md
  → score_avatar() → scores.json
```

**最深的一个洞**：即使把 Hermes 打开，也产不出 SoulMirror 那种"具名框架"。因为 `distill_avatar_with_finclaw_hermes` 喂给 LLM 的 `review_items`（core.py:4977-5003）只含 `sample_event_summaries`（`event_brief` 生成的文件名+关键词摘要）+ `old_wiki_summary` + `leaf_rule`，**从不含文件正文**。正文在采集时被读了（filesystem-content），却在进入理解层前被降维成关键词。**所以"接通理解层"不是翻一个 env 开关，而是要把正文证据端到端送到 LLM 面前。** 这决定了工作项 2 的真实工作量。

---

## 工作项 1 · 修采集边界（工程，1~2 天）

### 根因（代码级）
1. **默认扫云盘**：`filesystem_collector/scanner.py:72-94` 默认根含
   `~/Library/Mobile Documents/com~apple~CloudDocs`（iCloud）、`~/Library/CloudStorage`、`~/OneDrive`。
   云占位文件 `stat` 会触发下载/网络调用，在真实机器上极慢。
2. **UI 全量扫描**：`server.refresh_filesystem_collector:943-962` 仅当 payload 带 `limit` 才加 `--limit`；
   页面"立即采集"不传 limit → 全量遍历 → 撞 `timeout=payload.timeout_seconds or 420`（:972）。
3. **采集本身无增量游标**：lake 导入层有 `subscription_event_cursors`（core.py:4558），但**文件扫描每次重走整棵树**，没有 mtime 水位线。
4. **UI 文案自相矛盾**：`#collectors` 详情页同时写"内置 driver 实地遍历…写入 Lake"和"增量导入·只处理已放入 Lake 的输出，不主动运行"（`host.js`/`app.js` 里的 `采集边界说明` + `增量导入` 文案块）。

### 修复
- **A. 云盘默认关**：在 `scanner.py` 的默认根构造里，把 iCloud/CloudStorage/OneDrive 从"默认扫"改成"默认跳过、显式 opt-in"。新增 `--include-cloud` flag（默认 false）；或在 scanner 里对这三类根做 `is_cloud_root()` 判定并默认加入 ignore。保留用户在 UI 勾选启用。
- **B. 给"立即采集"合理默认边界**：`refresh_filesystem_collector` 在 payload 无 limit 时注入保守默认（如首扫 `--limit 2000` + `--max-size-mb 20`）；把 `timeout` 默认从 420 提到可配置，并在超时返回里带"已扫 N/预计 M"进度（scanner 需周期性 flush 计数到一个 sidecar 文件，server 读它做进度）。
- **C. 增量游标**：scanner 落一个 `roots-cursor.json`（每个 root 的 `last_scan_mtime`），下次只 emit `mtime > 水位线` 的文件；首次全量、之后增量。这与 lake 层的 seq 游标是两层，缺一不可。
- **D. UI 文案二选一并统一**：filesystem 的语义定义清楚——它**是主动扫描（driver 遍历）**，不是被动导入。删掉"增量导入·不主动运行"那段误导文案，改成"首次全量扫描，之后按 mtime 增量；仅采元数据+按需正文，不出本机"。`email/notes` 才是"待配置/被动导入"，别和 filesystem 混用同一文案模板。

### 验收
- 在一台挂了 iCloud/OneDrive 的机器上点"立即采集"，30 秒内返回，不碰云占位文件。
- 连点两次，第二次 emit 的事件数 ≈ 期间改动的文件数（增量生效）。
- UI 详情页文案不再出现"实地遍历"与"不主动运行"并存。

---

## 工作项 2 · 接通蒸馏"理解层"（核心）

### 根因（代码级）
- 默认蒸馏是 `route_avatar()`（core.py:4530）——`targets_for(event, engine)` 走 `engine_route_tables` 关键词/kind 路由，`maturity_factor_assessment` 按证据数/多样性/时间跨度打分。**无语义理解**。
- LLM 路径 `distill_avatar_with_finclaw_hermes()`（core.py:4881）**默认关**：`use_hermes` 读 env `FINCLAW_AVATAR_USE_HERMES` / `FINCLAW_AVATAR_DISTILL_MODE`（:5009），没设就 `write_strict_fallback`（:5016-5017）。
- LLM 调用 `run_finclaw_hermes_json()`（core.py:2583）：shell 出 `hermes chat -q <prompt> --quiet --yolo --max-turns 20 --source finclaw-avatar-core`（:2588-2600），`timeout=FINCLAW_AVATAR_HERMES_TIMEOUT`（默认 120s），输出用 `extract_json_payload` 解析。二进制由 `finclaw_hermes_binary()`（:2531）在 `FINCLAW_HOME/bin/hermes` 等处找，必须存在+可执行+在 FINCLAW_HOME 下。
- prompt（:5023-5060）**本身写得很好**：已含硬规则 3"交易/持仓只能形成行为骨架，无笔记/复盘不得把风险观/买入框架推过初步"，输出严格 leaf_signal JSON。
- **致命限制**：`review_items`（:4977-5003）只喂 `sample_event_summaries` + `old_wiki_summary` + `leaf_rule`，**不含正文**；且只复核 `has_new_evidence` 的事件、上限 24 条（:4977 `[:24]`）。

### 修复（三步，缺一不可）
**2.1 打开开关 + 保证 Hermes 可达（半天）**
- 让 server 在跑蒸馏时注入 `FINCLAW_AVATAR_USE_HERMES=1`（或在引擎配置里加 `distill.mode: hermes`，`distill_avatar_with_finclaw_hermes` 读引擎而非仅读 env）。
- 校验 `finclaw_hermes_binary()` 能找到本机 Hermes（当前 gateway 进程 pid 36437 在跑，但那是 `python -m hermes_cli.main gateway run`，不一定等于 `FINCLAW_HOME/bin/hermes` 这个 chat 二进制）。先跑一次 `run_finclaw_hermes_json("返回 {\"ok\":true}")` 冒烟，确认 CLI 通、能回 JSON。
- 失败要显式暴露（现在失败静默回退到 fallback，用户根本不知道 LLM 没跑）——在 run 结果和 UI 里标注 `used_hermes: true/false` 和失败原因。

**2.2 把正文送进理解层（真正让 wiki 有价值的一步）**
- 现在 `event_brief`（core.py:4110）产生的是关键词摘要。要在 `review_items` 里为每条候选附上**受控长度的正文摘录**：从 filesystem-content 事件的 `data`（正文深读结果）取 N 段代表性原文（已脱敏、截断），作为 `evidence_excerpts`。
- 改 `distill_avatar_with_finclaw_hermes`：`review_items` 增加 `evidence_excerpts` 字段；prompt 增加"基于 evidence_excerpts 提炼**具名的、可复述的**事实陈述（如'用户的卖出纪律：跌破成本 8% 无条件止损'），而不是罗列文件名+关键词"。
- 提高批量与分组：现在 `[:24]` 一刀切；应按 leaf 分组、每 leaf 独立成一个 distill 请求（或小批），避免一个大 prompt 稀释每叶子的推理质量。

**2.3 确定性与可审计并存（别丢了 SoulMirror 的"Git 审计"优点）**
- LLM 输出必须过 `leaf_signal` schema 校验（已有 `normalize_leaf_signal_data`）+ reason 闸复核（工作项 3）——LLM 只能"在规则允许的上限内"给结论，不能越权升熟。
- 缓存：以 `fact_id`+证据 refs 的 hash 为键缓存 LLM 判断，正文没变不重算（省 token、保幂等）。
- 保留 `distill_mode` 标记（`rule_candidates_plus_investor_app_prompt` vs `..._strict_fallback`，:4926）让每个叶子可回溯是规则还是 LLM 产出。

### 验收
- 同一批"投资复盘笔记"，关掉 Hermes → wiki 是"命中 N 个关键词"；打开 → wiki 出现具名框架 + 原文依据 + 来源文件。二者肉眼可辨。
- 断网/Hermes 挂 → 优雅回退到规则层，UI 明确显示"LLM 未参与"。

---

## 工作项 3 · 证据分层硬闸（防注水）

### 根因（代码级，精确到行）
- `REASON_COLLECTORS`（core.py:108-122）把 `filesystem`、`FILESYSTEM_CONTENT_COLLECTOR`、`wechat`、`qq`、`doubao`、`feishu` 全算作"原因层采集器"。
- `bucket_has_reason_layer()`（:4316）= 该叶子证据里**只要有一条来自上述采集器**，就 `has_reason_layer=True`。
- 后果：`maturity_factor_assessment`（:4392）`explanation_depth` 直接给 85；`cap_maturity`/`maturity_cap_for_signal`（:4457/4471）的 reason 闸整段被跳过。
- 于是一篇你**收藏在 Documents 的公众号文章**（filesystem-content 读到）→ `has_reason_layer=True` → "买入决策框架"被顶到初步。**这是把"用户消费的信息"误判成"用户产出的推理"。**

### 修复：把 reason 闸从"采集器身份"改成"内容作者性(authorship)"
**3.1 给事件加 provenance 维度（数据契约层）**
- 在 `finclaw.lake.event.v1` 的 `data` 或顶层加字段 `authorship ∈ {authored_by_user, consumed_by_user, unknown}`：
  - `authored_by_user`：用户本人写的——交易复盘笔记、投资日记、群里**用户本人发的**消息、用户建的估值表。
  - `consumed_by_user`：用户接收/收藏的——转发文章、研报 PDF、公众号收藏、他人群消息。
- 采集器负责打这个标（工作项 4 一起做）。filesystem 无法判定的默认 `unknown`；但可用启发式：`source` 含 `mp.weixin.qq.com`/`type:URL`/下载目录 → `consumed`；用户笔记目录/含第一人称复盘结构 → 倾向 `authored`。

**3.2 reason 闸改判据**
- 新增 `bucket_has_authored_reason(bucket)`：只有当叶子证据里存在 `authorship == authored_by_user` 的条目才为真。
- `bucket_has_reason_layer` 保留但降级为"话题相关"，**不再单独解除 reason-required 叶子的上限**。
- `maturity_factor_assessment`：`explanation_depth=85` 的条件从 `has_reason_layer` 改成 `has_authored_reason`；`consumed_only` 的原因层叶子 explanation_depth 压到 ≤20。
- `cap_maturity`/`maturity_cap_for_signal`：`REASON_REQUIRED_LEAVES` 叶子若无 `authored_by_user` 证据，硬顶在"苗头"（消费内容可作线索，不能成框架）。
- **消费内容的正确去处**：路由上，`consumed` 内容只允许进 `inv-information-source`（信息源）、`inv-industry-circle`（能力圈广度）、`inv-information-learning-style`（学习风格），**禁止进** buy/sell-framework、cognitive-bias、emotion-pattern、market-view、risk-view。可在 `engine_route_tables` 增加 `authorship` 维度的准入过滤。

### 验收
- 重跑我诊断时那批数据：转发文章不再把"买入/卖出框架"推过苗头；它们改为落在"信息源/能力圈"，且标注 `consumed`。
- 一条真实的"止损复盘笔记"（authored）能正常把"卖出框架"推到初步/扎实。

---

## 工作项 4 · 补"原因层"数据源（有理解层后才喂得出具名框架）

### 设计原则
`REASON_REQUIRED_LEAVES`（core.py:124-137，共 13 个原因层叶子）只能由 `authored_by_user` 证据推熟。所以采集的重点不是"更多渠道"，而是"更多**用户产出的推理**"，且每条都带 `authorship` 标。

### 优先级（按"能突破 reason 闸"排序）
| 数据源 | 喂养叶子 | authorship | 采集方式 | 现状 |
|---|---|---|---|---|
| **交易复盘/投资日记**（备忘录/Obsidian/Notion 里"为什么买/卖/错"） | 决策日志、买入/卖出框架、复盘记录、规则库 | authored | notes 采集器 + 复盘结构识别 | notes 有，缺"投资复盘"识别与 authorship 标 |
| **投资群聊天里用户本人发言** | 咨询对象、情绪模式、信息源 | authored（仅本人消息） | wechat/qq 采集，按 sender==本人过滤 | wechat 有，缺 sender 作者性拆分 |
| **自建估值/持仓 Excel** | 分析能力、买入框架 | authored | filesystem-content 专项解析 | 扫得到文件，缺"用户自建模型"解析 |
| **微信读书/Kindle 投资书划线** | 市场观、风险观、价值偏好 | authored（划线=用户主动标注） | 新采集器 | ❌ 无 |
| **AI 对话里的投资提问**（Kimi/DeepSeek/本机豆包） | 认知偏差、能力圈边界（暴露盲区） | authored | doubao 有，扩其他 | 仅豆包 |
| **风险测评问卷结果** | 风险观 | authored（用户自评） | 券商/基金 App 导出 | ❌ 无 |
| 收藏文章/研报 PDF | 信息源、能力圈广度（**不进原因层**） | consumed | 已有 | 已有，但需改 authorship=consumed |

### 关键点：意图 vs 行动 vs 消费三分
- **行动**（成交/持仓）：强事实，但对原因层只是骨架。
- **意图**（定投计划、条件单、价格提醒、雪球模拟盘）：更接近"为什么"，且天然 authored。建议事件 `kind` 或 `data.evidence_role` 区分 `intent` / `action` / `consumed`。
- **负证据**（长期自选却从未买）：刻画能力圈边界。需采集时保证自选/浏览/成交的 symbol 可对齐。

### 采集器要交付的新契约
每个原因层采集器输出事件时必须：
1. 打 `authorship`（见工作项 3.1）。
2. 对原因层内容保留**可脱敏摘录的正文**（供工作项 2.2 的 `evidence_excerpts`），而不是只给元数据。
3. 标 `evidence_role ∈ {action, intent, reasoning, consumed}`。

---

## 依赖与推进顺序

```
工作项 1（采集边界）── 独立，先做，让 filesystem 能稳定产数据
        │
工作项 3（reason 闸改 authorship）── 数据契约先行：先定义 authorship 字段
        │                              （工作项 2 的 excerpts、工作项 4 的采集都依赖它）
        ▼
工作项 2（理解层）── 依赖 3 的 authorship + 4 的正文摘录；打开 Hermes + 送正文 + 分叶蒸馏
        │
工作项 4（原因层数据源）── 依赖 3 的 authorship 契约；有了 2 才喂得出具名框架
```

建议里程碑：
- **M1（能稳定采）**：工作项 1 全量 + 工作项 3.1 的 `authorship` 字段落地（先让 filesystem/notes 打标）。
- **M2（能真正理解）**：工作项 2.1+2.2（开 Hermes、送正文），先在 filesystem-content 上验证"具名框架"能产出。
- **M3（不再注水）**：工作项 3.2 全量闸门 + 工作项 2.3 审计缓存。
- **M4（画像立体）**：工作项 4 逐个补原因层源，优先复盘笔记与本人群发言。

## 验收总纲（一句话）
拿同一批真实数据，跑通后：**组合/执行维靠交易强事实到扎实；哲学/风格/行为维只有在有 authored 复盘/笔记时才升熟，且 wiki 里是"具名框架+原文依据"而非"命中关键词清单"；转发文章只进信息源/能力圈广度。** 这三条同时成立，投资分身才算真能上线。

---

## 执行进度（2026-07-15 · 直接改真实 FinClaw 代码）

改动落在两处（均非 collectorx git 仓库，改前已备份到 scratchpad；avatar-core 运行态用官方 `reset` 重建过）：
- `~/Library/Application Support/FinClaw/avatar-core-tools/finclaw_avatar_core.py` / `finclaw_avatar_server.py`
- `~/Library/Application Support/FinClaw/hermes-home/collectorx/skills/filesystem-collector/scripts/…`（scanner.py / filesystem_query.py）

### ✅ M1（能稳定采）— 已完成并验证
- **工作项 1A** 云盘默认关：`default_roots(include_cloud=False)` + 新增 `default_cloud_roots()`，iCloud/CloudStorage/OneDrive 改 opt-in（`--include-cloud`）。实测本机有 7 个 iCloud 快照目录，正是全量扫描超时元凶。
- **工作项 1B** 保守默认：server 注入 `FILESYSTEM_DEFAULT_LIMIT=2000` / `MAX_SIZE_MB=20` / `TIMEOUT=180`（均 env 可调）；超时信息更友好。
- **工作项 1C** 增量游标：scanner 落 `filesystem-roots-cursor.json`（每 root mtime 水位），`--cursor-file` / `--full-rescan`；no-op 不再误报 gap，server 层 no-op 返回 `ok:True`（"已是最新"）。实测第二次采集 0 新事件、游标跳过 2。
- **工作项 3.1** authorship 字段：新增 `authored_by_user/consumed_by_user/unknown` + `document_authorship()` 启发式（转发文章→consumed、复盘→authored、Downloads→consumed）+ `event_authorship()` 读取器（notes 默认 authored，email/wechat 保守 unknown 待 M4）；`LeafBucket` 捕获 authorship 并随信号 round-trip。

- **1B 扫描进度 sidecar**：scanner 每 500 文件 flush `filesystem-scan-progress.json`（`--progress-file`），server 用 `ThreadingHTTPServer` 并发暴露 `GET /api/local-collectors/filesystem/progress`，长扫描可显示"已扫 N/已出 M"。

### ✅ M2（能真正理解）— 已完成并验证
- **2.1** 理解层默认开：`distill` 判据改为 env > engine `distill.mode` > `llm_ready`（默认 True），开箱即用无需设环境变量；`used_hermes` 显式暴露。本机 Hermes 冒烟 20.9s 回合法 JSON。
- **2.2** 送正文 + **分叶蒸馏**：建 `content_index`（源事件 event_id→脱敏正文摘录 700 字 + authorship），`review_items` 增 `evidence_excerpts`/`authorship_mix`；prompt 增硬规则 6（提炼**具名可复述**事实）+ 规则 7（authorship 准入）；**改为按叶分组、每叶一个焦点 Hermes 请求**（`FINCLAW_AVATAR_DISTILL_MAX_LEAVES` 上限，默认 16），解决单批 LLM 逐轮波动。
- **2.3** 缓存：每叶按 `engine_prompt_version + 证据/摘录 hash` 键缓存决策（`spool/<avatar>/distill-cache.json`），证据未变复用、不重算。
- **旗舰验证**：authored 止损复盘 → 卖出框架 wiki 产出「(1)跌破成本8%无条件止损、拒绝加仓摊薄；(2)估值到合理上沿分批减仓（茅台减仓三分之一）」**具名框架**；run1 分叶 10 次 Hermes、run2 证据未变 0.4s 短路复用。

### ✅ M3（不再注水）— 已完成并验证
- **3.2** reason 闸改 authorship：新增 `bucket_has_authored_reason()`；`maturity_factor_assessment` explanation_depth 加成从 `has_reason_layer` 改 `has_authored_reason`；`cap_maturity`/`maturity_cap_for_signal` 对 13 个 `REASON_REQUIRED_LEAVES` 无 authored 证据硬顶「苗头」；distill 后**确定性硬重 cap**（不信任 LLM 自觉）；**路由层准入过滤**：`AUTHORSHIP_CONSUMED` 事件直接从 reason-required 叶子剔除（连苗头都进不去）。
- **验证**：只喂转发文章 → 原因层叶子全部 **0**（买/卖框架、风险观、认知偏差都进不去），消费内容只落信息源/能力圈广度/学习风格。

### ◑ M4（画像立体）— 代码可完成项已做完，数据源缺失项无法验证
拆成两类：**(a) 给现有采集器补 reason-layer 契约**（authorship + evidence_role + 正文 + 路由）——纯代码，已做；**(b) 为不存在的数据源建新采集器**——需真实数据，无法在本机验证。

- ✅ **notes 投资复盘（#1 优先级）— 已做并端到端验证**：`notes/events.py` 打 `authorship`（`_note_looks_consumed` 启发式）+ `evidence_role`；core.py `content_index` 兼容 `content_preview`；`targets_for` 对 note/message/email 用投资关键词经 `target_routes` 路由到投资叶子（含"不能把 wiki 目标当 leaf_id"的修正 + 排除 document_content 防翻倍）。**实测**：Obsidian 投资笔记 → 买入决策框架/投资规则库产出具名框架「三条件同时满足才买入：ROE连续5年>15% / 能理解商业模式 / 估值低于内在价值七折」；同库转发文章被挡在原因层外。
- ✅ **wechat 本人发言 — 代码已做**：`wechat_query.py` 按 `sender=='我'` 打 `authorship`（本人 authored / 收到 consumed）+ `evidence_role` + `content_preview`。**需真实解密微信数据验证**（本机 key/qq 限制，属 real-validation 边界）。
- ✅ **收藏文章/研报 → consumed**：filesystem-content + notes 均已按标记判 consumed。
- ✅ **evidence_role**：filesystem-content / notes / wechat 已标 `reasoning|consumed`。
- ❌ **微信读书/Kindle 划线、风险测评问卷**：本机无此数据源，属**新采集器**，需先有真实导出才能建+验证。
- ⚠️ **意图/行动三分（trade collectors 的 action/intent）**：eastmoney/ths 等交易采集器未改，需真实券商数据。

### ✅ 病根二·第三层（organize / wiki 结构）— 已修复
诊断补充：病根二不止"蒸馏是关键词路由器"，还有第三层——**organize 把具名事实套回"已形成的画像/依据/待补充/成熟度说明"四段后台报表模板**（`generated_wiki_block` 写死；引擎的 organize LLM prompt 从未被调用，且 prompt 本身也在强制这套结构）。前端只是忠实渲染，问题全在后端。
- `generated_wiki_block` 重写为 **SoulMirror 式知识文档**：正文=具名事实作为带来源的条目（`- 用户的买入决策框架：…（来源：我的买入原则.md）`），成熟度/证据只留 frontmatter，待补充降为一句轻提示。
- `fact_source_attribution` + distill 里用 `content_index` 给 evidence_refs 补真实文件名 → wiki 引用 SoulMirror 式`（来源：<文件>）`。
- 初始种子 `generic_wiki_template` 改用空 GENERATED 块、`cleanup_legacy_wiki_body` 清理遗留四段 → 新/重置 home 干净，无残留报表。
- **验证**：买入原则复盘 → `买入决策框架.md` 从"# 标题 + 四段报表"变成"# 标题 + 具名框架条目 + 来源文件"，与 SoulMirror `决策框架.md` 同构。真实分身已 reset 应用新种子（20 叶 0 残留四段）。

### 剩余
1. **M4(b)** 数据源缺失项（微信读书划线、风险测评、trade intent/action）——需用户提供真实导出后单独建采集器。
2. 把 scanner/query/notes/wechat 改动同步回 `~/collectorx` 源仓库（现只在 FinClaw hermes-home clone，避免分叉）。
3. 可选优化：首次全量蒸馏较慢（每叶~20s×叶数，notes 实测 9 叶 512s），可改后台异步 + 前端轮询进度端点；稳态因增量+缓存已很快。

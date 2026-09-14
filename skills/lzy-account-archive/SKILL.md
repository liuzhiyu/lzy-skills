---
name: lzy-account-archive
description: |
  账号存量归档：给一个抖音或小红书账号，抓最近 90 天全部视频/笔记（标题 + 正文全文 + 赞评转藏指标），
    存入本地持久仓库。之后再抓时自动增量——只抓没归档过的，存量不重抓，当天的不收（数据未定型）。
  当用户说「把这个账号抓下来」「存档这个账号」「抓一下最近的」「更新 XX 账号的数据」时使用。
  本技能是 LZY 自媒体方法论工具箱（/lzy）的方法之一。
---

# lzy-account-archive · 账号存量归档（90 天 + 增量）

给一个抖音 / 小红书账号，把作品存进本地持久仓库：首次抓 **90 天存量**，以后每次只抓**增量**。
数据是资产——仓库一旦建好，后续所有分析方法（拆解、漏斗、Eval）都从这里取数，不用反复爬。

## 参数处理 / help 协议

参数是 `help` / `用法` / `怎么用`，或没给账号：只输出以下说明后停止，不做任何抓取——

```
lzy-account-archive · 账号存量归档

用法：
  /lzy-account-archive <账号主页链接或名称> [平台]
    平台可省略：douyin.com 链接自动识别为抖音，xiaohongshu.com 链接为小红书；
    只给名字时你注明过平台就按注明，否则根据名字判断并跟用户确认一次。

首次抓某账号：90 天内全部作品（标题/全文/指标）入库。
再抓同一账号：只抓新增的（增量），存量不重抓；当天发布的不收（数据未定型）。

数据仓库：~/WorkBuddy/lzy-data/accounts/<平台>/<账号>/（不在技能目录里，不进 GitHub）
  posts.jsonl   全部作品（含指标历史，每次抓取若指标变了会留档）
  STATUS.md     摘要（总数/日期范围/点赞Top5/全部作品清单——每条标题都是可点击的原帖链接）
  raw/          抓取原始产物
```

## 数据仓库（先读这段再动手）

- 根目录：`$LZY_ARCHIVE_ROOT` 或默认 `~/WorkBuddy/lzy-data/accounts/`。**绝不能放技能目录里**（技能要发布 GitHub）。
- 每个账号一个目录 `<platform>/<account-slug>/`，slug 用账号名或 id。
- **唯一入库通道是 `scripts/archive.py`**——去重、跳过当天、指标历史都由它保证，不要手写 JSONL。

### 标准字段 schema

```
id / url / title / content(正文全文) / publish_date(YYYY-MM-DD) / platform
metrics: {likes, comments, shares, collects}
first_seen / last_seen / history: [{date, metrics}]   ← 指标每次变化自动留档
```

## 工作流

### 第 0 步 · 定位账号

- 抖音：`https://www.douyin.com/user/<sec_uid>`；小红书：`https://www.xiaohongshu.com/user/profile/<user_id>`
- 只给账号名：先在平台内搜索找到主页确认是同一个号（粉丝量/简介对得上），再继续。

### 第 1 步 · 建仓（已存在则跳过）

```bash
python3 scripts/archive.py init douyin <账号slug>
```

### 第 2 步 · 抓作品列表

```bash
bash scripts/grab_douyin_list.sh "<主页URL或sec_uid>" <仓库>/raw/
bash scripts/grab_xhs.sh list "<主页URL或user_id>" <仓库>/raw/
```

### 第 3 步 · 增量过滤（核心，每次都要做）

```bash
python3 scripts/archive.py pending douyin <账号slug> <仓库>/raw/list.json > <仓库>/raw/pending_ids.txt
```

- 空仓库 → pending = 全部（即首次存量抓取）；老仓库 → pending 只含新作品。
- **90 天线**：从列表判断发布时间无法做到（列表页无日期），首次抓取按 pending 全量抓详情后由日期字段裁剪；之后每次抓取天然是增量的。若单账号作品极多（>300 条），首次抓详情时分批：抓完 90 天线即可停（详情页有日期，见到 <90 天前的就停）。

### 第 4 步 · 逐条抓详情（标题/全文/日期/指标）

```bash
# 抖音（每条一个 json，文件名 = 视频id.json）
bash scripts/grab_douyin_detail.sh <video_id> <仓库>/raw/items/<video_id>.json
# 小红书
bash scripts/grab_xhs.sh note <note_id> <仓库>/raw/items/<note_id>.json
```

- 逐条循环跑（可让 AI 分批并行会话，参考 lzy-douyin-teardown 的 3 会话并行；实测 3 批次并行各 4 条，12 条 56 秒抓完）。
- 抖音详情**从渲染后的 DOM 提取**（`data-e2e` 锚点 + `document.title`），不再读 RENDER_DATA——见「踩坑」2026-09-14 条。除标准四指标外还会记 `publish_time`（含时分）与 `duration_ms`（作品时长，毫秒，与常见导出 CSV 同单位），供导出对齐全字段表用（archive.py merge 只收标准字段，这两个存在 raw/items 里）。
- **校准协议**：每个账号（或 DOM 改版后）先抓 1 条验证字段完整——content 是全文、publish_date 正确、四个指标非全 0。校准通过再批量；不通过先修提取 JS（见「踩坑」），把修好的 JS 记回本文件。

### 第 4.5 步 · 口播全文（可选，做文本分析时必做）

⚠️ **抖音有两种「文本」，别搞混**：

| 口径 | 来源 | 典型长度 | 用途 |
|---|---|---|---|
| **正文 / caption** | 详情页 DOM（第 4 步抓到的 content） | 50~150 字 | 只是视频简介 + 话题标签 |
| **口播全文** | 下载视频 → Whisper 转写 | 800~1600 字（约 5~6 字/秒） | 对标拆解、选题分析、脚本规律——**真正要的是这个** |

如果目标是「对标账号文本分析」，caption 远远不够（差 10 倍以上）。补口播全文：

```bash
# 1) 拿播放流直链（每条约 5~15s）
bsk navigate "https://www.douyin.com/video/<id>" --session <SID> ...
bsk evaluate --session <SID> "document.querySelector('video')?.currentSrc"   # 拿直链
# 2) curl 带 UA + Referer 下载 mp4
# 3) 本地转写（复用 lzy-video-to-text，不要另造轮子）
$HOME/.workbuddy/skills/video-to-text/.venv/bin/python \
  $HOME/.workbuddy/skills/video-to-text/scripts/transcribe.py \
  --input v_<id>.mp4 --output script_<id>.txt --language zh \
  --domain creator,business --glossary <赛道自定义词库>
```

- **必须带赛道自定义词库**（`--glossary`），否则账号名/人名全错。实测该账号不建词库时「艺丰」会被转成 易峰/一封/易风（老数据里就是这么错的）；建了词库后同音错写 0 残留。
- 转写稿直接作为 `content` 入库（`publish_time` / `duration_ms` / `caption` 一并留在 raw/items）。
- 耗时参考：turbo 模型，单条 150s 视频 ≈ 30 秒（下载 + 转写），2 批次并行 12 条 ≈ 2.5 分钟。
- **口径要统一**：如果老数据用的是口播稿，新数据也必须补口播稿，否则两批数据不可比。

### 第 5 步 · 入库

```bash
# 把 raw/items/*.json 合成一个数组文件后：
python3 scripts/archive.py merge douyin <账号slug> <items数组.json>
# merge 自动：去重 / 补缺字段 / 跳过当天和未来日期 / 指标变化留 history
```

### 第 6 步 · 汇报

```bash
python3 scripts/archive.py stats douyin <账号slug>
python3 scripts/archive.py report douyin <账号slug>
```

向用户报告：本次新增 N 条（日期范围）、跳过当天 M 条、总量 T 条、缺正文的条数（有缺口要主动说，不装完整）。

**导出成表格给用户**：STATUS.md 是索引，用户真正要的是**能直接接上他原有表格的 CSV**。列名、列序、编码必须和用户手上那份**逐列对齐**，否则他没法合并。本账号既有格式：`作品标题,作品链接,发布时间,获赞,评论,分享,收藏,作品时长,内容文案`，GBK 编码，`发布时间` 精确到分钟，`作品时长` 毫秒，`内容文案` 是口播全文。

**老数据的缺口要顺手补**：第一次归档时若发现历史条目缺正文/缺指标，用同一套转写流程补齐再入库（同一个仓库两批数据口径不一致，比缺几条更糟）。补完要在汇报里说明补了几条。

## 硬规则

1. **增量优先**：抓列表后必须先过 `pending`，已归档的绝不重抓详情。
2. **当天不收**：`publish_date` = 今天（北京时间）的一律不入库，merge 会自动跳过；明天再抓自然会收。
3. **merge 是唯一入库口**：手工改 posts.jsonl 禁止。
4. **每条结论可回溯**：详情原始 json 留在 `raw/items/`，仓库问题清单在 `raw/merge_problems_*.json`。
5. **不编数据**：抓不到的字段留空并统计上报，不填 0 冒充。

## 依赖

- bsk（BrowserSkill）：抖音、小红书各需登录一次。未登录时列表抓取会命中登录墙——提示用户人工过一次验证即可。
- python3（标准库即可，无第三方依赖）。

## 踩坑记录（当天回写）

- 2026-09-10 v1.0.0 建档。抖音列表抓取复用 lzy-douyin-teardown 已验证逻辑（滚动容器动态查找 + 懒加载收敛）；详情页优先读 `RENDER_DATA`（SSR 数据，比 DOM 稳），DOM 结构变了它大概率还能用。
- **2026-09-14 ⚠️ 旧详情提取方案已失效（已改）**：抖音视频详情页的 `RENDER_DATA` 现在**只剩壳数据**（`app.user` / `app.odin` / abTest 等），**不含 aweme detail**，按 `desc + create_time/statistics` 深搜必然 0 命中——12 条样本 100% "SSR 未命中"。已重写 `grab_douyin_detail.sh` 改为 DOM 提取，实测 12/12 成功。可用的 DOM 锚点（2026-09-14 实测）：

  | 字段 | 选择器 |
  |---|---|
  | 文案全文 | `[data-e2e="detail-video-info"]` 第一个子元素的 innerText（去掉开头「展开/收起」）；更稳的备选是 `document.title` 去掉尾部 ` - 抖音`（取两者较长的） |
  | 发布时间 | `[data-e2e="detail-video-publish-time"]` → 文本形如 `发布时间：2026-09-10 16:49` |
  | 点赞 | `[data-e2e="video-player-digg"]` |
  | 评论 | `[data-e2e="feed-comment-icon"]` |
  | 收藏 | `[data-e2e="video-player-collect"]` |
  | 分享 | `[data-e2e="video-player-share"]` |
  | 作品时长 | `document.querySelector('video').duration`（**秒**，×1000 = 毫秒，与导出 CSV 的「作品时长」同单位） |

  指标取到的是展示文本（可能是 `1.1万`），交给 archive.py 的 `norm_metrics` 归一化，别在脚本里强行 int。
- 2026-09-14 附带确认：`bsk session` 并行安全——3 个批次各 4 条同时跑，12 条 56 秒抓完，无互抢。列表抓取一轮 23 秒收敛（122 条）。
- 待实测：小红书未登录验证墙频率、粉丝极多账号的列表收敛轮数（本轮 122 条收敛于第 5 轮，属正常）。

## 迭代纪律

- 发现新规律 / 抓取 JS 失效当天改回本文件并升版本（小修 +0.0.1）。
- 被推翻的写法标记作废但不删（防止走回头路）。

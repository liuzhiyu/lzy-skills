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
  STATUS.md     摘要（总数/日期范围/点赞Top5/缺正文提醒）
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

- 逐条循环跑（可让 AI 分批并行会话，参考 lzy-douyin-teardown 的 3 会话并行）。
- **校准协议**：每个账号（或 DOM 改版后）先抓 1 条验证字段完整——content 是全文、publish_date 正确、四个指标非全 0。校准通过再批量；不通过先修提取 JS（见「踩坑」），把修好的 JS 记回本文件。

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
- 待实测：小红书未登录验证墙频率、抖音 RENDER_DATA 在视频详情页的字段路径、粉丝极多账号的列表收敛轮数。首次真实抓取后回来补记录。

## 迭代纪律

- 发现新规律 / 抓取 JS 失效当天改回本文件并升版本（小修 +0.0.1）。
- 被推翻的写法标记作废但不删（防止走回头路）。

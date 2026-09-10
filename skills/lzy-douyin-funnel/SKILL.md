---
name: lzy-douyin-funnel
description: |
  抖音搜索词「完整漏斗」分析：抓搜索结果 Top100 做内容生态 landscape（词频/分类/话题/母题/身份桶），
  再逐条进视频抓评论区，识别真实客户咨询与留资钩子（A1-A4/B/C 分类 + 四象限控制变量），
  最终合并为完整漏斗报告（HTML）。
  当用户说「分析抖音 XX 的评论区」「看有没有客户咨询」「分析 XX 搜索词」「做 XX 的完整漏斗」
  「XX 这个词抖音上什么内容能带来客资」时使用。
  全程 bsk CLI 抓取 + 本地 Python 分析，不编数据，结论必须带控制变量。
argument-hint: "<搜索词> [--mode landscape|comments|funnel]"
---

# lzy-douyin-funnel · 抖音搜索词完整漏斗分析

回答一个复合问题：**某个搜索词下的抖音视频，内容生态长什么样（landscape）＋ 评论区里到底有没有真实客户咨询、什么内容能带来咨询（leads）？**

> 本技能是 LZY 自媒体方法论工具箱（/lzy）的方法之一，与 /lzy-douyin-teardown 同属抖音系：
> teardown 拆「账号内爆款 vs 非爆款」，funnel 拆「搜索词下生态 + 客资」。所有脚本在 `scripts/` 目录，路径相对于本技能的 base directory。

## help 协议

**每次运行开头，先静默执行版本检查**：`bash scripts/check_update.sh`。如果输出 `UPDATE_AVAILABLE ...`，在回复开头告诉用户「此技能有新版本，可以让 AI 同步更新」。无输出则不打扰。

如果收到的参数是 `help` / `用法` / `怎么用`，或没有给搜索词，直接输出以下用法说明后停止，不执行任何抓取：

```
lzy-douyin-funnel · 抖音搜索词完整漏斗 · 用法

/lzy-douyin-funnel <搜索词> [--mode landscape|comments|funnel]
  例：/lzy-douyin-funnel 桥本 --mode funnel

--mode 三种模式（默认 funnel，即完整漏斗）：
  landscape  只做内容生态分析（快，几分钟）：词频/分类/话题/母题/身份桶
  comments   只做评论区客资分析（约 13-30 分钟/100 条）
  funnel     landscape + 客资分析 + 合并漏斗报告（推荐交付）

前提：bsk CLI（BrowserSkill）已装且登录抖音；首次运行先跑 python3 scripts/setup_env.py --install
产物：funnel_report.html（合并漏斗）+ landscape_report.html + leads.csv / comments_all.csv 等全套底稿
```

## 三种模式（按需选）

| 模式 | 触发 | 跑哪些脚本 |
|---|---|---|
| **A. landscape-only** | "分析 XX 搜索词""看看 XX 的内容生态" | fetch_list → landscape.py |
| **B. 评论区客资** | "分析 XX 评论区""有没有客户咨询" | fetch_list → grab_comments → analyze.py (+report_comments.py) |
| **C. 完整漏斗（推荐）** | "做 XX 的完整漏斗" | 以上全部 + report_funnel.py |

## 环境前置

- **bsk CLI**：BrowserSkill daemon 已启动（`bsk session start` 可用）。无法自动安装，缺失时提示用户。
- **Python（含 jieba）**：按以下顺序解析解释器（记为 `$PY`）：
  1. 环境变量 `$LZY_PY`（显式指定）
  2. 本技能自带 `.venv/bin/python`（跑过 `setup_env.py --install` 后存在）
  3. `~/.workbuddy/binaries/python/envs/default/bin/python`（作者机器的 WorkBuddy venv，jieba 已装）
  4. `python3`（需确认 jieba 可导入）
- **首次运行**：`python3 scripts/setup_env.py --install`（体检 + 把 jieba 装进技能自带 .venv，不污染全局；bsk 缺失时只提示）。
- **config 模块**：每个搜索词一份 `config_<词>.py`（见下「领域适配」）。通用兜底为 `config_base.py`。

## 完整漏斗 5 步

设工作目录 `WORK`（放 list.json / comments/ / 各类输出），`SK` 为本技能的 `scripts/` 目录（按上方规则解析 `$PY`）。

```bash
SK="<本技能目录>/scripts"
WORK=/path/to/your/work
CFG=config_qiaoben      # 或 config_base，或你新建的 config_<词>
```

**① 抓搜索结果列表**
```bash
SESS=$(bsk session start --no-focus 2>&1 | tail -1)
bash "$SK/fetch_list.sh" "桥本" "$SESS" "$WORK" 130
# 产出 $WORK/list.json（排名/标题/标签/点赞/时长/作者/发布时间）
```
> 若 fetch_list 抽不到卡片（时机/选择器问题），用 `bsk navigate` + `bsk evaluate` 手动滚动抽取：滚动 40 轮累计、取 `li div.search-result-card` 的 innerText 按行解析，存 `raw.json` 后 `python3 "$SK/parse_list.py" raw.json list.json`。

**② 生成待抓 ID 列表（取前 100）**
```bash
$PY -c "import json;d=json.load(open('$WORK/list.json',encoding='utf-8'));open('$WORK/ids.txt','w').write('\n'.join(x['id'] for x in d[:100]))"
```

**③ 逐条抓评论区（最耗时，约 13–30 分钟 / 100 条）**
```bash
# 推荐：3 个独立会话并行分片，提速 2–3×
split -l 34 -d "$WORK/ids.txt" /tmp/ids_
for i in 1 2 3; do
  S=$(bsk session start --no-focus 2>&1 | tail -1)
  bash "$SK/grab_comments.sh" "$S" /tmp/ids_0$((i-1)) "$WORK/comments" >/tmp/grab$i.log 2>&1 &
done
wait
```
> `grab_comments.sh` 幂等：已存在的非空 json 跳过，空文件自动重试一次。跑完检查：`find "$WORK/comments" -size 0 | wc -l`（应接近 0）。

**④ landscape（阶段一：搜索生态）**
```bash
$PY "$SK/landscape.py" "$CFG" "$WORK/list.json" "$WORK"
# 产出 $WORK/landscape_tables.md + $WORK/landscape_report.html
```

**⑤ 客资分析 + 报告 + 合并漏斗（阶段二）**
```bash
$PY "$SK/analyze.py" "$CFG" "$WORK" "桥本" 100
# 产出 leads.csv / comments_all.csv / report_data.md / comments_stats.json
$PY "$SK/report_comments.py" "$CFG" "$WORK" "桥本" 100   # 可选 standalone 客资 HTML
$PY "$SK/report_funnel.py"   "$CFG" "$WORK" "桥本" 100   # 合并漏斗 HTML（推荐交付）
```

## 领域适配（核心：引擎 + 每词 config）

所有领域差异都收敛到一个文件 —— **`config_<词>.py`**。引擎脚本（landscape.py / analyze.py / parse_comments.py / report_*.py）**永不改动**，只换 config。

**做法**：复制 `config_base.py` 为 `config_<词>.py`，改下列变量：

**评论侧（客资识别）**
- `A1_PAT` 强意向话术（问价/求方案/求检测/问机构/问产品…——按词改）
- `A2_PAT` 求方法/求资料、`B_PAT` 同行共鸣、`A3_PAT` 钩子动作、`C_PAT` 泛互动、`HOOK_WORDS` 留资暗号词
- `is_org(r)` 机构号判定、`CROSSES` 交叉分析维度（控制变量）、`CASE`+`quad_bucket(r)` 四象限分桶

**landscape 侧（内容生态）**
- `DOMAIN` 领域词（jieba 加词）、`STOP` 停用词、`CATS` 分类体系（A–L）、`TOPICS` 话题簇（正则）、`MOTHER`/`MOTHER_DESC` 母题、`AUTH_SELF` 权威标记、`IDENTITY_BUCKETS`+`IDENTITY_META` 身份桶

> 通用模式下（`config_base`）`CATS/TOPICS/MOTHER` 为空，landscape 只输出词频/标签/身份，跳过分类/话题/母题段落。要做带母题的 landscape 必须有领域 config。

## 分类体系（客资）

| 码 | 含义 | 判定 |
|---|---|---|
| **A1** | 强意向线索 | 问价 / 要联系方式 / 求服务 / 求合作 / 明确意向 |
| **A2** | 求方法求资料 | 「怎么弄」「发我一份」 |
| **A3** | 钩子留资 | 评论区暗号（同视频≥3 条相同短内容） |
| **A4** | **@AI 代写** | `@豆包/@元宝/@kimi` 等开头，需求流向 AI |
| **B** | 同行共鸣 | 「我也是干这行的」「说的就是我」 |
| **C** | 泛互动 | 夸赞/玩梗/打卡 |

线索率 =（A1 + A2 + A3）÷ 评论总数

### 两条必须做的校验（否则结论全错）
1. **@豆包 必须单独成类（A4）**。不算 `@豆包 帮我生成方案`，会被误判成客户咨询——那是对 AI 说话，不是对博主。
2. **自报身份要分叉**。「我是做 XX 的」= 同行共鸣(B)；只有叠加求助动词（帮我/怎么/多少钱）才升级为线索(A1/A2)。否则某行业博主的评论区会全被判成客户。

### 必须做控制变量（单变量是假相关）
案例型内容线索率「6.19×」看着很强，拆成**钩子 × 案例四象限**才发现：只讲案例不设钩子只有 6.5%，和什么都不做的 3.3% 几乎没差——真正起作用的是钩子。**每次都跑四象限**，不要只报单变量。

## 低评论诊断（关键，避免白抓）

抓取中位只有 5 条、最高 8 条时，**先别以为是 bug**。用 `diag.js` 在视频详情页诊断：
```bash
bsk navigate "https://www.douyin.com/video/<id>" --session "$SESS" --wait-until commit --timeout 20
bsk evaluate --session "$SESS" --timeout 30s "$(cat "$SK/diag.js")"
```
- 若返回 `hasMoreText: true`（"暂时没有更多评论""暂无评论"）——**评论就是这么少，真实情况**，不是脚本问题。
- 若 `before` 与 `after` 滚动后都为 0 且 `scFound: false` —— 才是真 bug（详情页没加载，可能卡验证码，用 `bsk request-help` 过验证后重开会话）。

## 提速：独立会话可并行（纠正旧版）

旧版写「不要并行」——**那指的是同一浏览器的多个 session 同时 navigate 会排队阻塞**。正确做法是：开**多个独立浏览器会话**（`bsk session start` 多个），各自抓不同 ID 分片。实测 3 会话分片抓 100 条约 13 分钟（单会话约 30 分钟）。

## 输出文件清单

```
$WORK/
├─ list.json              # 搜索结果（fetch_list → parse_list）
├─ ids.txt                # 前 100 视频 id
├─ comments/<id>.json     # 逐条视频评论区（grab_comment.js v2 抓取）
├─ landscape_tables.md    # 阶段一数据底稿
├─ landscape_report.html  # 阶段一可视化
├─ leads.csv             # 视频 × 咨询分类
├─ comments_all.csv      # 全部评论原文 + 标签
├─ report_data.md         # 阶段二数据底稿（结论需人工撰写）
├─ comments_stats.json    # 结构化统计（供 report 引擎）
├─ comments_report.html   # 阶段二客资可视化（可选）
└─ funnel_report.html     # 完整漏斗合并报告（推荐交付）
```

## 跨赛道规律（5 词实测基线，作对照参考）

| 维度 | 获客 | 美国留学 | 长寿医学 | 桥本 |
|---|---|---|---|---|
| 最强客资开关 | 钩子+框架 9.8× | 晒结果 4.07× | 生意/加盟 5.56× | 晒案例 2.95× |
| 留资钩子文化 | 工业化（9.8×） | ≈0 | ≈0 | **0/90 全真空** |
| @AI 截流占比 | 9.9% | 0% | 1.9% | 1.1% |

三条跨赛道规律：
1. **留资钩子是分赛道的，不是通用的**：获客把"扣1/私信"跑成工业化；留学/长寿/桥本几乎不设钩子——**谁先装机关，谁零竞争收割**。
2. **晒真实案例/结果是跨赛道最强通用开关**：留学晒 offer 4.07×、桥本晒案例 2.95×、长寿 1.26×；抽象干货反 0 转化。
3. **@AI 截流只盯"可总结"内容**：获客 9.9%（用户直接 @豆包 代写）最重；纯知识型会被 AI 平替，交付必须升级成"AI 做不了的执行/陪跑/私域"。

## 已验证 config

- **`config_qiaoben.py`（桥本）**：已用真实数据回归验证，产出与历史报告一致（A1 2.1%、钩子 0/90、晒案例 2.96×、指标/降抗体 2.55×、女性/备孕 0.51×、情绪归因 0.00×）。
- 其余 4 词（糖尿病/获客/美国留学/长寿医学）按其 landscape + 客资参数按同法提取成 config 即可复用本引擎。

## 踩坑记录

- shell 脚本原为 zsh（`${0:A:h}` 取目录），移植时已改为 bash 兼容写法（`$(cd "$(dirname "$0")" && pwd)`），bash/zsh/Git Bash 通用。
- jieba 优先装进技能自带 `.venv`（与其他 lzy 子技能的 setup_env 约定一致）；作者机器上也可直接复用 WorkBuddy 默认 venv。

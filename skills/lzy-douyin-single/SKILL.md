---
name: lzy-douyin-single
description: |
  抖音单条视频爆款归因：给一个抖音视频链接，下载视频 + 抓取指标（点赞/评论/收藏/转发，
  带抓取时间戳）+ 本地 Whisper 转写口播文案 + 抽帧 + 八维归因报告，可选一键传到腾讯文档
  供他人查看协作。当用户说「拆这条视频」「这条为什么爆」「分析这个抖音视频」「把这条视频
  传成在线文档」「这条爆款拆解发给别人看」时使用。
  Single Douyin video teardown: download + metrics snapshot (timestamped) + transcript +
  8-dimension virality attribution + optional export to Tencent Docs.
argument-hint: "<抖音视频链接或video_id> [--domain 词库] [--doc]"
---

# lzy-douyin-single · 抖音单条爆款归因

给一条抖音视频链接，产出一份「可发出去给别人看」的拆解：数据快照（**带抓取时刻**）+ 口播全文 +
八维归因 + 可迁移清单，可选直接落到腾讯文档。

> 本技能是 LZY 自媒体方法论工具箱（/lzy）的子技能。所有脚本在 `scripts/` 目录，
> 路径相对于本技能的 base directory。

**与兄弟技能的分工**（别用错）：

| 技能 | 输入 | 回答的问题 |
|---|---|---|
| **本技能 lzy-douyin-single** | 单条视频链接 | 这一条为什么爆？能不能抄？ |
| `/lzy-douyin-teardown` | 账号主页 | 同一个号里，爆款比普通条多了什么变量（带对照组） |
| `/lzy-douyin-funnel` | 搜索词 | 这个词下什么内容能带客资 |

## help 协议

**每次运行开头，先静默执行版本检查**：`bash scripts/check_update.sh`。如果输出 `UPDATE_AVAILABLE ...`，在回复开头告诉用户「此技能有新版本，可以让 AI 同步更新」。无输出则不打扰。

如果收到的参数是 `help` / `用法` / `怎么用`，或没有给视频链接，直接输出以下用法说明后停止：

```
lzy-douyin-single · 抖音单条爆款归因 · 用法

/lzy-douyin-single <抖音视频链接或video_id> [--domain 词库] [--doc]
  例：/lzy-douyin-single https://www.douyin.com/video/7675325276112407860 --domain shortvideo --doc

选项：
  --domain shortvideo|health|drug|business   转写词库（行业内容必加，否则术语全是错字）
  --doc                                      报告出完再传到腾讯文档，给可协作链接
  --outdir <目录>                            工作目录（默认 ./拆解_<video_id>）

流程：抓页面指标+下载视频 → 抽帧 → 转写 → 文本层指标 → 八维归因 → 报告（可选传云文档）
前提：本机已装 BrowserSkill(bsk) 并在浏览器里登录抖音；转写复用 lzy-video-to-text 的环境
产物：单条拆解_<video_id>.md + data.json + text_metrics.json + v_*.mp4 + frames_*/
```

## 工作流（6 步）

```
Step 1 抓取      →  bash scripts/grab_one.sh <链接> <工作目录>     # 指标+文案+下载+抽帧
Step 2 转写      →  python3 $HOME/.claude/skills/lzy-video-to-text/scripts/transcribe.py --input v_<ID>.mp4 --domain <词库>
Step 3 文本指标   →  python3 scripts/analyze_script.py --transcript script.txt --data data.json
Step 4 目视      →  主 Agent 逐帧 Read frames_*/a_01.jpg + 中段帧，看场景/字幕/POV
Step 5 出报告    →  python3 scripts/build_report.py --workdir <目录>  → 主 Agent 填八维归因
Step 6 云文档    →  --doc 时：把报告写成腾讯在线文档，给分享链接
```

### Step 1 · 抓取（一次 bsk session 干完所有事）

```bash
bash scripts/grab_one.sh "https://www.douyin.com/video/<id>" ./拆解_<id>
```

产出 `data.json`：

| 字段 | 说明 |
|---|---|
| `captured_at_human` | **抓取时刻（UTC+8）**——抖音数字是活的，报告里必须带 |
| `metrics` / `metrics_raw` | 赞/评/藏/转，同时留原始显示（"1.1万"）与归一化数值 |
| `derived` | 评赞比 / 藏赞比 / 转赞比 / 互动总量 / 日均赞（赞 ÷ 存续天数） |
| `content` | 视频自带文案（标题+正文+话题） |
| `top_comments` | 前排评论（最多 15 条，抓不到就是空） |
| `files` | 视频 mp4 与帧图目录绝对路径 |

- 数据全部从**渲染后 DOM** 读（`[data-e2e=...]` 锚点）。RENDER_DATA 方案已失效，别回退。
- 视频流读 `video.currentSrc`（比 network 嗅探稳），带签名有时效，拿到立刻 curl 下载。
- 抽帧：开场 2fps 抓 12 帧（看钩子），6 秒后 0.5fps 抓 10 帧（看结构）。
- 抓不到就降级不中断：字段留 `null`，**绝不编数**。退出码 3 = 抓不完整。
- 环境变量可覆盖：`BSK_BIN`、`FFMPEG_BIN`。

### Step 2 · 转写（复用 lzy-video-to-text）

```bash
python3 "$HOME/.claude/skills/lzy-video-to-text/scripts/transcribe.py" \
  --input ./拆解_<id>/v_<ID>.mp4 \
  --output ./拆解_<id>/script_<ID>.txt \
  --domain shortvideo --timestamps --language zh
```

- 视频已在本地，不用 `protected_site_capture.py`（那是给没下载的情况用的）。
- `--domain` 必加：短视频/获客 → `shortvideo`；健康营养 → `health`；临床用药 → `health,drug`；商业 ToB → `business`。
- `--timestamps` 必加：钩子窗口和结构分段都要靠时间戳切。
- 没装 lzy-video-to-text 时，先跑它的 `scripts/setup_env.py --install`（首次装 mlx-whisper 要 20+ 分钟）。

### Step 3 · 文本层指标

```bash
python3 scripts/analyze_script.py --transcript ./拆解_<id>/script_<ID>.txt --data ./拆解_<id>/data.json
```

输出 `text_metrics.json` + 控制台摘要。程序只做**可计数的部分**：

- 钩子窗口（前 3 秒，无时间戳则按前 25 字估算）里的信号：反常识/否定、身份标签、痛点、紧迫、好奇悬念、数字、结果承诺
- **钩子信号种类数** —— 单条拆解里最值得看的数：前 3 秒同时塞了几种信号
- 四段字数分布（开场/展开/论证/收尾）→ 看信息密度压在哪
- 语速、短句占比、口语连接词次数
- CTA / 互动引导 / 免责话术命中词

语义判断（这个钩子是不是真钩子、情绪到没到位）**不外包**，Step 5 主 Agent 自己读稿判。

### Step 4 · 逐帧目视（主 Agent 亲自做）

至少读 `a_01.jpg`（开场）、`a_04.jpg`（钩子后）、中段 `b_03.jpg`。看：场景、POV、人物、屏幕字幕、镜头切换、画面是不是这条的必要组成。

### Step 5 · 出报告

```bash
python3 scripts/build_report.py --workdir ./拆解_<id>
```

生成 `单条拆解_<video_id>.md`：一~六章是**已测数据**（脚本自动填），第七章「八维归因」和第八章「可迁移清单」是**占位**，必须由主 Agent 补。

### 第七章 · 八维归因框架

每一维必须写三件事：**证据（第几秒 / 第几句）→ 判读 → 验证程度**。

| 维度 | 判读要点 | 典型验证程度 |
|---|---|---|
| 选题与人群 | 替谁说话？痛点强度？大众母题还是窄众黑话？ | 🟡 |
| 钩子（前 3 秒） | 塞了几个信号？拦住人靠反常识、身份点名还是结果承诺？ | 🔴 |
| 结构节奏 | 四段字数分布说明什么？有没有废段？ | 🔴 |
| 表达与语感 | 口语还是书面？短句比例、语速、有没有「人味」 | 🔴 |
| 信任与身份 | 凭什么信他？身份标签/案例/信任反转/免责怎么配比 | 🟡 |
| 互动设计 | 评论区怎么被设计出来的？预判滑走、提问、三连击 | 🟡 |
| CTA / 留资 | 有没有把人带走的钩子？路径几步？ | 🔴 |
| 制作层 | 场景 / POV / 字幕 / BGM / 剪辑节奏（逐帧后填） | 🟡 |

### 验证程度标注（必须遵守）

- 🔴 **已量化验证**：有计数或帧佐证（如「钩子窗口 4 类信号」）。
- 🟡 **推断**：读稿/读帧的判断，没有对照组支撑。
- ⚠️ **待验证**：涉及因果、或需要对照组才能说的（单条拆解里**绝大多数因果结论属于这档**）。

**单条拆解的硬约束**：没有同账号普通条做对照，「因为它 X 所以它爆」这类话一律降级成「X 与爆款强相关」，并在报告第九章边界里写清楚。这是本技能最大的弱点，不许绕过去写。

### Step 6 · 云文档（`--doc`）

报告出完后，把 Markdown 落成**腾讯在线文档**并给可协作链接：

1. 用腾讯文档能力新建一篇文档，标题格式：`单条拆解 · <作者昵称> · <发布日期>`。
2. **按块写，不要整段塞 Markdown** —— 腾讯文档对 md 的兼容不完整，整段粘贴会丢表格。做法：标题/正文用块插入，表格用表格块重建，代码块内容用正文块。
3. 报告顶部的元信息区（来源、抓取时刻、发布、时长、口径）放在文档最前面，**抓取时刻必须保留**。
4. 权限设成「拿到链接可查看/可评论」，把链接给用户。
5. 本地 md 原文件保留，不删。

> 当前环境没有腾讯文档能力时（比如纯 Claude Code 环境），跳过本步，把本地 md 路径给用户，并说明「腾讯文档需要 AI 环境具备腾讯文档能力；没有的话手动粘贴即可」。

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `grab_one.sh` | 一次 session 抓指标+文案+评论，下载 mp4，抽帧 → `data.json` |
| `analyze_script.py` | 口播稿文本层指标（钩子信号/结构/语速/CTA）→ `text_metrics.json` |
| `build_report.py` | 拼报告骨架（已测数据自动填，归因留占位）→ `单条拆解_<id>.md` |
| `check_update.sh` | 版本检查（lzy 全工具箱统一主版本号） |

复用外部：`$HOME/.claude/skills/lzy-video-to-text/scripts/transcribe.py`（转写）。

## 踩坑记录

| 坑 | 解法 |
|---|---|
| RENDER_DATA 拿不到 aweme detail | 改读渲染后 DOM 的 `[data-e2e=...]`（继承自 lzy-account-archive） |
| 视频直链 403 / 下载中断 | 带浏览器 UA + Referer；直链带签名有时效，拿到立刻下，重试 3 次 |
| 没登录抖音 | currentSrc 与指标都拿不到 → 提示用户先在浏览器登录再跑 |
| 转写稿 `#` 元信息头进 md 变成一级标题 | build_report 会过滤 `#` 开头的行 |
| 行业术语全是错字 | 转写必加 `--domain`；词库没有的往 glossary 加一行 |
| 腾讯文档丢表格 | 按块写，表格单独用表格块重建，别整段粘 md |

## 报告规范

文件名 `单条拆解_<video_id>.md`，九章：数据快照 → 自带文案 → 口播全文 → 文本指标 → 前排评论 → 素材索引 → 八维归因 → 可迁移清单 → 边界与免责。

## 对用户回复规范

只说四件事：**抓到什么数据（带抓取时刻）、这条最可能的 2-3 个爆点、能抄的 1-2 条、报告/云文档链接**。
不罗列中间步骤，不把「推断」说成「结论」。

---

### 状态

- v0.1（2026-09-29）首版。脚本语法与报告管线已用构造数据跑通，**尚未用真实抖音链接端到端验证**。
  第一条真实链接跑完后，把新踩到的坑回写进「踩坑记录」，并删掉本状态段。

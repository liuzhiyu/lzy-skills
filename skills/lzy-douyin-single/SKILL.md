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
Step 6.5 放视频  →  mp4 转 GIF → upload_image → smartcanvas.edit 插到顶部（详见 Step 6.5）
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
  本机若已有别的 Whisper 环境（如 WorkBuddy 的 `~/.workbuddy/skills/video-to-text/.venv`），
  直接用它的 python 解释器跑 `transcribe.py` 即可，不必重装。

### Step 2.5 · 无口播视频：先判有没有人说话（2026-09-29 实战新增）

**转写稿极短（几十字）时，八成不是转写失败，是这条根本没人说话。**

判据：转写出的句子押韵/像歌词、字数远小于时长应有的量。这时**文本在屏幕字幕上**，处理办法：

1. 逐帧 Read 帧图，把字幕**手工拼成全文**，存成 `captions_<ID>.txt`（带 `[mm:ss]`，时间轴按帧序推算，注明 ±0.5s）。
2. `analyze_script.py` 的文本分析**改喂 captions 文件**，不要喂转写稿（喂了就是在分析 BGM 歌词）。
3. 报告里必须写明「本条无口播，转写为 BGM 歌词，文本分析基于目视字幕」。
4. BGM 歌词本身可能是有效证据——见第八维「制作层」：歌词与叙事同构时，是加分项。

> 实战案例：`7674561376723012905`（陈松文）全片 13.7 秒无口播，字幕打字机式呈现，BGM《孤勇者》。
> 这类「字幕型」内容在医生 IP 里不少，别按口播型套框架。

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

一次调用搞定，**不用按块写**（v0.1 写的「按块写」是错的，已实测更正）：

```bash
# 1) 取票据（本地网关，不走代理）
#    GET $connector-proxy/url + /internal/tencent-docs/tokens  → personal.token
# 2) POST https://docs.qq.com/openapi/mcp
#    method=tools/call, name=create_smartcanvas_by_mdx
#    arguments: { title(≤36字), mdx: <报告全文>, content_format: "markdown" }
```

- 走**智能文档（smartcanvas）**品类，不是 doc。`content_format=markdown` 必须显式传，默认按 MDX。
- 实测：本地 md 5503 字、27 行表格整段塞进去，**标题/表格/引用全部正常渲染，零丢失**。
- 返回 `url` 给用户时拼上 `?_fid=<file_id>`。
- 用 `get_content` 回读验证一次（检查字数、表格行数、抓取时刻是否都在）。

> 网络坑：腾讯文档 MCP 在本机有代理环境下，python 版 `tencentdocs.py` 可能报 `502 Bad Gateway`，
> 去掉代理又报 DNS 失败。**解法：用 curl 直接 POST（curl 直连和走代理都能通），票据从本地网关取。**
> 纯 Claude Code 环境没有腾讯文档能力时跳过本步，把本地 md 路径给用户。

### Step 6.5 · 把视频塞进文档（默认要做）

**腾讯文档不能上传 mp4**——工具表里只有 `upload_image`，没有 upload_video；`doc.insert_attachment` 是 DOC 品类专用，smartcanvas 用不了。
要让读者在文档里直接看到画面，唯一可行解是**转成 GIF 动图内嵌**：

```bash
# 1) 转 GIF：控制在 10MB 以内（upload_image 硬上限），实测参数 13.7s/576x1024 → 4.7MB
ffmpeg -y -i v_<id>.mp4 \
  -filter_complex "fps=8,scale=432:-1:flags=lanczos,split[a][b];\
[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
  -loop 0 preview_<id>.gif

# 2) 上传拿 image_id
#    tools/call  upload_image  { image_base64: <base64>, file_name: "preview.gif" }
#    注意：传实际 base64 内容，不要传路径；4.7MB 的 gif → 6.3MB base64，POST 超时给到 180s

# 3) 插到顶部：先 smartcanvas.find 定位顶块 id，再 INSERT_BEFORE
#    tools/call  smartcanvas.edit  { file_id, action: "INSERT_BEFORE", id: <顶块id>,
#                                    content: "<Image src='<image_id>' alt='原片动图预览 13.7秒' />" }
```

四个实测结论，别踩：

| 坑 | 结论 |
|---|---|
| `![](image_id)` markdown 语法 | ❌ **不生效**，字数不变，静默失败。必须用 MDX `<Image src='...' />` |
| image_id 只有一天有效期 | 别管它。插入后服务端**转存成永久地址** `docimg*.docs.qq.com/image/xxx.gif`，用 `smartcanvas.read` 能看到真实 URL |
| GIF 超 10MB | 第一版 576 宽 + 10fps + 64 色 = 10.3MB 超限；降到 432 宽 + 8fps + 48 色 = 4.7MB 通过 |
| GIF 无声 | 图片后面插一段说明，给抖音原链接，读者想看有声版能点过去 |

插完用 `smartcanvas.read` 确认出现 `<Image src="https://docimg..." />` 块，再用 `get_content` 确认表格行数没变（防止误伤正文）。

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
| 分享链是 `/friend?modal_id=<id>` 不是 `/video/<id>` | 从 URL 里同时匹配 `/video/(\d+)` 和 `modal_id=(\d+)`，统一转成 `/video/<id>` 打开 |
| navigate 后 7s 取不到 currentSrc，视频下载失败 | **改成轮询**（每 2s 一次，最多 24s）；实测 8-10s 才出现。拿到立刻下载 |
| 转写只有几十字、像歌词 | 这条**没有口播**，文本在屏幕字幕上 → 走 Step 2.5，逐帧目视拼字幕再分析 |
| 信号词典对字幕型内容命中率低 | 已补：人群点名（老乡/家人们）、权威头衔（副主任医师/医学博士）、CTA（找我/尽管找）、痛点（冤枉路/冤枉钱） |
| 「主任医师」被计成命中 | 是「副主任医师」的子串，计数会虚高 1，人工复核时扣掉 |
| 腾讯文档 MCP 报 502 或 DNS 失败 | 用 curl 直连 `docs.qq.com/openapi/mcp`，票据从本地网关 `/internal/tencent-docs/tokens` 取 |
| 以为腾讯文档要按块写才不丢表格 | 错。smartcanvas + `content_format=markdown` 整段写入，实测零丢失 |
| 想把 mp4 传进文档 | 传不了，腾讯文档没有 upload_video。**转 GIF**（≤10MB）再 `upload_image` 内嵌，见 Step 6.5 |
| `![](image_id)` 插入后没反应 | 静默失败。编辑接口只认 **MDX `<Image src='...' />`**，markdown 图片语法不生效 |

## 报告规范

文件名 `单条拆解_<video_id>.md`，九章：数据快照 → 自带文案 → 口播全文 → 文本指标 → 前排评论 → 素材索引 → 八维归因 → 可迁移清单 → 边界与免责。

## 对用户回复规范

只说四件事：**抓到什么数据（带抓取时刻）、这条最可能的 2-3 个爆点、能抄的 1-2 条、报告/云文档链接**。
不罗列中间步骤，不把「推断」说成「结论」。

---

### 状态

- **v0.2（2026-09-29）已用真实链接端到端验证**：`7674561376723012905`（陈松文 / 上海市第一人民医院心内科，
  13.7 秒无口播的字幕型视频，1.1万赞 / 1138 评 / 2141 藏）。全链路跑通：抓取 → 下载 → 抽帧 → 转写 →
  文本指标 → 八维归因 → 腾讯文档。首版踩的坑已全部回写进上表。
- v0.1 → v0.2 的修正：补 modal_id 链接兼容、视频流改轮询、新增 Step 2.5 无口播处理、信号词典补字幕型词、
  云文档改一次写入（原「按块写」是错的）。

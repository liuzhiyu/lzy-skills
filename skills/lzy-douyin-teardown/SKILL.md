---
name: lzy-douyin-teardown
description: |
  抖音爆款拆解对比：给一个抖音账号主页，自动完成「抓主页作品列表 → 按点赞选样
  （爆款/非爆款各取 N 条，N 由用户输入）→ 批量下载+抽帧+转写 → 18 元素（含扩展维度）
  对比分析 → 输出规律报告」。
  当用户说「拆解这个账号」「分析 XX 的爆款和非爆款差在哪」「拆爆款」「对标账号分析」
  「这个号凭什么爆」时使用。
  全程本地多模态（逐帧目视 + Whisper 转写 + CLAP 音频分类），每条结论标注验证程度，不编数据。
argument-hint: "<抖音主页链接> [爆款N] [对照N]"
---

# lzy-douyin-teardown · 抖音爆款拆解对比

给一个抖音主页，拆解对比「爆款 vs 非爆款」，按 18 元素（+扩展维度）输出规律报告。
核心价值：**不是看"爆款长什么样"，是看"爆款有而普通条没有的变量"** —— 必须带对照组，
否则全是幸存者偏差（这是 v1 踩过的最大的坑）。

> 本技能是 LZY 自媒体方法论工具箱（/lzy）的第一个方法。所有脚本在 `scripts/` 目录，
> 路径相对于本技能的 base directory。

## help 协议

**每次运行开头，先静默执行版本检查**：`bash scripts/check_update.sh`。如果输出 `UPDATE_AVAILABLE ...`，在回复开头告诉用户「此技能有新版本，可以让 AI 同步更新」。无输出则不打扰。

如果收到的参数是 `help` / `用法` / `怎么用`，或没有给主页链接，直接输出以下用法说明后停止，不执行任何抓取：

```
lzy-douyin-teardown · 抖音爆款拆解对比 · 用法

/lzy-douyin-teardown <抖音主页链接> [爆款N] [对照N]
  例：/lzy-douyin-teardown https://www.douyin.com/user/xxxx 10 10

可选参数：
  爆款N   爆款组取几条（默认 10，点赞 Top N）
  对照N   非爆款组取几条（默认 10，点赞末 N）

流程：依赖检测 → 抓主页列表 → 选样 → 批量下载+抽帧+转写 → 元素分析 → 规律报告
前提：需要本机已装 BrowserSkill(bsk) 并登录抖音；首次运行先跑 scripts/setup_env.py --install
产物：拆解对比_<账号名>_爆款vs非爆款.md + 全部视频素材（帧图/转写/数据json）
```

## 工作流总览（6 步）

```
Step 0 依赖检测   →  python3 scripts/setup_env.py --install
Step 1 确认参数   →  问用户：爆款取 N 条？非爆款取 N 条？（默认各 10）
Step 2 抓主页列表 →  bash scripts/grab_homepage.sh <主页URL> <工作目录>
Step 3 选样      →  python3 scripts/select_samples.py all_videos.json --viral N --control N
Step 4 批量抓取   →  bash scripts/batch_grab.sh <爆款ids...>  /  <对照ids...>
Step 5 元素分析   →  python3 scripts/analyze_elements.py + classify_bgm.py
Step 6 出报告     →  主 Agent 逐帧目视 + 转写全文 → 规律报告
```

### Step 0 · 依赖检测（首次运行必做）

```bash
python3 scripts/setup_env.py --install
```

- 检测四项：`bsk`(BrowserSkill) / `ffmpeg·ffprobe·curl` / `whisper 转写环境` / `CLAP 音频分类`。
- pip 包、brew 工具可自动装；**bsk 无法自动装**（需用户手动装 BrowserSkill 插件并登录抖音），检测到缺失时明确提示用户。
- 退出码 0=就绪，1=有缺。运行任何抓取前先跑一次。
- 转写环境复用 `$HOME/.workbuddy/skills/video-to-text/` 的 venv（可用 `V2T_VENV`/`V2T_TS` 环境变量覆盖）。

### Step 1 · 确认选样参数（问用户，别默认）

用 AskUserQuestion 问清楚：
1. **爆款组取几条**（默认 10）
2. **非爆款组取几条**（默认 10）
3. 对照组赞数区间（可选，默认不过滤，但建议 `--min-control 20` 避开 0 赞/异常）

样本量原则：**20 条（10+10）才能坐实文本层变量**；想验证「选题」这类需更大样本（50+）或跨账号。

### Step 2 · 抓主页作品列表

```bash
bash scripts/grab_homepage.sh "https://www.douyin.com/user/<sec_uid>" <工作目录>
```

- 自动滚动加载（抖音主页是虚拟滚动，**主容器是 `.parent-route-container`，必须 `scrollTop=99999 + dispatchEvent('scroll')` 才触发懒加载**，`window.scrollTo` 无效）。
- 输出 `all_videos.json`（id + 标题 + 点赞数），含点赞分布概览。

### Step 3 · 选样

```bash
python3 scripts/select_samples.py all_videos.json --viral 10 --control 10 --out 选样.txt
```

- 爆款组 = 点赞 Top N；对照组 = 点赞末 N（可选 `--min-control/--max-control` 约束区间）。
- 输出 `选样.txt`，两行：`# 爆款组` + ids、`# 对照组` + ids。

### Step 4 · 批量抓取（下载 + 抽帧 + 转写 + 可选 BGM）

```bash
# 环境变量可选：WORKDIR、DOMAIN（词库，默认 health）、DO_BGM=1（启用 BGM 识别）
bash scripts/batch_grab.sh <爆款ids...>
bash scripts/batch_grab.sh <对照ids...>
```

- 每条：开独立 bsk session → **读 `video.currentSrc` 拿播放流直链**（100% 命中，比 network 嗅探稳）→ curl 下载（带 UA + Referer）→ 分段抽帧（0-6s 每 0.5s 抓钩子；6s 后每 2s，540px）→ Whisper 转写。
- 产物：`v_<ID>.mp4`、`frames_<ID>/a_XX.jpg、b_XX.jpg`、`script_<ID>.txt`。
- `DO_BGM=1` 时抓完统一调 `classify_bgm.py` 批量识别 BGM，输出 `bgm.json`（模型一次加载处理全部，避免重复加载）。

### Step 5 · 元素分析（程序化部分）

```bash
python3 scripts/analyze_elements.py --workdir <目录> --viral <ids...> --control <ids...>
```

- 自动检测可程序化的文本层维度（返场/缘分/秘密/紧迫钩子、精确克数、配伍动作、体感词、医学词、互动话术、信任反转、免责话术、时长、字数）。
- 输出 `elements.json` + 爆款 vs 对照命中率对比表。
- **脚本只做可程序化的部分**，画面层（场景/镜头/POV/字幕）和语义判断（钩子信号密度、体感vs医学的细微差别）必须主 Agent 逐帧目视 + 读转写全文判断。

### Step 6 · 出报告（主 Agent 亲自做，不外包）

报告结构见下方「报告规范」。关键动作：
1. **逐帧 Read 图片**：至少看每条的开头帧（a_02）+ 中段帧（b_05）。要批量看就用 `ffmpeg -framerate 1 -i frames/%02d.jpg -vf tile=5x4` 拼 contact sheet，一眼看穿画面层是否恒定。
2. **转写全文读一遍**：钩子句式、体感/医学、数字配伍、互动话术、免责话术要对照原文找证据。
3. **标注验证程度**（见下），不得把"推断"写成"结论"。

## 18 元素框架（+ 扩展维度）

> 这是从文章作者的「18 元素」框架扩展而来。核心经验：**同一账号里，画面/制作层元素大部分恒定，拉不开爆款和普通条的差距；真正拉开差距的是文本层的少数几个元素。**

### 18 元素总表

| # | 元素 | 验证方式 | 同账号是否恒定 |
|---|---|---|---|
| 1 | 类型 | 文本/目视判断 | 通常恒定 |
| 2 | 品类 | 文本/目视判断 | 通常恒定 |
| 3 | 产品 | 文本判断 | 可能变 |
| 4 | 时长 | ffprobe 实测 | 变（可统计） |
| 5 | 选题 | 文本判断 | 变（⚠️ 待验证，混时间偏差） |
| 6 | 情绪基调 | 文本/目视 | 通常恒定 |
| 7 | POV | 逐帧目视 | 恒定 |
| 8 | 人物 | 逐帧目视 | 恒定 |
| 9 | 素材结构 | 逐帧目视 | 开头多变、中段恒定 |
| 10 | **Hook** | 逐帧 + 转写 | **变（胜负手）** |
| 11 | **文案** | 转写全文 | **变（胜负手）** |
| 12 | 屏幕字幕 | 逐帧目视 | 样式恒定、内容变 |
| 13 | 场景 | 逐帧目视 | **开头多变、中段恒定** |
| 14 | 视觉风格 | 逐帧目视 | 开头多变、中段恒定 |
| 15 | 镜头与卖点 | 逐帧目视 | 开头多变、中段恒定 |
| 16 | **CTA** | 转写 | **变（胜负手）** |
| 17 | BGM | CLAP 分类 | 通常恒定 |
| 18 | 人声 | 听感推断 | 通常恒定 |

### 扩展维度（跨视频对比验证出的真变量，比 18 元素更锋利）

这些是 20 条样本验证出的「爆款有、普通条没有」的变量，报告必须逐项对比：

| 扩展维度 | 爆款特征 | 对照组特征 |
|---|---|---|
| 钩子信号密度 | 前 4 句装 4 信号（症状+紧迫+处方预览+缘分） | 只有 1 个反常识信号 |
| 数字配伍 | 「克数×克数×动作」（白芍8克+木瓜8克煮水） | 「成本不到三块钱」价格单点 |
| 症状表达 | 体感词（疼到苦瓜脸/肌肉一抽一抽的） | 医学词（气血淤堵/舌头有齿痕） |
| 互动引擎 | 三段式：预判滑走→原谅→把互动定义成动力 | 直接乞讨（留下一朵小红花） |
| 信任反转 | 「方子不收费，爱上哪买上哪买」 | 只有「今天免费」 |
| 免责话术（反向） | 少（4/10） | 多（8/10）—— 免责越多越不爆 |

> ⚠️ 注意：**数字不是胜负手**（对照组也有数字），差异在「数字绑没绑动作」；「克数=收藏引擎」是 v1 被推翻的结论，勿再写。

## 验证程度标注规范（必须遵守）

每个结论必须标注它是**测出来的还是推出来的**，三档：

- 🔴 **已量化验证**：有 10 vs 10 计数或帧佐证（如缘分钩子 9:4、免责 4:8）。
- 🟡 **推断**：同账号该元素没变，所以「测不出作用」—— 不是"验证了没用"，是"这份数据里它没变，证明不了任何事"。
- ⚠️ **待验证**：混了时间偏差（高赞普遍发得早、累积期长），单账号拆不开。

报告里「真变量」「胜负手」这类词，准确说应是「**强相关因素**」（相关性 ≠ 因果）。「画面层恒定不影响爆款」是推断不是验证。

## BGM 识别（CLAP，已验证可用）

```bash
python3 scripts/classify_bgm.py --video v_<ID>.mp4 --video v_<ID2>.mp4 --json bgm.json --top 3
```

- 用 `laion/clap-htsat-unfused` 做零样本分类，标签池聚焦「音乐类型 + 有无伴奏」（见 `classify_bgm.py` 的 `CANDIDATES`），**勿用情绪形容词**（会分散置信度）。
- 实测置信度中等（40-50%），**作辅助元素，不作核心判断依据**；标签池可按赛道自定义。
- 依赖：transformers + torch + soundfile（`setup_env.py` 会装）；首次运行在线下载模型（约 300MB）。
- 已知坑：transformers 5.x 的 `get_text/audio_features` 返回 `BaseModelOutputWithPooling`，要取 `.pooler_output`；`processor` 参数是 `audio`（不是 `audios`）；torchaudio 2.11 默认后端是 torchcodec，读音频改用 soundfile。

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `setup_env.py` | 依赖检测 + 自动安装（`--install`） |
| `grab_homepage.sh` | 抓主页作品列表（滚动懒加载）→ all_videos.json |
| `select_samples.py` | 按点赞选样（爆款 N + 对照 N）→ 选样.txt |
| `batch_grab.sh` | 批量下载+抽帧+转写（+可选 BGM） |
| `analyze_elements.py` | 18 元素程序化提取 + 爆款/对照对比统计 |
| `classify_bgm.py` | CLAP BGM 识别（零样本分类） |

## 踩坑记录（2026-09-08 实测）

| 坑 | 解法 |
|---|---|
| `bsk network` 嗅探抓不到 douyinvod 直链 | 改读 `video.currentSrc`，100% 命中 |
| 同 session 内 SPA 路由切换后视频流不重新请求 | 每条视频开独立 session |
| douyinvod 直链带签名有时效 | navigate 后轮询 currentSrc（最多 20s），拿到立即下载 |
| curl 直链 403 / exit 56 | 带浏览器 UA + Referer 头；下载失败重试 3 次 |
| 主页滚动无效（window.scrollTo 不动） | 滚 `.parent-route-container` 容器：`scrollTop=99999 + dispatchEvent('scroll')` |
| 主页只加载 18 条 | 是虚拟滚动懒加载，滚动容器触发后能挖到几百条 |
| tesseract 对艺术字大字幕几乎不可用 | 字幕靠逐帧目视读 |
| Whisper 错字集中在药名/术语 | 转写加 `--domain health,drug`（按赛道选）；报告列勘误表 |
| 转写依赖（mlx-whisper）首次安装 20+ 分钟 | 首次运行时耐心等，装完秒起 |
| CLAP transformers 5.x API 变化 | 见上「BGM 识别」已知坑 |

## 报告规范

报告文件名用 `拆解对比_<账号名>_爆款vs非爆款.md`，结构：

```
一、样本说明（爆款 N 条平均赞 / 对照 N 条平均赞 / 差距倍数 / 选样口径）
二、账号基础信息（粉丝量、内容类型、挂载方式）
三、18 元素对比总表（每个元素标：恒定/变 + 验证程度🔴🟡⚠️）
四、扩展维度逐项对比（钩子密度/数字配伍/体感vs医学/互动/信任反转/免责反向）
五、反例与边界（低赞反例验证反直觉结论；样本边界：单账号、时间偏差）
六、素材索引（文件路径）
```

对用户回复规范：只讲「拆了几条、爆款/对照平均赞、最值钱的 3-5 条规律、报告路径」。不罗列中间步骤。

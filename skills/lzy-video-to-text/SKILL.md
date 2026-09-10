---
name: lzy-video-to-text
description: |
  把视频（URL 链接或本地文件）转写成纯文本稿，全程本地、免费、离线。
  当用户要「转写视频」「视频转文字」「提取口播文案」「视频内容录成文字」「把视频变成 txt」时使用。
  支持 YouTube / B站 / 网课 / 直接 mp4 链接，以及本地 mp4/mov/mkv 等文件。
  不依赖任何第三方付费服务（无需鲸剪/VIP），使用本机 Whisper 模型转写。
argument-hint: "<视频URL或本地路径> [--domain 词库] [--timestamps]"
---

# lzy-video-to-text · 视频转文字（本地免费版）

把视频/音频变成本地转写的纯文本稿。支持 Apple Silicon、Intel Mac、Linux、Windows；
不联网、不上传、不依赖任何付费服务。

> 本技能是 LZY 自媒体方法论工具箱（/lzy）的子技能，移植自 WorkBuddy 的 video-to-text skill（v2.1.0）。
> 所有脚本在 `scripts/` 目录，路径相对于本技能的 base directory。

## help 协议

**每次运行开头，先静默执行版本检查**：`bash scripts/check_update.sh`。如果输出 `UPDATE_AVAILABLE ...`，在回复开头告诉用户「此技能有新版本，可以让 AI 同步更新」。无输出则不打扰。

如果收到的参数是 `help` / `用法` / `怎么用`，或没有给视频链接/路径，直接输出以下用法说明后停止，不做任何转写：

```
lzy-video-to-text · 视频转文字 · 用法

/lzy-video-to-text <视频URL或本地路径> [选项]
  例：/lzy-video-to-text https://www.bilibili.com/video/BVxxxx --domain shortvideo
  例：/lzy-video-to-text ~/Desktop/口播.mp4 --timestamps
  （URL/路径也可以用 --input 传，两种写法等价）

常用选项：
  --domain shortvideo|health|drug|business   行业词库（行业内容必加，否则术语全是错字）
  --timestamps                               输出带 [mm:ss] 时间戳的分段稿
  --outdir <目录> --title <标题>             归档到指定目录，文件名自动加日期前缀
  --model turbo|large-v3|medium|small        转写模型档位（默认 turbo）

流程：首次使用先跑 python3 scripts/setup_env.py --install（装进本技能自带 .venv，不污染全局）
支持：YouTube / B站 / 网课 / 直链 mp4 / 本地 mp4·mov·mkv；抖音等需登录站点走 protected_site_capture.py
不适用：直播、微信视频号 App 内嵌、付费加密视频
```

## 何时使用

- 用户给了视频链接（YouTube / B站 / 网课 / 直链 mp4）或本地视频文件，想要文字稿
- 「把这条视频转成文字」「提取口播文案」「视频内容录下来变成 txt」

**不适用**：直播、微信视频号 App 内嵌、付费加密等无法拿到源文件的视频 → 本 Skill 无法处理。

## 首次使用：先跑环境自检（必做）

任何人、任何机器上装完本 skill，第一次使用前先跑一次体检与安装：

```bash
python3 scripts/setup_env.py            # 只体检，报告缺什么、给出安装命令
python3 scripts/setup_env.py --install  # 体检 + 自动安装缺失依赖
```

`--install` 会把 Python 依赖装进 **skill 自带的 `.venv`**，绝不污染用户的全局 Python 环境。
系统级依赖（ffmpeg）默认只打印安装命令，只有 macOS + 已装 Homebrew 时才自动 `brew install`。

退出码：`0` 全部就绪 / `1` 有缺失项 / `2` 安装失败。

需要机器可读结果时加 `--json`；只想要该用哪个解释器时加 `--print-python`。

## 标准工作流

### 1) 普通转写（URL 或本地文件）

```bash
python3 scripts/transcribe.py \
  --input "<视频URL或本地路径>" \
  --output "<输出txt路径>" \
  --language zh \
  --domain shortvideo       # 行业内容必加，否则术语全是错字
```

脚本会打印输出 txt 路径即成功。之后用 Read 读取校验，向用户报告路径与字数。

> 依赖装在 `.venv` 时无需手动指定解释器——`transcribe.py` 会自举切换到正确环境。
>
> 判断该加哪个词库：内容是短视频运营/获客 → `shortvideo`；健康营养医疗 → `health`；
> 商业/ToB/创业 → `business`；都不是 → 不加或加自己的词库。拿不准就问用户。

### 2) 存量稿回炉矫正（已抓完的稿子错字多）

手上已经有一批转写稿、术语错成一团时，用 `polish.py` 按词库回炉重修，不用重新转写：

```bash
# 单文件：输出 <原名>_polished.txt + 矫正报告，原稿不动
python3 scripts/polish.py --input 稿子.txt --domain drug --report

# 批量：整个目录下所有 txt/md
python3 scripts/polish.py --input 转写归档/ --domain health,drug --report

# 只体检不写文件，先看会改哪些词
python3 scripts/polish.py --input 稿子.txt --domain drug --dry-run

# 报告确认无误后覆盖原稿
python3 scripts/polish.py --input 稿子.txt --domain drug --inplace
```

红线：**只改错字，不改表达**。不删「啊/呢」，不把口语改成书面语，不动句式——
口播稿的语感比「通顺」更值钱。元信息区（`#` 注释、`- 来源：URL`、含 `→` 的校对提示行）跳过不动，
URL 用占位符挖出来保护，不会被词库替换误伤。

报告是 Markdown 表格，每处改动标注**命中方式**与**风险**：
「词库」= 显式映射，低风险；「拼音」= 同音推断，有误伤可能，改稿前过一眼。

### 3) 归档到指定目录（带时间戳）

```bash
python3 scripts/transcribe.py \
  --input "<视频URL或本地路径>" \
  --outdir "./转写归档" \
  --title "这期视频的主题" \
  --timestamps --language zh
```

产物：`./转写归档/20260904_这期视频的主题_script.txt`，含 来源/日期/模型 元信息头 + `[mm:ss]` 分段正文。
未指定 `--outdir` 时落到默认目录 `./transcripts`（可用环境变量 `VIDEO_TO_TEXT_OUTDIR` 覆盖）。

### 4) 受登录保护的站点（抖音等）

抖音等站点的详情接口强制登录，`yt-dlp` 直连会被 403 挡下。改用浏览器抓取真实播放流：

```bash
python3 scripts/protected_site_capture.py \
  --input "https://www.douyin.com/video/7675325276112407860" \
  --title "布洛芬用药警示" --outdir "./转写归档" --language zh
```

原理：`bsk` 打开本机**已登录**的浏览器 → 抓 network 里的 CDN 播放流直链 → 下载 mp4 → 本地转写 → 关闭 session。

- 依赖 `bsk` CLI（来自 **BrowserSkill** 技能）。未安装时脚本会直接给出安装指引并退出，不会抛裸 traceback。
- 未登录该站点时抓不到直链 → 提示用户先登录再重跑。
- 新增站点（如视频号）时在脚本的 `STREAM_PATTERNS` 里补 CDN 域名特征即可。
- 抖音 CDN 直链带签名且有时效，脚本抓到后立即下载。

### 5) 批量收件箱（可选，适合挂定时任务）

```bash
python3 scripts/watch_transcribe.py --init    # 创建目录结构并打印路径
python3 scripts/watch_transcribe.py           # 转写收件箱里所有视频，原文件自动归档
```

目录可用环境变量覆盖：`VIDEO_TO_TEXT_INBOX` / `VIDEO_TO_TEXT_ARCHIVE` / `VIDEO_TO_TEXT_OUTDIR`。

## 参数速查（transcribe.py）

| 参数 | 必填 | 说明 |
|------|------|------|
| `--input`（或位置参数） | 是 | 视频 URL 或本地音视频文件路径；两种写法等价，位置参数直接跟在命令后即可 |
| `--output` | 否 | 输出 txt 路径；不指定则归档到默认目录 |
| `--model` | 否 | 档位：`turbo`(默认) / `large-v3` / `medium` / `small` / `base` / `tiny`，也可传完整 HF 仓库名 |
| `--language` | 否 | 语言代码，默认 `zh`；留空自动检测 |
| `--timestamps` | 否 | 输出带 `[mm:ss]` 时间戳的分段稿 |
| `--outdir` | 否 | 归档目录，文件名自动加日期前缀 |
| `--title` | 否 | 归档文件名标题 |
| `--backend` | 否 | 强制指定后端：`mlx-whisper` / `faster-whisper` / `openai-whisper` |
| `--cookies-from-browser` | 否 | 需登录的站点：`chrome` / `safari` / `firefox` / `edge` |
| `--proxy` | 否 | 代理地址（如 `http://127.0.0.1:7890`）；传 `''` 绕过系统代理，内网地址常需要 |
| `--domain` | 否 | 行业词库：`shortvideo` / `health` / `business`，矫正行业术语错字 |
| `--glossary` | 否 | 自定义词库文件路径，可与 `--domain` 叠加，自定义优先 |
| `--no-glossary` | 否 | 关闭词库与纠错，纯裸跑 Whisper |
| `--no-correct` | 否 | 只注入热词提示，不做转写后的替换纠错 |
| `--no-pinyin` | 否 | 关闭同音字兜底（默认开；能纠出词库没列过的错写，如 起威→企微） |
| `--prompt` | 否 | 额外注入热词提示（默认关，理由见「错字矫正」章节） |

## 错字矫正：两层机制

Whisper 在中文上的错字 **90% 集中在专有名词**——普通口语它识别得很准，
但「完播率」「企微」「私域」这类行业词没有语言先验，会被写成同音的日常词。
所以本 skill 用两层来治，**建议凡是行业内容都加 `--domain`**：

```
裸跑   短视频或客 / 玩播率 / 岂微流资 / 思域承接
加词库 短视频获客 / 完播率 / 企微留资 / 私域承接
```

| 层 | 机制 | 默认 | 说明 |
|---|---|---|---|
| 第二层 | 按词库显式映射替换 | **开** | 词库里列过的错写，确定性强 |
| 第三层 | 同音字兜底（`pypinyin`） | **开** | 读音相同即判为错写，**不用穷举**；缺 `pypinyin` 自动跳过 |
| 第四层 | 通用文字/排版清理 | **开** | 见下，与行业无关 |
| 第一层 | 注入 `initial_prompt` 热词提示 | 关（`--prompt` 开启） | 见下方说明 |

第四层做三件与行业无关的清理，都是中文 ASR 的通病：

- 补语标志「得」被写成「的」：`吃的不多` → `吃得不多`
- 半角标点转全角：`我们,今天` → `我们，今天`（只在紧邻中文时转，URL / `3.5` / `Python(3.9)` 不受影响）
- 清理热词注入残留的多余空格与乱码字符

「得」这条只改「动词 + 的 + 补语标志」一种结构，动词表剔除了「有/是/在/和」等有歧义的字。
实测 10 条助词反例（`我的手机`、`短视频的底层逻辑`、`做的人很少`）零误伤。

实测（短视频口播 23 秒 / 大健康口播 28 秒）：

```
短视频  裸跑 玩播率 / 起威 / 流资 / 私欲承接  →  默认 全部修正
大健康  裸跑 皮质纯 / 线立体 / 清断食        →  默认 全部修正
```

「起威」词库里**没列过**，是第三层按拼音（qiwei）纠正的——同音字组合穷举不完。

### 为什么热词提示默认关闭

这是实测得出的反直觉结论。注入提示词会**改变模型解码**，副作用实测到两类：

- **标点污染**：prompt 超过 ~40 字（58 token）就开始把逗号输出成全角 `Ｚ` 或乱码
- **重复幻觉**：大健康样本里把「可以试试轻断食」输出成「可以是是轻断食」

而同一批样本上，**只做后两层纠错就已经 100% 修正了全部术语**，且没有副作用。
所以默认走更可控的路径，把提示词降级为可选项。

什么时候加 `--prompt`：词库很小、或纠错后仍有术语错得离谱（音素层面就错了，
拼音也匹配不上）时试一下；发现标点异常或重复字就去掉。

**必须按行业矫正**——通用模型没有行业语境，用通用词库等于没用。内置四套：

| `--domain` | 适用 | 词量 |
|---|---|---|
| `shortvideo` | 短视频运营 / 获客：完播率、企微、私域、留资、客资、千川、ROI… | 69 术语 / 126 纠错 |
| `health` | 功能医学 / 营养 / 抗衰：胰岛素抵抗、肠道菌群、皮质醇、轻断食、NAD+… | 见文件 |
| `drug` | 临床用药 / 药品：布洛芬、对乙酰氨基酚、阿司匹林、非甾体抗炎药、二甲双胍… | 见文件 |
| `business` | 商业 / ToB：毛利、现金流、续费率、护城河、LTV、SOP… | 见文件 |

### 光按「行业」还不够，要按「子领域」

踩过的坑：一条讲布洛芬用药禁忌的医疗科普，挂 `health` 词表跑，**4 个错词一个都没纠上**——
`解热症痛药` / `对乙鲜胺基分缓湿片` / `非载体抗炎药` / `RCP0`，全是临床用药词，
而 `health` 表是功能医学 / 营养 / 抗衰向的，一个药名都没有。

所以词表按子领域拆细，用时按需叠加：

```bash
# 既讲营养又讲药（糖尿病用药科普、慢病管理这类最常见）
--domain health,drug
```

**词表不是越大越好。** `initial_prompt` 只有 40 字预算，只放得下 5-6 个术语。
把「营养抗衰」和「临床用药」塞进一张表，本篇真正会出现的药名就挤不进提示，等于白注入。
拆成子领域后按需叠加，热词提示的精度才上得去。

### 同音字兜底救不了的两类错

第三层（拼音）只对「**读音完全相同、字形不同**」有效：

- ✅ 能救：`胰岛素抵炕` → 胰岛素抵抗、`皮质纯` → 皮质醇、`起威` → 企微
- ❌ 救不了：**漏字/多字**（`胰岛低抗` 少了「素」，读音长度都不一样）→ 只能显式写进词库
- ❌ 救不了：**符号级错写**（`RCP0` → 阿司匹林，根本不是中文）→ 只能显式写进词库

遇到这两类，往 `glossary/*.txt` 加一行 `正确词 = 转写出来的错词` 即可，越用越准。

### 建自己的词库

行业黑话、人名、品牌名、地名这些内置词库没有的，建一个自己的文件：

```txt
# 我的词库：格式  正确写法 = 误识别1, 误识别2
智宇师兄 = 志宇师兄, 智宇师付
广誉远 = 广玉远, 广誉园
CPM医生 = CPM一生, CPM医师
刘鸣岐 = 刘鸣奇, 刘明岐
```

```bash
python3 scripts/transcribe.py --input 视频 --domain shortvideo --glossary ~/myglossary.txt
```

- 等号左边进热词提示，右边用于转写后替换。不容易错的词直接写裸词（不加等号）。
- 每次转写完看日志里的「纠错 N 类」，发现新错字就往词库里加一行，越用越准。
- 想让它成为默认：`export VIDEO_TO_TEXT_DOMAIN=shortvideo`、
  `export VIDEO_TO_TEXT_GLOSSARY=~/myglossary.txt`。

参考格式见 `glossary/*.txt`。

## 后端自动选择

| 平台 | 后端 | 说明 |
|------|------|------|
| Apple Silicon (M 系列) | `mlx-whisper` | Neural Engine 加速，最快 |
| Intel Mac / Linux / Windows | `faster-whisper` | CPU int8；检测到 N 卡自动走 CUDA |
| 兜底 | `openai-whisper` | 最通用但最慢 |

模型档位是**跨后端统一**的，同一条命令在任何平台都能跑；脚本会按后端映射到对应模型仓库，
仓库名失效时自动尝试备选（社区仓库常有改名/下架）。

## 故障速查

| 症状 | 处理 |
|------|------|
| **新电脑首次使用没出转录稿** | 九成是环境没装。跑 `python3 scripts/setup_env.py --install`（装进技能自带 .venv）后重跑；缺环境时报错会直接给出这条命令 |
| 转写成功但找不到稿子 | 脚本最后一行打印的就是输出 txt 的**绝对路径**；未指定 `--output/--outdir` 时落在**当时所在目录**的 `./transcripts/` 下 |
| 报缺依赖 | `python3 scripts/setup_env.py --install` |
| 模型下载超时 / 502 / 403 | `export HF_ENDPOINT=https://hf-mirror.com` 后重跑 |
| pip 装包慢 | `export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` |
| B站等要登录才能下最高清 | 加 `--cookies-from-browser chrome` |
| 抖音/视频号 403 | 改用 `protected_site_capture.py`（见上） |
| 链接下载报 502 / 连不上 | 公司网络或内网地址常是代理问题，加 `--proxy ''` 绕过，或 `--proxy http://...` |
| 报「该视频没有音轨」 | 视频本身无声（纯画面录屏），没有可转写内容 |
| CPU 上转写太慢 | 换小模型：`--model small` 或 `--model base` |
| 行业术语全是错字 | 加 `--domain`（见「错字矫正」章节）；内置库没有的用 `--glossary` 自建 |
| `--domain` 报未知领域 | 只认 `shortvideo` / `health` / `business`，其它用 `--glossary` 自己的文件 |
| 转写结果字间有多余空格 | 已自动清理；若还有，检查是否用了 `--no-glossary` |
| 加了词库术语仍错 | 该错写不在词库里 → 往词库加一行 `正确词 = 转写出来的错词` 后重跑 |

详细的各平台安装命令、离线部署、错误码见 `references/INSTALL.md`。

## 对用户回复规范

只说明：**是否成功、输出 txt 路径、大致字数、失败原因与可执行建议**（换源 / 装依赖 / 检查网络）。
不展开技术细节，不罗列中间步骤。

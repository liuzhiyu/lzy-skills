# lzy-skills · LZY 自媒体方法论工具箱

刘志宇的自媒体分析方法技能集，运行在 [Claude Code](https://claude.com/claude-code) 的 skill 体系上（`~/.claude/skills/`）。

## 技能清单

| 技能 | 说明 |
|---|---|
| `lzy` | 工具箱主入口（路由 + help + 新增方法规范） |
| `lzy-douyin-teardown` | 抖音爆款拆解对比：爆款 vs 非爆款对照组，18 元素 + 扩展维度，输出规律报告 |
| `lzy-douyin-funnel` | 抖音搜索词完整漏斗：Top100 内容生态 landscape + 评论区客资识别，合并 HTML 报告 |
| `lzy-video-to-text` | 视频转文字：URL/本地文件 → TXT，本地 Whisper，行业词库纠错，免费离线 |

## 方法详解

### 1️⃣ lzy-douyin-teardown · 抖音爆款拆解对比

给一个抖音账号主页，自动拆解「爆款 vs 非爆款」到底差在哪。核心方法论是**对照组思维**：不是看"爆款长什么样"，而是找"爆款有而普通条没有的变量"——没有对照组的拆解全是幸存者偏差。

**它自动做的事**：抓主页作品列表 → 按点赞选样（爆款 Top N / 非爆款末 N）→ 批量下载视频 + 抽帧 + Whisper 转写 + CLAP 音频分类 → 按 18 元素（含扩展维度）逐条对比 → 输出规律报告。

**用法**：

```
/lzy-douyin-teardown <抖音主页链接> [爆款N] [对照N]
例：/lzy-douyin-teardown https://www.douyin.com/user/xxxx 10 10
```

**产出**：`拆解对比_<账号名>_爆款vs非爆款.md` 规律报告 + 全部视频素材（帧图/转写稿/数据 json）。每条结论标注验证程度（🔴实锤 / 🟡疑似 / ⚠️推测），不编数据。

**前提**：本机已装 BrowserSkill(bsk) 并登录抖音；首次运行会自动跑 `scripts/setup_env.py --install` 体检并装齐 ffmpeg/whisper/CLAP。

### 2️⃣ lzy-douyin-funnel · 抖音搜索词完整漏斗分析

回答一个复合问题：**某个搜索词下的抖音视频，内容生态长什么样 + 评论区里到底有没有真实客户咨询、什么内容能带来咨询？**

**三种模式**：
- `--mode landscape`：只做内容生态分析（词频/分类/话题/母题/身份桶），几分钟出结果
- `--mode comments`：只做评论区客资分析（A1 强意向 / A2 求方法 / A3 钩子留资 / A4 @AI 代写 / B 同行 / C 泛互动）
- `--mode funnel`：完整漏斗 = 生态 + 客资 + 合并 HTML 报告（推荐交付）

**它自动做的事**：bsk 抓搜索结果 Top100 → landscape 分词统计 → 逐条进视频抓评论区（3 会话并行，100 条约 13 分钟）→ jieba 分词 + 规则分类 + **钩子×案例四象限控制变量**（单变量是假相关）→ 合并漏斗报告。领域差异全部收敛到 `config_<词>.py` 一个文件，引擎脚本永不改动。

**用法**：

```
/lzy-douyin-funnel <搜索词> [--mode landscape|comments|funnel]
例：/lzy-douyin-funnel 桥本 --mode funnel
```

**产出**：`funnel_report.html`（合并漏斗）+ `landscape_report.html` + `leads.csv` / `comments_all.csv` 全套底稿。方法论沉淀了 5 个搜索词的跨赛道实测基线（留资钩子分赛道、晒真实案例是最强通用开关、@AI 截流规律）。

**前提**：bsk CLI（BrowserSkill，需登录抖音）；首次运行 `python3 scripts/setup_env.py --install` 自动装 jieba（进技能自带 .venv）。

### 3️⃣ lzy-script-coach · 智宇师兄大号口播文案校正

贴一段口播文案，AI 按真实数据规律做校正审核。**不是通用短视频常识，是 2026/7–9 共 23 条真实发布视频回归出来的规律**，且持续回写迭代（被推翻的结论标记作废保留，防止走回头路）。

**校正流程**：
1. **主题闸门**（两层）：闸门一否决跑题方向（影视/行业观察/个人感悟，实测只有流量幻觉）；闸门二强制改写「模型/清单/通用道理」型内容
2. **七项体检打分**（第 1 项翻倍）：开场切入、「我」的位置、诊断型动作、重新定义问题、反清单体、单点聚焦、嘴替——外加爹味自检、开头钩子三选一、同轴检查、案例铁律
3. **最小改动改写**：保留用户判断和原话，只调结构与开场；改写稿干净可直接拿去拍
4. 附「自嗨急救」：写嗨了怎么用写前锚定 + 三步转换拉回框架

**用法**：

```
/lzy-script-coach <口播文案（粘贴全文或文件路径）>
```

**适用范围**：仅大号「智宇师兄」（服务老板/ToB，目标拿客户）；小号超短句打法不适用。
**环境依赖**：零。纯方法论技能，装完即用。

### 4️⃣ lzy-video-to-text · 视频转文字（本地免费版）

把视频（URL 或本地文件）转写成纯文本稿。**全程本地、免费、离线**——不依赖任何第三方付费服务（无需鲸剪/VIP），用本机 Whisper 模型转写。

**支持**：YouTube / B站 / 网课 / 直链 mp4 / 本地 mp4·mov·mkv 等。
**不支持**：直播、微信视频号 App 内嵌、付费加密视频。

**用法**：

```
/lzy-video-to-text <视频URL或本地路径> [选项]
例：/lzy-video-to-text https://www.bilibili.com/video/BVxxxx --domain shortvideo
例：/lzy-video-to-text ~/Desktop/口播.mp4 --timestamps
```

**常用选项**：
- `--domain shortvideo|health|drug|business` —— 行业词库纠错（行业内容必加，否则专业术语全是错字）
- `--timestamps` —— 输出带 `[mm:ss]` 时间戳的分段稿
- `--model turbo|large-v3|medium|small` —— 转写模型档位（默认 turbo）
- `--outdir <目录> --title <标题>` —— 归档到指定目录，文件名自动加日期前缀

**前提**：首次使用先跑 `python3 scripts/setup_env.py --install`，依赖装进技能自带的 `.venv`，不污染全局环境。

### 5️⃣ lzy · 工具箱入口（装完即用，零依赖）

只做路由不做分析。`/lzy help` 看全部用法；`/lzy <方法名> [参数]` 直接调用方法；也可以直接描述需求（如贴个抖音主页链接），入口会自动路由。里面还写了「如何新增一个方法」的规范——以后新的自媒体分析方法都往这个工具箱里沉淀。

## 快速安装

如果你在用 Claude Code（或任何 AI 编程工具），直接对 AI 说：

> 帮我安装这个 skill：https://github.com/liuzhiyu/lzy-skills

不用 AI 工具的话，手动一条命令：

```bash
git clone https://github.com/liuzhiyu/lzy-skills.git && bash lzy-skills/install.sh
```

`install.sh` 把 `skills/` 下所有 `lzy-*` 复制到 `~/.claude/skills/`，幂等可重复执行（再次运行即更新）。

### 环境依赖（重要）

| 技能 | 装完即用 | 需要额外环境 |
|---|---|---|
| `lzy` 入口 / `lzy-script-coach` | ✅ | 无（纯方法论，零依赖） |
| `lzy-video-to-text` | ❌ | ffmpeg + whisper（重依赖技能，转写用；首次使用时让 AI 引导安装） |
| `lzy-douyin-funnel` | ❌ | bsk（BrowserSkill，需登录抖音）+ Python + jieba（setup_env.py 自动装进 .venv） |
| `lzy-douyin-teardown` | ❌ | bsk（BrowserSkill，需登录抖音）+ ffmpeg + whisper + 抽帧/音频分类环境 |

装完后在 Claude Code 里输入 `/lzy help` 查看用法。

### 跨平台说明

已实测环境：**macOS**。其他平台理论支持情况：

- `lzy-video-to-text`：**明确支持 Windows**（`setup_env.py` 内置 Windows 安装路径：`winget install Gyan.FFmpeg`、yt-dlp、faster-whisper 跨平台后端 CPU/CUDA 均可）。Linux 同理。
- `lzy-douyin-funnel` / `lzy-douyin-teardown`：各自依赖在 Windows 均可安装，bash 脚本在 Git Bash 下可跑；**共同卡点是 bsk（BrowserSkill）**——抖音登录抓取目前只在 macOS 验证过，Windows 可用性未验证。

> 当前版本：lzy 1.3.0 / douyin-teardown 1.0.1 / douyin-funnel 1.0.0 / script-coach 1.0.0 / video-to-text 1.0.1

## 目录结构

```
skills/
├── lzy/                  入口：路由表 + help + 新增方法规范 + 发布流程
├── lzy-douyin-teardown/  抖音爆款拆解（SKILL.md + scripts/ + VERSION）
├── lzy-douyin-funnel/    抖音搜索词漏斗（SKILL.md + scripts/ + config_* + VERSION）
├── lzy-script-coach/    口播文案校正（SKILL.md + VERSION，零依赖）
└── lzy-video-to-text/    视频转文字（SKILL.md + scripts/ + glossary/ + VERSION）
```

## 机制

- **版本检查**：每个技能根目录有 `VERSION`，`scripts/check_update.sh` 每天最多联网查一次远端版本，有更新时提示。仓库公开、匿名可读；若本机存在 `~/.workbuddy/.lzy-github-token` 会带认证请求（仅作者机器需要）。
- **发布**：本地 `~/.claude/skills/lzy*` 是源；改完跑 `validate.sh` 校验 → 升 `VERSION` → `publish.sh` 自动 clone 到 /tmp → 同步 → 校验 → commit → push。
- **新增方法**：见 `skills/lzy/SKILL.md` 的「如何新增一个方法」。

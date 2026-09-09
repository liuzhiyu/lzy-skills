# video-to-text · 视频转文字

把视频/音频转写成纯文本稿。**全程本地运行，免费、离线、不上传**。

支持 YouTube、B站、网课、直链 mp4，以及本地 mp4/mov/mkv 等文件；
支持 Apple Silicon、Intel Mac、Linux、Windows。

## 特性

- **零付费依赖**：不依赖任何第三方转写服务（无需鲸剪、无需 VIP、无需 API Key）
- **跨平台**：Apple Silicon 走 `mlx-whisper`（Neural Engine 加速），其它平台走 `faster-whisper`（CPU/CUDA）
- **开箱即用**：一条命令自动体检 + 安装缺失依赖，依赖装进独立 venv，不污染全局环境
- **行业词库矫正**：内置短视频运营 / 大健康 / 商业三套词库，两层机制专治行业术语错字
- **隐私**：音频不出本机，无需上传任何文件
- **带时间戳**：可输出 `[mm:ss]` 分段稿，便于按时间定位与剪辑

## 快速开始

```bash
# 1. 体检并自动安装依赖（仅首次）
python3 scripts/setup_env.py --install

# 2. 转写（行业内容建议加 --domain）
python3 scripts/transcribe.py --input "视频URL或本地路径" --language zh --domain shortvideo
```

输出 txt 路径会打印在最后一行。

常用参数：

```bash
# 归档到指定目录 + 带时间戳
python3 scripts/transcribe.py \
  --input "video.mp4" \
  --outdir "./转写归档" \
  --title "这期视频的主题" \
  --timestamps --language zh --domain shortvideo

# CPU 机器嫌慢就换小模型
python3 scripts/transcribe.py --input video.mp4 --model small
```

## 为什么错字多？——行业词库

Whisper 中文错字 **90% 集中在专有名词**。普通口语它很准，但行业词没有语言先验，
会被写成同音的日常词：

```
裸跑   短视频或客 / 玩播率 / 岂微流资 / 思域承接
加词库 短视频获客 / 完播率 / 企微留资 / 私域承接
```

默认三层：

1. **按词库显式映射替换**——词库里列过的错写
2. **同音字兜底**（需 `pypinyin`）——读音相同即判为错写，**不用穷举错写列表**
3. **中文 ASR 通病清理**——与行业无关

第二层专门解决穷举不完的问题：词库列了 岂微/企威/起微/奇微，实际还能写成「起威」——
同音字组合列不完，但读音一样就能发现。缺 `pypinyin` 时自动跳过，不影响主流程。

第三层包括：补语「得」被写成「的」（`吃的不多`→`吃得不多`）、半角标点转全角
（`我们,今天`→`我们，今天`，URL 和 `3.5` 不受影响）、清理多余空格与乱码。

另有可选的 `--prompt`（转写时注入热词提示），**默认关闭**：实测它会改变模型解码，
偶发把逗号输出成全角 `Ｚ`、或产生重复幻觉（试试→是是），而后两层已能覆盖绝大多数错字。
词库很小或纠错后仍不满意时可以试试。

内置词库：

| `--domain` | 适用 |
|---|---|
| `shortvideo` | 短视频运营 / 获客 |
| `health` | 大健康 / 营养 / 功能医学 |
| `business` | 商业 / ToB / 创业 |

自建词库（`glossary/*.txt` 同格式）：

```txt
# 正确写法 = 误识别1, 误识别2
智宇师兄 = 志宇师兄, 智宇师付
CPM医生 = CPM一生, CPM医师
```

```bash
python3 scripts/transcribe.py --input 视频 --domain shortvideo --glossary ~/myglossary.txt
```

设为默认：`export VIDEO_TO_TEXT_DOMAIN=shortvideo`、`export VIDEO_TO_TEXT_GLOSSARY=~/myglossary.txt`

## 平台支持

| 平台 | 转写后端 | 加速方式 |
|------|----------|----------|
| Apple Silicon (M1/M2/M3/M4) | mlx-whisper | Neural Engine |
| Intel Mac | faster-whisper | CPU (int8) |
| Linux | faster-whisper | CPU (int8) / CUDA |
| Windows | faster-whisper | CPU (int8) / CUDA |

系统依赖：`ffmpeg`（必需）、`yt-dlp`（仅 URL 输入需要）。
首次运行 `setup_env.py --install` 会自动补齐 Python 依赖并给出 ffmpeg 的安装命令。

## 目录结构

```
video-to-text/
├── SKILL.md                         技能定义（给 AI 读）
├── README.md                        本文件
├── LICENSE.txt                      MIT
├── scripts/
│   ├── setup_env.py                 环境体检 + 依赖自动安装
│   ├── transcribe.py                核心转写管线
│   ├── glossary.py                  行业词库：热词提示 + 转写纠错
│   ├── protected_site_capture.py    抖音等需登录站点的抓取转写
│   ├── watch_transcribe.py          收件箱批量转写（可挂定时任务）
│   └── _env.py                      共享环境配置（路径/后端/venv 解析）
├── glossary/
│   ├── shortvideo.txt               短视频运营 / 获客词库
│   ├── health.txt                   大健康 / 营养词库
│   └── business.txt                 商业 / ToB 词库
└── references/
    └── INSTALL.md                   各平台安装详解与故障排查
```

## 常见问题

**需要联网吗？**
装依赖和首次下模型时需要。之后全程离线可用。

**模型多大？**
默认 turbo 约 1.5GB（仅下载一次）。嫌大可用 `--model small`（约 500MB）。

**下载模型超时？**
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

**抖音链接转写失败？**
抖音接口需要登录态，用浏览器抓取模式：
```bash
python3 scripts/protected_site_capture.py --input "<抖音链接>" --title "主题"
```
需要 `bsk` CLI（来自 BrowserSkill 技能）；未安装时脚本会给出安装指引。

更多排查见 `references/INSTALL.md`。

## 许可

MIT — 见 `LICENSE.txt`。

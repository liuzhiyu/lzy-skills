# 安装与故障排查

正常情况只需 `python3 scripts/setup_env.py --install`。本文件用于排查异常场景、
离线部署、以及需要手动干预的环境。

## 一、依赖一览

| 依赖 | 必需性 | 用途 | 缺失后果 |
|------|--------|------|----------|
| Python 3.9+ | 必需 | 运行脚本 | 无法运行 |
| ffmpeg | 必需 | 抽取/归一化音轨 | 无法处理任何输入 |
| 转写后端 | 必需 | Whisper 推理 | 无法转写 |
| yt-dlp | 可选 | 从视频链接下载 | 本地文件仍可用，URL 不可用 |
| bsk | 可选 | 抓取需登录站点 | 普通转写不受影响 |

## 二、各平台安装命令

`setup_env.py --install` 会处理 Python 依赖；系统级依赖需按平台手动装一次。

### macOS

```bash
# Homebrew（推荐，需先装 https://brew.sh）
brew install ffmpeg
brew install yt-dlp          # 可选

# 无 Homebrew：下载静态构建
# https://evermeet.cx/ffmpeg/ 或 https://www.osxexperts.net/
```

### Linux

```bash
# Debian / Ubuntu
sudo apt-get update && sudo apt-get install -y ffmpeg
# Fedora
sudo dnf install -y ffmpeg ffmpeg-free
# Arch
sudo pacman -S ffmpeg
# Conda 环境
conda install -c conda-forge ffmpeg

# yt-dlp（可选）
pipx install yt-dlp          # 推荐，避免污染系统 Python
# 或 sudo apt install yt-dlp
```

### Windows

```powershell
winget install Gyan.FFmpeg        # 推荐，Win11 自带 winget
winget install yt-dlp.yt-dlp
# 备选：choco install ffmpeg  /  scoop install ffmpeg
```

装完 ffmpeg 需**重开终端**让 PATH 生效。验证：`ffmpeg -version`。

## 三、Python 环境：隔离策略

依赖默认装到 skill 自带的 `.venv`，**不污染全局环境**。

```
<skill 目录>/
└── .venv/          # 由 setup_env.py 自动创建
```

自定义位置：

```bash
export VIDEO_TO_TEXT_VENV=~/.venvs/video-to-text
python3 scripts/setup_env.py --install
```

想复用已有的 Python 环境（例如已装好 mlx-whisper 的 conda/venv），
直接激活后跑脚本即可，脚本检测到当前解释器已有后端就不会再建 venv：

```bash
conda activate myenv
python3 scripts/transcribe.py --input video.mp4 --language zh
```

或强制指定解释器：

```bash
export VIDEO_TO_TEXT_PYTHON=/path/to/your/python
```

## 四、模型下载与缓存

首次转写会自动下载模型（turbo 约 1.5GB，仅一次），缓存在：

| 后端 | 缓存位置 |
|------|----------|
| mlx-whisper / faster-whisper | `~/.cache/huggingface/hub/` |
| openai-whisper | `~/.cache/whisper/` |

模型档位与体积（越小越快、精度越低）：

| 档位 | 显存/内存占用 | 速度 | 精度 |
|------|--------------|------|------|
| `tiny` | ~1GB | 最快 | 低 |
| `base` | ~1GB | 很快 | 一般 |
| `small` | ~2GB | 快 | 较好 |
| `medium` | ~5GB | 慢 | 好 |
| `large-v3` | ~10GB | 很慢 | 很好 |
| `turbo`（默认） | ~6GB | 快 | 很好（推荐） |

CPU 机器上默认档位自动降为 `small`，避免首次体验过慢。强制指定：`--model turbo`。

## 五、中国大陆网络加速

HuggingFace 与 PyPI 在国内常超时，装依赖或下模型前先设：

```bash
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export HF_ENDPOINT=https://hf-mirror.com
```

建议写进 `~/.zshrc` / `~/.bashrc` 长期生效。

## 六、错误码

| 退出码 | 含义 | 处理 |
|--------|------|------|
| 0 | 成功 / 全部就绪 | — |
| 1 | 存在缺失依赖（体检）或运行失败 | 看 stderr 提示 |
| 2 | 安装过程失败 | 看具体命令输出，多为网络问题 |
| 3 | `bsk` 未安装（受保护站点脚本） | 安装 BrowserSkill，或改用普通模式 |
| 130 | 用户中断 | — |

## 七、常见故障

**`ffmpeg 抽取音轨失败`**
文件不是有效媒体，或 URL 下载到的是 HTML 错误页。用 `file <路径>` 检查；
URL 场景确认链接可直接访问。

**`该视频没有音轨`**
视频本身没有声音（纯画面录屏、无声素材），没有可转写内容。确认：

```bash
ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 <文件>
# 无输出即无音轨
```

**链接下载报 `502 Bad Gateway` / 连不上**
多数是代理问题 —— 系统代理会拦截内网地址和部分域名。

```bash
--proxy ''                            # 绕过系统代理（内网/本机地址常用）
--proxy http://proxy.company.com:8080 # 显式指定公司代理
```

注意：`no_proxy` 环境变量对 yt-dlp 通常无效，请用 `--proxy` 参数。

**`未找到 yt-dlp`**
`python3 scripts/setup_env.py --install`，或直接用本地文件路径。

**`未产出可处理文件；该站点可能需要登录/cookie`**
加 `--cookies-from-browser chrome`（需本机浏览器已登录该站点）。

**`所有模型候选均失败`**
多为网络问题。设 `HF_ENDPOINT=https://hf-mirror.com` 后重跑；
也可能是磁盘空间不足（turbo 需 1.5GB+）。

**CPU 上转写极慢**
换小模型 `--model base`；或只转写片段（先用 ffmpeg 裁剪）。

**Permission denied（venv 创建）**
目标目录无写权限，换位置：`export VIDEO_TO_TEXT_VENV=/tmp/v2t-venv`。

**`未知领域`**
`--domain` 只认 `shortvideo` / `health` / `business`。
其它领域用 `--glossary` 指向自己的词库文件，不需要改代码。

**行业术语还是错**
确认词库里有没有这个词。`glossary/<领域>.txt` 里加一行：

```txt
正确词 = 转写出来的错词
```

也可以只加等号左边（裸词），让它进热词提示。改完立即生效，不用重装任何东西。

**想确认词库有没有生效**
转写日志里会有这三行：

```
[video-to-text] 词库[短视频运营 / 获客] 术语 69 个，纠错映射 126 条
[video-to-text] 热词提示(148字): 以下是一段关于短视频运营...
[video-to-text] 纠错 3 类 / 共 5 处：玩播率->完播率、岂微->企微...
```

第三行只在第二层（替换纠错）命中时才出现——全靠第一层热词改对时不会打印，属正常。

## 八、环境变量速查

| 变量 | 作用 |
|------|------|
| `VIDEO_TO_TEXT_OUTDIR` | 默认归档目录（默认 `./transcripts`） |
| `VIDEO_TO_TEXT_VENV` | venv 位置（默认 `<skill>/.venv`） |
| `VIDEO_TO_TEXT_PYTHON` | 强制指定转写用解释器 |
| `VIDEO_TO_TEXT_BACKEND` | 强制后端：`mlx-whisper`/`faster-whisper`/`openai-whisper` |
| `VIDEO_TO_TEXT_MODEL` | 默认模型档位 |
| `VIDEO_TO_TEXT_DOMAIN` | 默认行业词库：`shortvideo`/`health`/`business` |
| `VIDEO_TO_TEXT_GLOSSARY` | 默认自定义词库文件路径 |
| `VIDEO_TO_TEXT_INBOX` | 收件箱目录（watch 脚本） |
| `VIDEO_TO_TEXT_ARCHIVE` | 已转写视频归档目录（watch 脚本） |
| `PIP_INDEX_URL` | pip 镜像源 |
| `HF_ENDPOINT` | HuggingFace 镜像 |

## 九、离线 / 内网部署

在有网的机器上先准备好模型，再把缓存目录整体拷到目标机：

```bash
# 源机器：确认模型已缓存
ls ~/.cache/huggingface/hub/
# 或显式预热
python3 -c "from huggingface_hub import snapshot_download; \
  snapshot_download('mlx-community/whisper-large-v3-turbo')"

# 目标机器：拷贝缓存后，全程断网可用
scp -r ~/.cache/huggingface 目标机:~/.cache/
```

脚本优先读本地缓存（`local_files_only=True`），缓存命中时完全不联网。

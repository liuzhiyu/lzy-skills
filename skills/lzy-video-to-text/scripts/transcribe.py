#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video-to-text 核心管线：视频/音频 -> 纯文本稿。

输入：视频 URL（YouTube / B站 / 网课 / 直链 mp4 等）或本地视频/音频文件路径
输出：纯文本转写稿（txt）

流程：
  1. URL      -> yt-dlp 抽取音轨
     本地文件 -> ffmpeg 抽音轨
  2. ffmpeg 归一化到 16kHz 单声道 wav（Whisper 要求）
  3. 本地 Whisper 转写（自动选后端，离线、免费）
  4. 写出 txt

后端自动选择：
  Apple Silicon (M 系列)  -> mlx-whisper    （Neural Engine 加速，最快）
  Intel Mac / Linux / Win -> faster-whisper （CPU int8，有 N 卡自动走 CUDA）
  兜底                     -> openai-whisper

首次使用请先跑体检/安装：
    python3 scripts/setup_env.py --install
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
import glossary as G  # noqa: E402

_env.ensure_utf8_console()

SETUP_CMD = f"python3 {os.path.join('scripts', 'setup_env.py')}"
MISSING_HINT = (
    "转写后端未安装。请先运行：\n"
    f"    {SETUP_CMD} --install\n"
    "它会自动把依赖装进 skill 自带的 .venv，不污染你的全局环境。"
)


def log(msg):
    _env.log(msg)


def is_url(s):
    return s.startswith("http://") or s.startswith("https://")


# ---------------------------------------------------------------- 命令定位
def ytdlp_base():
    """
    定位 yt-dlp 的调用方式。
    优先用 skill venv 里装的那份（setup_env.py 会装进去），
    其次 PATH 上的 yt-dlp，都没有则退回 `python -m yt_dlp`（会给出明确报错）。
    """
    venv = _env.venv_dir()
    if _env.venv_has_module(venv, "yt_dlp"):
        return [_env.venv_python(venv), "-m", "yt_dlp"]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _ytdlp_failure(e):
    """把 yt-dlp 的 CalledProcessError 翻成人能看懂的提示。"""
    err = e.stderr or b""
    if isinstance(err, bytes):
        err = err.decode("utf-8", "replace")
    lines = [l.strip() for l in err.splitlines() if l.strip()]
    keep = [l for l in lines if l.startswith("ERROR") or "Error" in l]
    detail = "\n  ".join((keep or lines)[-3:]) or "（无错误输出）"
    return (
        f"yt-dlp 下载失败：\n  {detail}\n\n"
        "常见原因与处理：\n"
        "  · 站点需要登录   -> 加 --cookies-from-browser chrome\n"
        "  · 网络 / 代理问题 -> 检查代理设置（内网地址可能需要 no_proxy）\n"
        "  · 站点不支持     -> 先手动确认链接在浏览器里能正常播放\n"
        "  · 只想转本地文件 -> 直接传文件路径，不需要 yt-dlp"
    )


def require(cmd_name, hint):
    if shutil.which(cmd_name) is None:
        raise RuntimeError(
            f"未找到 `{cmd_name}`，它是本流程必需的。\n{hint}\n"
            f"也可运行 `{SETUP_CMD} --install` 自动安装。"
        )


# ---------------------------------------------------------------- 下载 / 归一化
def download_audio(url, workdir, proxy=None):
    """用 yt-dlp 把视频 URL 抽成可处理的音/视频文件。"""
    base = list(ytdlp_base())
    if proxy is not None:
        # 传空字符串表示绕过系统代理（内网地址常需要）
        base += ["--proxy", proxy]
    out_tpl = os.path.join(workdir, "dl.%(ext)s")
    # 首选：只抽最佳音轨并转 wav
    cmd_audio = base + ["-f", "bestaudio", "--extract-audio",
                        "--audio-format", "wav", "--no-playlist", "-o", out_tpl, url]
    # 兜底：某些单流 mp4 没有独立音轨，改为下载最佳完整文件，再由 ffmpeg 抽音频
    cmd_best = base + ["-f", "best", "--no-playlist", "-o", out_tpl, url]
    log(f"yt-dlp 下载音轨: {url}")
    try:
        subprocess.run(cmd_audio, check=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError(
            f"未安装 yt-dlp。运行 `{SETUP_CMD} --install` 安装，或直接传入本地文件路径。")
    except subprocess.CalledProcessError as e1:
        log("bestaudio 失败，改用 best 整文件下载，后续由 ffmpeg 抽音频")
        try:
            subprocess.run(cmd_best, check=True, capture_output=True)
        except subprocess.CalledProcessError as e2:
            # 兜底命令也失败 -> 抛出可读错误，而不是裸的 CalledProcessError
            raise RuntimeError(_ytdlp_failure(e2 or e1))
    cands = [f for f in os.listdir(workdir)
             if f.endswith((".wav", ".m4a", ".mp3", ".webm", ".ogg",
                            ".mp4", ".mkv", ".mov", ".flac", ".aac"))]
    if cands:
        wavs = [c for c in cands if c.endswith(".wav")]
        return os.path.join(workdir, (wavs[0] if wavs else cands[0]))
    raise RuntimeError("yt-dlp 未产出可处理文件；该站点可能需要登录/cookie，"
                       "可加 --cookies-from-browser chrome 后再试")


def probe_has_audio(src):
    """用 ffprobe 检查是否存在音轨。无法检查时返回 True（交给后续 ffmpeg 报错）。"""
    if shutil.which("ffprobe") is None:
        return True
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", src],
        capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def normalize_to_wav(src, workdir):
    """ffmpeg 归一化到 16kHz 单声道 wav。"""
    require("ffmpeg", "macOS: brew install ffmpeg / Ubuntu: sudo apt-get install -y ffmpeg "
                      "/ Windows: winget install Gyan.FFmpeg")

    # 无声视频（纯画面录屏、无声素材）很常见，先明确区分，别报成"文件损坏"
    if not probe_has_audio(src):
        raise RuntimeError(
            "该视频没有音轨，无法转写文字。\n"
            "请确认这个视频本身有声音——纯画面录屏、静音素材没有可转写的内容。")

    dst = os.path.join(workdir, "audio_16k_mono.wav")
    cmd = ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-vn", dst]
    log("ffmpeg 归一化音轨 -> 16kHz 单声道")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        # 只保留关键错误行，避免 dump 大段 ffmpeg 输出
        keys = [l.strip() for l in err.splitlines()
                if "Error" in l or "Invalid" in l or "No such" in l]
        detail = "\n  ".join(keys[-3:]) if keys else err[-400:]
        raise RuntimeError(f"ffmpeg 抽取音轨失败：\n  {detail}")
    return dst


# ---------------------------------------------------------------- 转写后端
def _norm_result(text, segments):
    return {"text": (text or "").strip(),
            "segments": [{"start": s.get("start", 0), "end": s.get("end", 0),
                          "text": s.get("text", "")} for s in segments or []]}


def _mlx_transcribe(wav, repo, language, prompt=None):
    from mlx_whisper import transcribe as _tw
    # 离线优先：用本地已缓存模型，规避网络/代理问题
    try:
        from huggingface_hub import snapshot_download
        local_model = snapshot_download(repo, local_files_only=True)
        log(f"使用本地缓存模型: {local_model}")
        return _tw(wav, path_or_hf_repo=local_model, language=language,
                   initial_prompt=prompt)
    except Exception as e:
        log(f"本地缓存不可用（{type(e).__name__}），改为加载/下载: {repo}")
        return _tw(wav, path_or_hf_repo=repo, language=language,
                   initial_prompt=prompt)


def _faster_transcribe(wav, repo, language, prompt=None):
    from faster_whisper import WhisperModel
    if _env.has_nvidia_gpu():
        device, compute = "cuda", "float16"
    else:
        device, compute = "cpu", "int8"
    log(f"faster-whisper 载入 {repo}（device={device}, compute={compute}）")
    model = WhisperModel(repo, device=device, compute_type=compute)

    # 注意：不要传 hotwords。实测 faster-whisper 1.2 的 hotwords 是为英文设计的，
    # 传中文（无论整句还是词表）会导致解码输出完全为空——比不加还糟。
    # 中文场景下 initial_prompt 才是有效的热词机制。
    kwargs = {"language": language, "beam_size": 5, "vad_filter": True}
    if prompt:
        kwargs["initial_prompt"] = prompt

    segs_iter, info = model.transcribe(wav, **kwargs)
    segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segs_iter]
    log(f"检测语言: {getattr(info, 'language', '?')} "
        f"(概率 {getattr(info, 'language_probability', 0):.2f})")
    return _norm_result("".join(s["text"] for s in segs), segs)


def _openai_transcribe(wav, repo, language, prompt=None):
    import whisper
    try:
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        dev = "cpu"
    log(f"openai-whisper 载入 {repo}（device={dev}）")
    model = whisper.load_model(repo, device=dev)
    return model.transcribe(wav, language=language, initial_prompt=prompt)


BACKEND_FN = {
    _env.MLX: _mlx_transcribe,
    _env.FASTER: _faster_transcribe,
    _env.OPENAI: _openai_transcribe,
}


def transcribe(wav_path, model, language, backend=None, prompt=None):
    """按后端转写；模型仓库逐个候选尝试（社区仓库名可能变动）。"""
    backend = backend or _env.preferred_backend()
    cands = _env.resolve_model(model, backend)
    log(f"后端 = {backend}，模型候选 = {cands}")
    if prompt:
        log(f"热词提示({len(prompt)}字): {prompt[:60]}...")

    last_err = None
    for repo in cands:
        try:
            log(f"转写中 (model={repo}, lang={language or 'auto'}) ...")
            return BACKEND_FN[backend](wav_path, repo, language, prompt)
        except ImportError:
            raise RuntimeError(MISSING_HINT)
        except Exception as e:
            last_err = e
            log(f"模型 {repo} 失败（{type(e).__name__}: {e}），尝试下一个候选")
            continue

    extra = ""
    msg = str(last_err or "")
    if any(k in msg for k in ("Connection", "Timeout", "timed out", "502", "403", "Proxy")):
        extra = ("\n\n网络问题：中国大陆访问 HuggingFace 常超时，可先执行：\n"
                 "    export HF_ENDPOINT=https://hf-mirror.com\n再重跑。")
    raise RuntimeError(f"所有模型候选均失败：{cands}\n最后错误：{last_err}{extra}")


# ---------------------------------------------------------------- 输出
def fmt_time(sec):
    sec = int(round(sec or 0))
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', '_', str(s)).strip()[:80] or "video"


def build_output_path(args):
    """返回 (输出路径, 是否写元信息头)。"""
    if args.output and not args.outdir and not args.title:
        return args.output, False
    if args.output and args.outdir:
        return os.path.join(args.outdir, os.path.basename(args.output)), True
    outdir = args.outdir or _env.default_outdir()
    base = args.title or os.path.splitext(os.path.basename(args.input))[0]
    if is_url(args.input) and not args.title:
        base = "video"
    fname = f"{date.today().strftime('%Y%m%d')}_{safe_name(base)}_script.txt"
    os.makedirs(outdir, exist_ok=True)
    return os.path.join(outdir, fname), True


def bootstrap_if_needed():
    """
    自举：当前解释器没装转写后端、但 skill 自带 .venv 里有，
    就自动切换到 venv 解释器重跑一次。

    这样无论用户用系统 python3 还是别的解释器执行
    `python3 scripts/transcribe.py ...`，都能落到正确的环境上。
    """
    if os.environ.get("V2T_BOOTSTRAPPED") == "1":
        return
    backend = _env.preferred_backend()
    if _env.current_has(backend):
        return
    venv = _env.venv_dir()
    if not _env.venv_has(venv, backend):
        return  # 两边都没有 -> 交给 transcribe() 抛出安装指引
    py = _env.venv_python(venv)
    log(f"当前解释器缺少 {backend}，自动切换到 skill 自带环境: {py}")
    r = subprocess.run([py, os.path.abspath(__file__)] + sys.argv[1:],
                       env=dict(os.environ, V2T_BOOTSTRAPPED="1"))
    sys.exit(r.returncode)


def main():
    bootstrap_if_needed()
    ap = argparse.ArgumentParser(
        description="视频/音频 -> 文本（本地 Whisper，免费离线）")
    ap.add_argument("--input", required=True,
                    help="视频 URL 或本地视频/音频文件路径")
    ap.add_argument("--output", default=None,
                    help="输出 txt 路径；不指定则归档到默认目录（见 --outdir）")
    ap.add_argument("--model", default=None,
                    help="模型档位：turbo(默认) / large-v3 / medium / small / base / tiny，"
                         "也可传完整 HF 仓库名或本地路径")
    ap.add_argument("--language", default="zh",
                    help="语言代码，默认 zh；留空则自动检测")
    ap.add_argument("--timestamps", action="store_true",
                    help="输出带 [mm:ss] 时间戳的分段稿")
    ap.add_argument("--outdir", default=None,
                    help="归档目录；不指定则用默认目录"
                         "（环境变量 VIDEO_TO_TEXT_OUTDIR 可覆盖，默认 ./transcripts）")
    ap.add_argument("--title", default=None, help="归档文件名用的标题")
    ap.add_argument("--source", default=None,
                    help="归档稿「来源」字段内容（如原始视频 URL），默认取 --input")
    ap.add_argument("--backend", default=None,
                    choices=[_env.MLX, _env.FASTER, _env.OPENAI],
                    help="强制指定转写后端（默认按平台自动选）")
    ap.add_argument("--cookies-from-browser", default=None,
                    help="需要登录的站点可传 chrome / safari / firefox / edge")
    ap.add_argument("--proxy", default=None,
                    help="代理地址（如 http://127.0.0.1:7890）；"
                         "传空字符串 '' 可绕过系统代理，内网地址常需要")
    # ---- 行业词库 / 纠错 ----
    domain_list = ", ".join(f"{k}({v[0]})" for k, v in G.DOMAINS.items())
    ap.add_argument("--domain", default=G.default_domain(),
                    help=f"行业词库，内置：{domain_list}")
    ap.add_argument("--glossary", default=G.default_glossary_path(),
                    help="自定义词库文件路径（格式见 glossary/*.txt），"
                         "可与 --domain 叠加，自定义优先")
    ap.add_argument("--no-glossary", action="store_true",
                    help="关闭词库与纠错，纯裸跑 Whisper")
    ap.add_argument("--no-correct", action="store_true",
                    help="只注入热词提示，不做转写后的替换纠错")
    ap.add_argument("--no-pinyin", action="store_true",
                    help="关闭同音字兜底纠错（需 pypinyin；默认开启，"
                         "能纠出词库没列过的错写，如 启微->企微）")
    ap.add_argument("--prompt", action="store_true",
                    help="额外注入热词提示（默认关闭）。实测后处理纠错已能覆盖"
                         "绝大多数错字，而提示词偶发标点污染与重复幻觉；"
                         "词库很小或术语纠错仍不满意时可加此开关试试")
    args = ap.parse_args()

    # ---------------------------------------------------------------- 词库
    gloss = None
    if not args.no_glossary:
        gloss = G.Glossary.load(domain=args.domain, path=args.glossary)
        if gloss:
            log(gloss.describe())
        elif args.domain or args.glossary:
            log("警告：词库为空，将按无词库处理")
            gloss = None
    # 热词提示默认关闭：实测后两层纠错已能覆盖绝大多数错字，
    # 而提示词会改变解码，偶发标点污染（逗号变全角 Ｚ）与重复幻觉（试试->是是）。
    if args.prompt and gloss:
        log("已开启热词提示（--prompt）；若发现标点异常或重复字，去掉该开关")
    prompt = gloss.build_prompt() if (gloss and args.prompt) else None

    workdir = tempfile.mkdtemp(prefix="v2t_")
    try:
        if is_url(args.input):
            src_wav = download_audio(args.input, workdir, args.proxy)
        else:
            p = os.path.expanduser(args.input)
            if not os.path.exists(p):
                raise FileNotFoundError(f"找不到本地文件: {args.input}")
            src_wav = p
        wav = normalize_to_wav(src_wav, workdir)
        lang = args.language if args.language else None
        result = transcribe(wav, args.model, lang, args.backend, prompt)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    text = (result.get("text") or "").strip()
    segments = result.get("segments") or []

    # ---------------------------------------------------------------- 纠错
    hits = []
    if gloss and not args.no_correct:
        use_py = not args.no_pinyin
        # 逐段纠错后再拼全文，保证 --timestamps 与纯文本稿内容一致
        if segments:
            for seg in segments:
                seg["text"] = gloss.tidy_spaces(
                    gloss.correct(seg.get("text", ""), use_py)[0])
            text = "".join(s.get("text", "") for s in segments).strip()
        text, hits = gloss.correct(text, use_py)
        text = gloss.tidy_spaces(text)
        if hits:
            log(f"纠错 {len(hits)} 类 / 共 {sum(h[2] for h in hits)} 处：" +
                "、".join(f"{w}->{r}({m})" for w, r, _, m in hits[:8]))

    out_path, with_meta = build_output_path(args)

    lines = []
    if with_meta:
        lines.append(f"# 转写稿：{args.title or os.path.basename(args.input)}")
        lines.append(f"- 来源：{args.source or args.input}")
        lines.append(f"- 日期：{date.today().isoformat()}")
        lines.append(f"- 模型：{args.model or 'auto'} / "
                     f"后端：{args.backend or _env.preferred_backend()} / lang={args.language}")
        if gloss:
            lines.append(f"- 词库：{gloss.name}"
                         f"（术语 {len(gloss.terms)} / 纠错映射 {len(gloss.fixes)}）")
            if hits:
                lines.append("- 已纠错：" +
                             "；".join(f"{w}→{r}×{n}({m})" for w, r, n, m in hits))
                if any(m == "拼音" for _, _, _, m in hits):
                    lines.append("  （标「拼音」的是按同音推断改的，非词库声明，"
                                 "跨领域内容请抽查核对）")
            elif args.no_correct:
                lines.append("- 词库：仅注入热词，未做替换纠错")
        lines.append("")
    if args.timestamps and segments:
        for seg in segments:
            lines.append(f"[{fmt_time(seg.get('start', 0))}] {seg.get('text', '').strip()}")
    else:
        lines.append(text)
    content = "\n".join(lines).strip() + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"完成 -> {out_path} (字符数: {len(text)})")
    print(out_path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        _env.log(f"失败：{e}")
        sys.exit(1)

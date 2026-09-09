#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video-to-text 共享环境配置。

transcribe.py / protected_site_capture.py / watch_transcribe.py / setup_env.py
共用本模块，避免「路径解析」「平台判定」「后端选择」「venv 定位」四处重复。

对外发布的 skill 不得硬编码任何用户机器上的绝对路径，
所有可配置项一律通过环境变量覆盖：

    VIDEO_TO_TEXT_OUTDIR   默认归档目录（不设则自动推断）
    VIDEO_TO_TEXT_VENV     venv 位置（默认 <skill>/.venv）
    VIDEO_TO_TEXT_PYTHON   强制指定用于转写的解释器
    VIDEO_TO_TEXT_BACKEND  强制指定后端：mlx-whisper|faster-whisper|openai-whisper
    VIDEO_TO_TEXT_MODEL    默认模型档位：turbo|large-v3|medium|small|base|tiny
"""
import os
import platform
import shutil
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- 平台判定
SYSTEM = platform.system()                    # Darwin | Linux | Windows
MACHINE = platform.machine().lower()          # arm64 | x86_64 | amd64
IS_MAC = SYSTEM == "Darwin"
IS_WIN = SYSTEM == "Windows"

# Apple Silicon（M 系列）才能用 mlx —— mlx 框架仅支持 arm64 macOS
IS_APPLE_SILICON = IS_MAC and MACHINE in ("arm64", "aarch64")

# Linux/Windows 上有 N 卡时可走 CUDA，否则 CPU int8
def has_nvidia_gpu():
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, timeout=15)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 后端选择
MLX = "mlx-whisper"
FASTER = "faster-whisper"
OPENAI = "openai-whisper"

# 模型档位 -> 各后端的具体仓库/短名。
# faster-whisper 用短名最稳（库内部会映射到官方 CTranslate2 仓库）；
# 短名失败时 _resolve 会依次回退到别名列表里的备选仓库。
MODEL_ALIASES = {
    "turbo": {
        MLX:    ["mlx-community/whisper-large-v3-turbo",
                 "mlx-community/whisper-large-v3-mlx"],
        FASTER: ["large-v3-turbo",
                 "mobiuslabsgmbh/faster-whisper-large-v3-turbo"],
        OPENAI: ["turbo"],
    },
    "large-v3": {
        # 注意：mlx-community/whisper-large-v3 不存在，正确名是 -mlx 后缀
        MLX:    ["mlx-community/whisper-large-v3-mlx"],
        FASTER: ["large-v3", "Systran/faster-whisper-large-v3"],
        OPENAI: ["large-v3"],
    },
    "medium": {
        MLX:    ["mlx-community/whisper-medium-mlx",
                 "mlx-community/whisper-medium"],
        FASTER: ["medium", "Systran/faster-whisper-medium"],
        OPENAI: ["medium"],
    },
    "small": {
        MLX:    ["mlx-community/whisper-small-mlx"],
        FASTER: ["small", "Systran/faster-whisper-small"],
        OPENAI: ["small"],
    },
    "base": {
        MLX:    ["mlx-community/whisper-base-mlx"],
        FASTER: ["base", "Systran/faster-whisper-base"],
        OPENAI: ["base"],
    },
    "tiny": {
        MLX:    ["mlx-community/whisper-tiny-mlx",
                 "mlx-community/whisper-tiny"],
        FASTER: ["tiny", "Systran/faster-whisper-tiny"],
        OPENAI: ["tiny"],
    },
}

DEFAULT_MODEL_TIER = "turbo"
# CPU 上 turbo/large-v3 很慢，非 Apple Silicon 默认降一档，避免首次体验劝退
DEFAULT_MODEL_NON_MLX = "small"


def preferred_backend():
    """按平台挑最快可用的后端。"""
    forced = os.environ.get("VIDEO_TO_TEXT_BACKEND")
    if forced in (MLX, FASTER, OPENAI):
        return forced
    return MLX if IS_APPLE_SILICON else FASTER


def default_model_tier(backend=None):
    """默认模型档位：Apple Silicon 用 turbo，其它平台用 small（CPU 友好）。"""
    env = os.environ.get("VIDEO_TO_TEXT_MODEL")
    if env:
        return env
    backend = backend or preferred_backend()
    return DEFAULT_MODEL_TIER if backend == MLX else DEFAULT_MODEL_NON_MLX


def resolve_model(model_arg, backend):
    """
    把用户给的 --model 解析成该后端的候选仓库列表（按顺序回退）。

    --model 可以是：
      - 档位名：turbo / large-v3 / medium / small / base / tiny（推荐，跨平台一致）
      - 完整 HF 仓库名或本地路径（高级用法，原样透传，只试这一个）
    """
    if not model_arg:
        model_arg = default_model_tier(backend)
    table = MODEL_ALIASES.get(model_arg)
    if not table:
        # 完整 HF 仓库名或本地路径：原样透传，只试这一个
        return [model_arg]

    cands = list(table.get(backend) or [])
    if not cands:
        # 该档位在此后端没有映射 -> 退到该后端的默认档位。
        # 绝不跨后端混用候选：mlx 与 CTranslate2 模型格式不兼容，混用必然失败。
        fb = DEFAULT_MODEL_TIER if backend == MLX else DEFAULT_MODEL_NON_MLX
        cands = list(MODEL_ALIASES.get(fb, {}).get(backend) or [])
    return cands or [model_arg]


# ---------------------------------------------------------------- venv 定位
def venv_dir():
    env = os.environ.get("VIDEO_TO_TEXT_VENV")
    if env:
        return os.path.expanduser(env)
    return os.path.join(SKILL_ROOT, ".venv")


def venv_python(venv=None):
    venv = venv or venv_dir()
    if IS_WIN:
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python")


def venv_has_module(venv, mod):
    """venv 里是否已装某个 Python 模块。"""
    py = venv_python(venv)
    if not os.path.exists(py):
        return False
    try:
        # 注意：必须显式 import importlib.util，
        # 单独的 `import importlib` 不会加载 util 子模块，find_spec 会抛 AttributeError
        code = ("import importlib.util as _u, sys; "
                f"sys.exit(0 if _u.find_spec('{mod}') else 1)")
        r = subprocess.run([py, "-c", code], capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def venv_has(venv, backend):
    """venv 里是否已装指定后端。"""
    mod = {MLX: "mlx_whisper", FASTER: "faster_whisper", OPENAI: "whisper"}[backend]
    return venv_has_module(venv, mod)


def current_has(backend):
    """当前解释器是否已装该后端。"""
    mod = {MLX: "mlx_whisper", FASTER: "faster_whisper", OPENAI: "whisper"}[backend]
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def resolve_python(backend=None):
    """
    返回「应该用来跑转写的 python 解释器」。

    优先级：
      1. 环境变量 VIDEO_TO_TEXT_PYTHON
      2. 当前解释器已装后端 -> 直接用（本机已配好的情况，零成本）
      3. skill 自带 .venv 已装后端 -> 用 venv
      4. 都没有 -> 返回 venv 预期路径（尚未创建，交给 setup_env.py --install）
    """
    forced = os.environ.get("VIDEO_TO_TEXT_PYTHON")
    if forced:
        return os.path.expanduser(forced)
    backend = backend or preferred_backend()
    if current_has(backend):
        return sys.executable
    venv = venv_dir()
    if venv_has(venv, backend):
        return venv_python(venv)
    return venv_python(venv)


# ---------------------------------------------------------------- 输出目录
def default_outdir():
    """
    默认归档目录。对外发布版本不含任何个人路径：
      1. 环境变量 VIDEO_TO_TEXT_OUTDIR
      2. 当前工作目录下的 transcripts/
    """
    env = os.environ.get("VIDEO_TO_TEXT_OUTDIR")
    if env:
        return os.path.expanduser(env)
    return os.path.join(os.getcwd(), "transcripts")


def log(msg, stream=None):
    stream = stream or sys.stderr
    try:
        print(f"[video-to-text] {msg}", file=stream, flush=True)
    except UnicodeEncodeError:
        # Windows GBK 控制台兜底
        print(f"[video-to-text] {msg}".encode("utf-8", "replace").decode("utf-8", "replace"),
              file=stream, flush=True)


def ensure_utf8_console():
    """Windows 中文控制台防炸。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

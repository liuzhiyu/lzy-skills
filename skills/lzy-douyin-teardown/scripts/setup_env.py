#!/usr/bin/env python3
"""
douyin-viral-teardown 依赖检测 / 自动安装
=================================================
用法：
  python3 setup_env.py            # 仅检测，输出报告（不装）
  python3 setup_env.py --install  # 检测 + 缺失自动安装（pip 包、brew 工具）
  python3 setup_env.py --install --yes   # 全自动，不交互确认

检测项：
  1. bsk (BrowserSkill CLI) + daemon 127.0.0.1:52800  —— 无法自动装，只能提示
  2. ffmpeg / ffprobe / curl  —— brew 可自动装
  3. whisper 转写环境（video-to-text skill 的 venv + mlx_whisper）
  4. CLAP 音频分类（transformers + 模型，用于 BGM 识别）—— pip 可自动装

退出码：0=全部就绪；1=有缺失（--install 后仍缺的才计）
"""
import os
import sys
import shutil
import subprocess

HOME = os.path.expanduser("~")
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))          # .../scripts
SKILL_ROOT = os.path.dirname(SKILL_DIR)                          # .../douyin-viral-teardown
V2T_DIR = os.path.join(HOME, ".workbuddy", "skills", "video-to-text")
V2T_VENV = os.path.join(V2T_DIR, ".venv", "bin", "python")

AUTO = "--install" in sys.argv
YES = "--yes" in sys.argv

results = []  # (name, ok, detail, auto_installable)


def check(cmd):
    return shutil.which(cmd) is not None


def run(cmd_list, **kw):
    return subprocess.run(cmd_list, capture_output=True, text=True, **kw)


# ---------- 1. bsk ----------
def check_bsk():
    ok = check("bsk")
    if not ok:
        return (False, "未找到 bsk CLI", False)
    # 检查 daemon
    r = run(["curl", "-s", "-m", "3", "http://127.0.0.1:52800/status"])
    if r.returncode != 0:
        return (False, "bsk 存在但 daemon(127.0.0.1:52800) 未响应，请启动 BrowserSkill", False)
    return (True, "bsk CLI + daemon 就绪", False)


# ---------- 2. ffmpeg / ffprobe / curl ----------
def check_media_tools():
    missing = [c for c in ("ffmpeg", "ffprobe", "curl") if not check(c)]
    if not missing:
        return (True, "ffmpeg/ffprobe/curl 就绪", True)
    return (False, f"缺少: {', '.join(missing)}", True)


# ---------- 3. whisper 转写环境 ----------
def check_whisper():
    if not os.path.exists(V2T_VENV):
        return (False, f"video-to-text venv 缺失: {V2T_VENV}", True)
    ts = os.path.join(V2T_DIR, "scripts", "transcribe.py")
    if not os.path.exists(ts):
        return (False, "transcribe.py 缺失", True)
    r = run([V2T_VENV, "-c", "import mlx_whisper"])
    if r.returncode != 0:
        return (False, "mlx_whisper 未装（venv 存在但缺依赖）", True)
    return (True, "whisper 转写环境就绪", True)


# ---------- 4. CLAP 音频分类 ----------
def check_clap():
    # 复用 video-to-text 的 venv（已装 torch），检查 transformers
    if not os.path.exists(V2T_VENV):
        return (False, "CLAP 依赖 video-to-text venv，其缺失", True)
    r = run([V2T_VENV, "-c", "import transformers; import torch"])
    if r.returncode != 0:
        return (False, "transformers 未装（CLAP 需要）", True)
    # 检查模型是否已缓存（不强制，首次会在线下载）
    cache = os.path.join(HOME, ".cache", "huggingface", "hub")
    has_model = False
    if os.path.isdir(cache):
        has_model = any("clap" in d.lower() for d in os.listdir(cache))
    detail = "transformers+torch 就绪，模型已缓存" if has_model else "transformers+torch 就绪（模型首次运行在线下载）"
    return (True, detail, True)


# ---------- 自动安装 ----------
def install_media_tools():
    if check("ffmpeg"):
        return True
    print("  → brew install ffmpeg ...")
    r = run(["brew", "install", "ffmpeg"])
    return r.returncode == 0


def install_whisper():
    if os.path.exists(V2T_VENV):
        r = run([V2T_VENV, "-c", "import mlx_whisper"])
        if r.returncode == 0:
            return True
    # 调用 video-to-text 的 setup 脚本
    setup = os.path.join(V2T_DIR, "scripts", "setup_env.py")
    if os.path.exists(setup):
        print("  → 调用 video-to-text setup_env.py --install ...")
        r = run([V2T_VENV if os.path.exists(V2T_VENV) else sys.executable, setup, "--install"])
        return r.returncode == 0
    return False


def install_clap():
    r = run([V2T_VENV, "-c", "import transformers"])
    if r.returncode != 0:
        print("  → pip install transformers torchaudio ...")
        r2 = run([V2T_VENV, "-m", "pip", "install", "transformers", "torchaudio"])
        if r2.returncode != 0:
            return False
    return True


def main():
    checks = [
        ("bsk (BrowserSkill)", check_bsk),
        ("ffmpeg/ffprobe/curl", check_media_tools),
        ("whisper 转写环境", check_whisper),
        ("CLAP 音频分类(BGM识别)", check_clap),
    ]

    print("=" * 60)
    print("douyin-viral-teardown 依赖检测")
    print("=" * 60)

    for name, fn in checks:
        ok, detail, auto = fn()
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}: {detail}" + ("  (可自动装)" if auto and not ok else ""))

    if AUTO:
        print("\n" + "=" * 60)
        print("开始自动安装缺失依赖...")
        print("=" * 60)
        # 逐个尝试
        for name, fn, installer in [
            ("ffmpeg", check_media_tools, install_media_tools),
            ("whisper", check_whisper, install_whisper),
            ("clap", check_clap, install_clap),
        ]:
            ok, detail, auto = fn()
            if ok:
                continue
            if not auto:
                continue
            if not YES:
                ans = input(f"\n安装 {name} 相关依赖? [y/N] ").strip().lower()
                if ans != "y":
                    print(f"  跳过 {name}")
                    continue
            print(f"  → 安装 {name} ...")
            if installer():
                print(f"  ✅ {name} 安装完成")
            else:
                print(f"  ❌ {name} 安装失败，请手动处理")

        print("\n" + "=" * 60)
        print("复检：")
        print("=" * 60)
        all_ok = True
        for name, fn in checks:
            ok, detail, auto = fn()
            mark = "✅" if ok else "❌"
            print(f"{mark} {name}: {detail}")
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)
    else:
        missing = sum(1 for _, fn in checks if not fn()[0])
        print("\n提示：加 --install 参数可自动安装 pip 包与 brew 工具（bsk 需手动装）。")
        sys.exit(0 if missing == 0 else 1)


if __name__ == "__main__":
    main()

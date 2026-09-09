#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video-to-text 环境自检 + 依赖安装引导。

任何人在任何机器上装完本 skill 后，先跑它：

    python3 scripts/setup_env.py                # 体检：报告缺什么、怎么装
    python3 scripts/setup_env.py --install      # 体检 + 自动安装可安全自动化的部分
    python3 scripts/setup_env.py --json         # 机器可读，供 agent 解析后提示用户
    python3 scripts/setup_env.py --print-python # 只打印可直接用于转写的解释器路径

退出码：
    0  全部就绪
    1  存在缺失项（体检模式）
    2  安装过程失败

设计原则（对外发布版）：
    · 不硬编码任何用户路径，全部走 _env.py 的环境变量覆盖机制
    · Python 依赖装进 skill 自带的 .venv，绝不污染用户全局环境
    · 系统级依赖（ffmpeg）默认「给命令、不代劳」，避免 sudo 风险；
      仅 macOS + 已装 Homebrew 时才自动 brew install（可用 --no-system 关闭）
    · 中国网络环境：自动提示 pip 镜像源与 HF_ENDPOINT 加速
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402

_env.ensure_utf8_console()

GREEN, RED, YELLOW = "🟢", "🔴", "🟡"


# ================================================================== 检查项
def check_python():
    v = sys.version_info
    ok = v >= (3, 9)
    return {
        "name": "Python",
        "required": True,
        "ok": ok,
        "found": f"{v.major}.{v.minor}.{v.micro}",
        "need": ">= 3.9",
        "fix": ["安装 Python 3.9+：https://www.python.org/downloads/"] if not ok else [],
    }


def check_ffmpeg():
    path = shutil.which("ffmpeg")
    return {
        "name": "ffmpeg",
        "required": True,
        "ok": bool(path),
        "found": path or "未安装",
        "need": "抽音轨必需",
        "fix": [] if path else ffmpeg_install_cmds(),
        "auto_installable": can_auto_install_ffmpeg(),
    }


def check_ytdlp():
    path = shutil.which("yt-dlp")
    return {
        "name": "yt-dlp",
        "required": False,  # 仅 URL 输入需要；本地文件不需要
        "ok": bool(path),
        "found": path or "未安装",
        "need": "仅「视频链接」转写时需要；本地文件不需要",
        "fix": [] if path else [
            f"{venv_pip()} install -U yt-dlp",
            "macOS:   brew install yt-dlp",
            "Windows: winget install yt-dlp.yt-dlp",
            "Linux:   pipx install yt-dlp   （或 sudo apt install yt-dlp）",
        ],
        "auto_installable": True,
        "pip_pkg": "yt-dlp",
    }


def check_backend(backend):
    mod = {_env.MLX: "mlx_whisper", _env.FASTER: "faster_whisper",
           _env.OPENAI: "whisper"}[backend]
    import importlib.util
    here = importlib.util.find_spec(mod) is not None
    in_venv = _env.venv_has(_env.venv_dir(), backend)
    ok = here or in_venv
    where = []
    if here:
        where.append("当前解释器")
    if in_venv:
        where.append("skill .venv")
    note = {
        _env.MLX: "Apple Silicon 专属，Neural Engine 加速（最快）",
        _env.FASTER: "跨平台后端，CPU/CUDA 均可（Intel Mac / Linux / Windows）",
        _env.OPENAI: "官方参考实现，最通用但最慢",
    }[backend]
    return {
        "name": f"转写后端 {backend}",
        "required": True,
        "ok": ok,
        "found": "、".join(where) if where else "未安装",
        "need": note,
        "fix": [] if ok else [
            f"{venv_pip()} install -U {backend}",
            "（默认装进 skill 自带 .venv，不污染全局环境）",
        ],
        "auto_installable": True,
        "pip_pkg": backend,
        "backend": backend,
    }


def check_pypinyin():
    """
    可选依赖：同音字兜底纠错用。
    没装不影响主流程（自动降级为只做词库显式映射），只是纠不出没列过的错写。
    """
    import importlib.util
    here = importlib.util.find_spec("pypinyin") is not None
    in_venv = _env.venv_has_module(_env.venv_dir(), "pypinyin")
    ok = here or in_venv
    return {
        "name": "pypinyin（同音字纠错，可选）",
        "required": False,
        "ok": ok,
        "found": "已安装" if ok else "未安装",
        "need": "让「启微→企微」这种词库没列过的同音错写也能自动纠正",
        "fix": [] if ok else [
            f"{venv_pip()} install -U pypinyin",
            "（不装也能用，只是少一层兜底）",
        ],
        "auto_installable": True,
        "pip_pkg": "pypinyin",
    }


# ================================================================== 安装命令
def ffmpeg_install_cmds():
    if _env.IS_MAC:
        return [
            "brew install ffmpeg          （需先装 Homebrew：https://brew.sh）",
            "无 Homebrew 时：下载静态构建 https://evermeet.cx/ffmpeg/ 或 https://www.osxexperts.net/",
        ]
    if _env.IS_WIN:
        return [
            "winget install Gyan.FFmpeg   （推荐，Windows 11 自带 winget）",
            "或 choco install ffmpeg",
            "或 scoop install ffmpeg",
        ]
    return [
        "sudo apt-get update && sudo apt-get install -y ffmpeg      # Debian/Ubuntu",
        "sudo dnf install -y ffmpeg ffmpeg-free                     # Fedora",
        "sudo pacman -S ffmpeg                                      # Arch",
        "conda install -c conda-forge ffmpeg                        # Conda 环境",
    ]


def can_auto_install_ffmpeg():
    """只有 macOS + 已有 brew 时才自动装系统包，其它平台一律只给命令。"""
    return _env.IS_MAC and shutil.which("brew") is not None


def venv_pip():
    v = _env.venv_dir()
    if _env.IS_WIN:
        return f'{os.path.join(v, "Scripts", "python.exe")} -m pip'
    return f'{os.path.join(v, "bin", "python")} -m pip'


def pip_index_hint():
    """国内网络加速提示。"""
    if os.environ.get("PIP_INDEX_URL") or os.environ.get("HF_ENDPOINT"):
        return []
    return [
        "",
        "⚡ 中国大陆网络加速（可选，能显著减少超时）:",
        "   export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple",
        "   export HF_ENDPOINT=https://hf-mirror.com",
    ]


# ================================================================== 执行安装
def ensure_venv():
    v = _env.venv_dir()
    py = _env.venv_python(v)
    if os.path.exists(py):
        return py
    _env.log(f"创建隔离虚拟环境: {v}")
    r = subprocess.run([sys.executable, "-m", "venv", v],
                       capture_output=True, text=True)
    if r.returncode != 0:
        _env.log(f"venv 创建失败: {r.stderr.strip()}")
        return None
    # 升级 pip（失败不致命）
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"],
                   capture_output=True, timeout=300)
    return py


def pip_install(pkg):
    py = ensure_venv()
    if not py:
        return False, "venv 创建失败"
    _env.log(f"安装 {pkg} 到 {_env.venv_dir()} ...（首次约需 1-5 分钟）")
    try:
        r = subprocess.run([py, "-m", "pip", "install", "-U", pkg],
                           capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "安装超时，可重试或换用 pip 镜像源"
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()[-6:]
        return False, "\n".join(tail)
    return True, ""


def auto_install_system(item):
    if item["name"] == "ffmpeg" and can_auto_install_ffmpeg():
        _env.log("brew install ffmpeg ...（首次约需 1-3 分钟）")
        r = subprocess.run(["brew", "install", "ffmpeg"],
                           capture_output=True, text=True, timeout=1800)
        return r.returncode == 0, (r.stderr or "").strip()[-500:]
    return False, ""


# ================================================================== 报告
def render_text(items, platform_info, installed):
    lines = []
    lines.append("=" * 62)
    lines.append("video-to-text · 环境体检")
    lines.append("=" * 62)
    lines.append(f"系统: {platform_info['system']} {platform_info['machine']}"
                 f"   Python: {platform_info['python']}")
    lines.append(f"推荐后端: {platform_info['backend']}"
                 f"   默认模型: {platform_info['model']}")
    lines.append("")
    lines.append(f"{'状态':<4} {'依赖':<26} {'当前':<34} 说明")
    lines.append("-" * 62)
    for it in items:
        mark = GREEN if it["ok"] else (RED if it["required"] else YELLOW)
        tag = "必需" if it["required"] else "可选"
        found = it["found"]
        if len(found) > 32:
            found = "..." + found[-29:]
        lines.append(f"{mark:<4} {it['name']:<24} {found:<34} {tag}")
    lines.append("-" * 62)

    missing_req = [i for i in items if i["required"] and not i["ok"]]
    missing_opt = [i for i in items if not i["required"] and not i["ok"]]

    if not missing_req and not missing_opt:
        lines.append("")
        lines.append("✅ 全部就绪，可以直接转写。")
        lines.append("")
        lines.append("下一步：")
        lines.append(f"  {_env.resolve_python()} \\")
        lines.append("    scripts/transcribe.py --input \"<视频URL或本地文件>\" --language zh")
        return "\n".join(lines)

    if missing_req:
        lines.append("")
        lines.append(f"❌ 缺少 {len(missing_req)} 个必需依赖，需先安装：")
        for it in missing_req:
            lines.append("")
            lines.append(f"  ▸ {it['name']}（{it['need']}）")
            for c in it["fix"]:
                lines.append(f"      {c}")
    if missing_opt:
        lines.append("")
        lines.append("🟡 可选依赖（按需安装）：")
        for it in missing_opt:
            lines.append(f"  ▸ {it['name']} —— {it['need']}")
            for c in it["fix"]:
                lines.append(f"      {c}")

    lines.append("")
    if installed and missing_req:
        lines.append("⚠️  已尝试自动安装，但依赖仍未就绪。常见于：")
        lines.append("   · 装包成功但与当前系统/芯片不兼容（如非 Apple Silicon 装 mlx-whisper）")
        lines.append("   · 网络中断导致装包不完整")
        lines.append("   排查详见 references/INSTALL.md，或手动执行上方命令查看原始报错。")
    elif installed:
        lines.append("✅ 自动安装完成。")
    else:
        lines.append("👉 自动安装（Python 依赖装进 skill 自带 .venv，不污染全局）：")
        lines.append("   python3 scripts/setup_env.py --install")
    lines.extend(pip_index_hint())
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="video-to-text 环境自检与依赖安装")
    ap.add_argument("--install", action="store_true",
                    help="自动安装缺失的 Python 依赖（装进 .venv）；macOS+brew 时顺带装 ffmpeg")
    ap.add_argument("--json", action="store_true", help="输出 JSON，供 agent 解析")
    ap.add_argument("--print-python", action="store_true",
                    help="只打印应使用的 python 解释器路径")
    ap.add_argument("--no-system", action="store_true",
                    help="--install 时不碰系统级依赖（ffmpeg），只装 Python 包")
    args = ap.parse_args()

    backend = _env.preferred_backend()

    if args.print_python:
        print(_env.resolve_python(backend))
        return 0

    items = [check_python(), check_ffmpeg(), check_ytdlp(),
             check_backend(backend), check_pypinyin()]

    installed_any = False
    failed = []
    if args.install:
        for it in items:
            if it["ok"]:
                continue
            if it.get("pip_pkg"):
                ok, err = pip_install(it["pip_pkg"])
                if ok:
                    installed_any = True
                else:
                    failed.append((it["name"], err))
            elif it["name"] == "ffmpeg" and not args.no_system:
                if can_auto_install_ffmpeg():
                    ok, err = auto_install_system(it)
                    if ok:
                        installed_any = True
                    else:
                        failed.append((it["name"], err or "brew install 失败"))
        # 装完重新体检
        items = [check_python(), check_ffmpeg(), check_ytdlp(),
                 check_backend(backend), check_pypinyin()]

    platform_info = {
        "system": _env.SYSTEM,
        "machine": _env.MACHINE,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "apple_silicon": _env.IS_APPLE_SILICON,
        "backend": backend,
        "model": _env.default_model_tier(backend),
        "venv": _env.venv_dir(),
        "outdir": _env.default_outdir(),
    }

    if args.json:
        print(json.dumps({
            "platform": platform_info,
            "items": items,
            "ready": all(i["ok"] for i in items if i["required"]),
            "python_for_transcribe": _env.resolve_python(backend),
            "failures": failed,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(items, platform_info, installed_any))
        for name, err in failed:
            print(f"\n🔴 {name} 自动安装失败：\n{err}", file=sys.stderr)

    if failed:
        return 2
    ready = all(i["ok"] for i in items if i["required"])
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())

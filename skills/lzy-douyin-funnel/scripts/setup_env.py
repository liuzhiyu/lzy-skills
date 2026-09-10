#!/usr/bin/env python3
# lzy-douyin-funnel 环境体检与安装（与其他 lzy 子技能的 setup_env 约定一致）
# 用法：
#   python3 scripts/setup_env.py            # 只体检，报告缺什么、给出安装命令
#   python3 scripts/setup_env.py --install  # 体检 + 自动安装可自动安装项（jieba 装进技能自带 .venv）
# 退出码：0 全部就绪 / 1 有缺失项 / 2 安装失败
import os
import subprocess
import sys

SELF = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(SELF)
VENV = os.path.join(SKILL, ".venv")


def venv_python():
    if os.name == "nt":
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python")


def check(cmd):
    try:
        return subprocess.run(["which", cmd], capture_output=True).returncode == 0
    except Exception:
        return False


def jieba_ok(py):
    try:
        return subprocess.run([py, "-c", "import jieba"], capture_output=True).returncode == 0
    except Exception:
        return False


def find_jieba_dir():
    """在常见位置搜索已安装的 jieba（纯 Python 包，跨 venv 复制可用）"""
    import glob
    patterns = [
        os.path.expanduser("~/.workbuddy/binaries/python/envs/*/lib/python3.*/site-packages/jieba"),
        os.path.expanduser("~/.claude/skills/*/lib/python3.*/site-packages/jieba"),
        "/opt/homebrew/lib/python3*/site-packages/jieba",
        "/usr/local/lib/python3*/site-packages/jieba",
        os.path.expanduser("~/Library/Python/*/lib/python/site-packages/jieba"),
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def copy_jieba(dst_venv):
    """从已有安装复制 jieba 到目标 venv 的 site-packages（pip 安装失败时的兜底）"""
    import glob
    import shutil
    src = find_jieba_dir()
    if not src:
        return False
    sp = glob.glob(os.path.join(dst_venv, "lib", "python3.*", "site-packages")) or \
        glob.glob(os.path.join(dst_venv, "Lib", "site-packages"))
    if not sp:
        return False
    try:
        shutil.copytree(src, os.path.join(sp[0], "jieba"), dirs_exist_ok=True)
        return jieba_ok(venv_python())
    except Exception:
        return False


def main():
    install = "--install" in sys.argv
    problems = []
    lines = []

    # 1) python3
    py3 = sys.executable or "python3"
    lines.append(f"[ok] Python: {py3}")

    # 2) bsk CLI（无法自动安装）
    if check("bsk"):
        lines.append("[ok] bsk CLI: 已找到")
    else:
        problems.append("bsk")
        lines.append("[缺] bsk CLI：BrowserSkill 未安装（无法自动安装）。"
                     "需先安装 BrowserSkill 并确保 daemon 可用（`bsk session start` 能返回会话）。")

    # 3) jieba：优先技能自带 .venv，其次当前解释器
    vp = venv_python()
    if os.path.exists(vp):
        if jieba_ok(vp):
            lines.append(f"[ok] jieba: 已装在技能 .venv（{vp}）")
        else:
            problems.append("jieba-venv")
            lines.append(f"[缺] jieba: 技能 .venv 存在但缺 jieba（{vp}）")
    elif jieba_ok(py3):
        lines.append(f"[ok] jieba: 当前解释器可用（{py3}）")
    else:
        problems.append("jieba")
        lines.append(f"[缺] jieba: 当前解释器无 jieba（{py3}）"
                     f"{'，可用 --install 装进技能自带 .venv' if not install else ''}")

    print("\n".join(lines))

    if install and problems:
        # 自动安装项：jieba（装进技能自带 .venv，不污染全局）；bsk 无法自动装
        try:
            if not os.path.exists(vp):
                print(f"→ 创建 .venv: {VENV}")
                subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
            print("→ pip install jieba（进 .venv）")
            pip_ok = subprocess.run([vp, "-m", "pip", "install", "-q", "--no-cache-dir", "jieba"]).returncode == 0
            if not pip_ok:
                # pip 对 jieba 的 wheel 解包在部分环境会 EEXIST 失败（pip 25 已知问题）
                # 兜底：从机器上任何已有 jieba 的 venv/site-packages 复制（纯 Python 包，跨 venv 通用）
                print("→ pip 安装失败，尝试从已有环境复制 jieba（纯 Python 包）")
                if not copy_jieba(VENV):
                    raise RuntimeError("pip 安装与复制兜底均失败，请手动安装：pip install jieba")
            print("[ok] jieba 已装进 .venv")
        except Exception as e:
            print(f"[fail] 自动安装失败: {e}")
            sys.exit(2)
        if "bsk" in problems:
            print("[缺] bsk 无法自动安装，请手动安装 BrowserSkill 后重跑体检")
            sys.exit(1)
        problems = [p for p in problems if p == "bsk"]
        if not problems:
            print("✅ 环境就绪")
            sys.exit(0)

    if problems:
        sys.exit(1)
    print("✅ 环境就绪")
    sys.exit(0)


if __name__ == "__main__":
    main()

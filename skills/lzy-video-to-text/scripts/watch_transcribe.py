#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频收件箱自动转写（定时自动化入口）。

监视「待转写视频」目录，对新增的本地视频文件自动：
  1. 本地 Whisper 转写（transcribe.py）
  2. 归档转写稿到输出目录
  3. 把原视频移到「已转写视频」，避免重复处理

由 automation 定时调用；也可手动运行做一次性处理。

目录全部可通过环境变量配置，不含任何硬编码个人路径：
    VIDEO_TO_TEXT_INBOX     待转写视频目录（默认 ./待转写视频）
    VIDEO_TO_TEXT_ARCHIVE   已转写视频目录（默认 ./已转写视频）
    VIDEO_TO_TEXT_OUTDIR    转写稿输出目录（默认 ./transcripts）
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402

_env.ensure_utf8_console()

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE = os.path.join(HERE, "transcribe.py")
SETUP_CMD = f"python3 {os.path.join('scripts', 'setup_env.py')}"

CWD = os.getcwd()
DEFAULT_INBOX = os.path.join(CWD, "待转写视频")
DEFAULT_ARCHIVE = os.path.join(CWD, "已转写视频")

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".ts",
             ".mp3", ".m4a", ".wav", ".aac", ".flac"}


def resolve_dirs(args):
    inbox = args.inbox or os.environ.get("VIDEO_TO_TEXT_INBOX") or DEFAULT_INBOX
    archive = args.archive or os.environ.get("VIDEO_TO_TEXT_ARCHIVE") or DEFAULT_ARCHIVE
    outdir = args.outdir or _env.default_outdir()
    return (os.path.expanduser(inbox), os.path.expanduser(archive),
            os.path.expanduser(outdir))


def main():
    ap = argparse.ArgumentParser(description="批量转写收件箱里的视频")
    ap.add_argument("--inbox", default=None, help="待转写视频目录")
    ap.add_argument("--archive", default=None, help="转写完成后原视频归档目录")
    ap.add_argument("--outdir", default=None, help="转写稿输出目录")
    ap.add_argument("--language", default="zh", help="语言代码，默认 zh")
    ap.add_argument("--model", default=None, help="模型档位（透传给 transcribe.py）")
    ap.add_argument("--timestamps", action="store_true", help="输出带时间戳的分段稿")
    ap.add_argument("--domain", default=None,
                    help="行业词库：shortvideo / health / business（透传给 transcribe.py）")
    ap.add_argument("--glossary", default=None,
                    help="自定义词库文件路径（透传给 transcribe.py）")
    ap.add_argument("--init", action="store_true",
                    help="只创建目录结构并打印路径，不处理文件")
    args = ap.parse_args()

    inbox, archive, outdir = resolve_dirs(args)

    if args.init:
        for d in (inbox, archive, outdir):
            os.makedirs(d, exist_ok=True)
        print(f"待转写视频: {inbox}\n已转写视频: {archive}\n转写稿输出: {outdir}")
        return

    os.makedirs(inbox, exist_ok=True)
    os.makedirs(archive, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    videos = sorted(
        f for f in os.listdir(inbox)
        if os.path.isfile(os.path.join(inbox, f))
        and os.path.splitext(f)[1].lower() in VIDEO_EXT
    )

    if not videos:
        print(f"[watch] 收件箱为空，无新视频。({inbox})", file=sys.stderr)
        return

    py = _env.resolve_python()
    print(f"[watch] 发现 {len(videos)} 个待转写视频", file=sys.stderr)
    done = 0
    for f in videos:
        src = os.path.join(inbox, f)
        title = os.path.splitext(f)[0]
        print(f"[watch] 处理: {f}", file=sys.stderr)
        cmd = [py, TRANSCRIBE, "--input", src, "--outdir", outdir,
               "--title", title, "--language", args.language]
        if args.model:
            cmd += ["--model", args.model]
        if args.timestamps:
            cmd += ["--timestamps"]
        # 词库：显式指定才透传；不传时 transcribe.py 会自己读
        # VIDEO_TO_TEXT_DOMAIN / VIDEO_TO_TEXT_GLOSSARY 环境变量
        if args.domain:
            cmd += ["--domain", args.domain]
        if args.glossary:
            cmd += ["--glossary", args.glossary]
        r = subprocess.run(cmd)
        if r.returncode == 0:
            dest = os.path.join(archive, f"{date.today().strftime('%Y%m%d')}_{f}")
            shutil.move(src, dest)
            done += 1
            print(f"[watch] 完成，原视频已归档: {dest}", file=sys.stderr)
        else:
            print(f"[watch] 失败，保留原文件待重试: {f}", file=sys.stderr)
            if not shutil.which("ffmpeg"):
                print(f"[watch] 提示：未找到 ffmpeg，请先运行 `{SETUP_CMD} --install`",
                      file=sys.stderr)
                break

    print(f"[watch] 本轮处理完成：{done}/{len(videos)}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"[watch] 失败：{e}", file=sys.stderr)
        sys.exit(1)

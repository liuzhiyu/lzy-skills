#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
受登录保护的视频站点（抖音 / 视频号 等）一键转写。

这些站点的视频详情接口需要登录态，yt-dlp 直连会报 403
（"Fresh cookies (not necessarily logged in) are needed"）。
但 browser-skill 驱动的是你本机**已登录**的浏览器，页面能正常加载播放器，于是改用：

    bsk 打开已登录浏览器 → 抓 network 里的真实播放流 CDN 直链
    → curl 下载该直链（绕过 API 鉴权）→ video-to-text 本地转写

前置依赖：`bsk` CLI（来自 browser-skill）。
未安装时本脚本会直接给出安装指引并退出，不会抛出裸 traceback。

用法：
    python3 scripts/protected_site_capture.py --input "<受保护站点视频URL>" \
        [--title "主题"] [--outdir <归档目录>] [--language zh]

例：
    python3 scripts/protected_site_capture.py \
        --input "https://www.douyin.com/video/7675325276112407860" \
        --title "布洛芬用药警示" --outdir "./转写归档"
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402

_env.ensure_utf8_console()

BSK = "bsk"
HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE = os.path.join(HERE, "transcribe.py")
SETUP_CMD = f"python3 {os.path.join('scripts', 'setup_env.py')}"

# 受保护站点的播放流 CDN 特征（命中即认为抓到了直链）。
# 新增站点（如视频号）时在这里补该站的 CDN 域名特征即可。
STREAM_PATTERNS = [
    r"https?://[^\s\"'<>]*douyinvod\.com[^\s\"'<>]*",
    r"https?://[^\s\"'<>]*byteimg\.com[^\s\"'<>]*\.mp4",
    r"https?://[^\s\"'<>]*\.mp4[^\s\"'<>]*",
]

BSK_MISSING = """\
未找到 `bsk` 命令 —— 它是抓取「需要登录的站点」（抖音/视频号等）所必需的。

安装方式：
  1. 在 WorkBuddy 技能市场搜索并安装 **BrowserSkill**（腾讯开源的浏览器自动化技能）
  2. 安装后确保 `bsk` 在你的 PATH 上，且浏览器扩展已连接（扩展弹窗显示绿灯）
  3. 用 `bsk doctor` 自检

不需要转写登录保护站点时，可改用普通模式（支持 YouTube/B站/直链/本地文件）：
  {setup}
  python3 scripts/transcribe.py --input "<视频URL或本地文件>" --language zh
""".format(setup=SETUP_CMD)


def check_bsk():
    if shutil.which(BSK) is None:
        print(BSK_MISSING, file=sys.stderr)
        sys.exit(3)
    # 快速连通性自检：失败不致命，但给出提示
    try:
        r = subprocess.run([BSK, "browsers"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0 and "not connected" in (r.stdout + r.stderr).lower():
            print("🟡 bsk 已安装，但浏览器扩展似乎未连接。\n"
                  "   请打开浏览器确认 BrowserSkill 扩展弹窗显示绿灯，或运行 `bsk doctor`。",
                  file=sys.stderr)
    except Exception:
        pass


def bsk(args, timeout=60):
    try:
        r = subprocess.run([BSK] + args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        print(BSK_MISSING, file=sys.stderr)
        sys.exit(3)
    return r.returncode, r.stdout, r.stderr


def start_session():
    rc, out, err = bsk(["session", "start"])
    if rc != 0:
        raise RuntimeError(
            f"bsk session start 失败: {err.strip()}\n"
            "排查：1) 浏览器扩展是否已连接（弹窗绿灯）  2) 运行 `bsk doctor` 自检")
    sid = out.strip().split()[-1]
    if not re.fullmatch(r"[A-Za-z0-9]{4}", sid or ""):
        m = re.search(r"[A-Za-z0-9]{4}", out)
        sid = m.group(0) if m else None
    if not sid:
        raise RuntimeError(f"无法解析 session id，bsk 输出: {out!r}")
    return sid


def capture_stream_url(sid, url, max_wait=45):
    bsk(["navigate", url, "--session", sid,
         "--wait-until", "domcontentloaded", "--timeout", "30000"])
    deadline = time.time() + max_wait
    while time.time() < deadline:
        rc, out, _ = bsk(["network", "--session", sid, "--limit", "200"], timeout=30)
        for pat in STREAM_PATTERNS:
            m = re.search(pat, out)
            if m:
                return m.group(0)
        time.sleep(2)
    raise RuntimeError(
        "未在限定时间内抓到播放流直链。常见原因：\n"
        "  1) 本机浏览器未登录该站点 → 先在弹出的窗口里登录，再重跑\n"
        "  2) 页面未真正加载播放器 → 可手动确认视频能正常播放\n"
        "  3) 该站点的 CDN 域名不在 STREAM_PATTERNS 里 → 在脚本中补上后重试")


def download(url, out_path, referer=None):
    """带浏览器 UA + Referer 下载，命中 CDN 签名直链的要求。"""
    referer = referer or "https://www.douyin.com/"
    subprocess.run(
        ["curl", "-s", "-L", "--max-time", "180",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
         "-H", f"Referer: {referer}",
         "-o", out_path, url],
        check=True,
    )


def extract_id(url):
    m = re.search(r"(\d{6,})", url)
    return m.group(1) if m else "video"


def main():
    ap = argparse.ArgumentParser(description="受登录保护站点视频 → 本地转写")
    ap.add_argument("--input", required=True, help="受保护站点的视频 URL")
    ap.add_argument("--output", default=None, help="输出 txt 路径")
    ap.add_argument("--outdir", default=None,
                    help="归档目录（与 --title 配合，自动加日期前缀）；"
                         "默认 ./transcripts，可用环境变量 VIDEO_TO_TEXT_OUTDIR 覆盖")
    ap.add_argument("--title", default=None, help="归档标题 / 文件名主题")
    ap.add_argument("--language", default="zh", help="语言代码，默认 zh")
    ap.add_argument("--model", default=None, help="模型档位（透传给 transcribe.py）")
    ap.add_argument("--timestamps", action="store_true", help="输出带时间戳的分段稿")
    ap.add_argument("--domain", default=None,
                    help="行业词库：shortvideo / health / business（透传给 transcribe.py）")
    ap.add_argument("--glossary", default=None,
                    help="自定义词库文件路径（透传给 transcribe.py）")
    args = ap.parse_args()

    check_bsk()

    sid = start_session()
    print(f"[protected_site] bsk session = {sid}", file=sys.stderr)
    try:
        stream = capture_stream_url(sid, args.input)
        print(f"[protected_site] 抓到播放流直链: {stream[:90]}...", file=sys.stderr)

        workdir = tempfile.mkdtemp(prefix="psc_")
        try:
            mp4 = os.path.join(workdir, "video.mp4")
            download(stream, mp4, referer=args.input)
            print(f"[protected_site] 已下载视频: {mp4}", file=sys.stderr)

            base = args.title or extract_id(args.input)
            py = _env.resolve_python()
            cmd = [py, TRANSCRIBE, "--input", mp4, "--language", args.language,
                   "--source", args.input]
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
            outdir = args.outdir or _env.default_outdir()
            cmd += ["--outdir", outdir, "--title", base]
            if args.output:
                cmd += ["--output", args.output]

            print("[protected_site] 转写中...", file=sys.stderr)
            r = subprocess.run(cmd)
            if r.returncode != 0:
                raise RuntimeError(
                    f"transcribe.py 返回非零: {r.returncode}\n"
                    f"若提示依赖缺失，先运行 `{SETUP_CMD} --install`")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    finally:
        bsk(["session", "stop", sid])
        print(f"[protected_site] bsk session {sid} 已关闭", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"[protected_site] 失败：{e}", file=sys.stderr)
        sys.exit(1)

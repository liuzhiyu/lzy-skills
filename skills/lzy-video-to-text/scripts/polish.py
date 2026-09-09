#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
存量稿矫正器：把「已经转写完、错字较多」的稿子按行业词库回炉重修。

和 transcribe.py 的区别：
  transcribe.py  转写时注入热词 —— 治本，但只对**以后**的稿子有效
  polish.py      转写后按词库修 —— 兜底，能救**已经抓完**的存量稿

典型场景：手上有一批抓下来的视频转写稿，行业术语错成一团
（解热症痛药 / 对乙鲜胺基分缓湿片 / 非载体抗炎药），想批量修回来。

设计红线：
  1. 只改错字，不改表达。不删「啊/呢」，不把口语改成书面语，
     不动句式和标点风格 —— 口播稿的语感比「通顺」更值钱。
  2. 默认不覆盖原稿，输出 <原名>_polished.txt，另出一份 diff 报告
     供人工过一眼。确认无误再加 --inplace。
  3. 元信息区（# 注释、- 来源：URL、含 → 的校对提示行）跳过不动。

用法：
    # 单文件，输出 _polished 版本 + diff 报告
    python3 scripts/polish.py --input 稿子.txt --domain drug

    # 批量（目录下所有 txt/md）
    python3 scripts/polish.py --input 转写归档/ --domain health,drug

    # 确认后原地覆盖
    python3 scripts/polish.py --input 稿子.txt --domain drug --inplace

    # 只体检不改文件，看会改哪些词
    python3 scripts/polish.py --input 稿子.txt --domain drug --dry-run
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402
import glossary as G  # noqa: E402

_env.ensure_utf8_console()

TEXT_EXT = {".txt", ".md", ".markdown"}

# 需要原样保留、不参与替换的区域
_RE_URL = re.compile(r"https?://[^\s)）】\"']+")
# 校对提示行（"- 错写 → 正确"）本身就是记录错字的，改了就没法对照了
_RE_HINT_LINE = re.compile(r"^\s*[-*]\s*.*[→>].*$")


def log(msg):
    _env.log(msg)


def bootstrap_if_needed():
    """
    拼音兜底依赖 pypinyin。当前解释器没有、但 skill 自带 .venv 里有，
    就切到 venv 解释器重跑，保证 --domain 的纠错能力和 transcribe.py 一致。
    """
    if os.environ.get("V2T_BOOTSTRAPPED") == "1":
        return
    try:
        import pypinyin  # noqa: F401
        return
    except ImportError:
        pass
    venv = _env.venv_dir()
    py = _env.venv_python(venv)
    if not os.path.exists(py):
        return  # 没 venv 就降级为「只做显式映射」，仍然可用
    try:
        has = _env.venv_has_module(venv, "pypinyin")
    except Exception:
        has = False
    if not has:
        return
    log("当前解释器缺 pypinyin，切换到 skill 自带环境以启用拼音兜底")
    r = subprocess.run([py, os.path.abspath(__file__)] + sys.argv[1:],
                       env=dict(os.environ, V2T_BOOTSTRAPPED="1"))
    sys.exit(r.returncode)


def split_protected(line):
    """
    把一行拆成可替换文本 + 保护区（URL）。
    返回 (拼接模板, [可替换片段...]) —— 用占位符把 URL 挖出来，替换完再塞回去。
    """
    slots, placeholder = [], "\x00{}\x00"

    def _stash(m):
        slots.append(m.group(0))
        return placeholder.format(len(slots) - 1)

    return _RE_URL.sub(_stash, line), slots


def restore_protected(text, slots):
    for i, s in enumerate(slots):
        text = text.replace("\x00{}\x00".format(i), s)
    return text


def is_protected_line(line):
    """元信息行不参与纠错：Markdown 标题/注释、校对提示行。"""
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if _RE_HINT_LINE.match(line):
        return True
    # 纯链接行 / 元信息行（"- 来源：xxx"）
    if s.startswith("- ") and ("：" in s or ":" in s) and len(s) < 80:
        return True
    return False


def polish_text(text, gloss, use_pinyin=True):
    """
    逐行矫正。受保护的行原样返回。
    返回 (新文本, [(错写, 正确, 次数, 方式), ...])
    """
    out_lines, total_hits = [], {}
    for line in text.split("\n"):
        if is_protected_line(line):
            out_lines.append(line)
            continue
        workable, slots = split_protected(line)
        fixed, hits = gloss.correct(workable, use_pinyin=use_pinyin)
        fixed = gloss.tidy_spaces(fixed)
        out_lines.append(restore_protected(fixed, slots))
        for wrong, right, n, how in hits:
            key = (wrong, right, how)
            total_hits[key] = total_hits.get(key, 0) + n
    merged = [(w, r, n, h) for (w, r, h), n in total_hits.items()]
    merged.sort(key=lambda x: -x[2])
    return "\n".join(out_lines), merged


def collect_inputs(path):
    """输入可以是单文件，也可以是目录（递归找 txt/md）。"""
    path = os.path.expanduser(path)
    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        found = []
        for root, _dirs, files in os.walk(path):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in TEXT_EXT:
                    found.append(os.path.join(root, f))
        return found
    raise SystemExit(f"找不到输入路径: {path}")


def build_report(path, hits, gloss, use_pinyin):
    """生成人能一眼扫完的 diff 报告。"""
    lines = [
        f"# 矫正报告 · {os.path.basename(path)}",
        "",
        f"- 词库：{gloss.describe()}",
        f"- 拼音兜底：{'开' if use_pinyin else '关'}",
        f"- 共修正 **{sum(h[2] for h in hits)}** 处，涉及 **{len(hits)}** 个词",
        "",
    ]
    if not hits:
        lines.append("未发现命中词库的错字。若仍有错，多半是词库没覆盖该子领域，")
        lines.append("把「错写 = 正确」补进对应的 glossary/*.txt 即可。")
        lines.append("")
        return "\n".join(lines)

    lines.append("| 错写 | 修正为 | 次数 | 命中方式 | 风险 |")
    lines.append("|---|---|---:|---|---|")
    for wrong, right, n, how in hits:
        risk = "低（词库显式映射）" if how == "词库" else "中（同音推断，建议人工确认）"
        lines.append(f"| {wrong} | **{right}** | {n} | {how} | {risk} |")
    lines.append("")
    lines.append("> 「拼音」方式是把读音相同但字形不同的片段判为错字，")
    lines.append("> 命中率高但有误伤可能，改稿前请过一遍上表。")
    return "\n".join(lines)


def main():
    bootstrap_if_needed()
    ap = argparse.ArgumentParser(
        description="存量转写稿按行业词库回炉矫正（只改错字，不改表达）")
    ap.add_argument("--input", required=True,
                    help="待矫正的 txt/md 文件，或包含它们的目录")
    ap.add_argument("--domain", default=_env_default_domain(),
                    help="行业词库，可逗号叠加：health,drug。"
                         f"内置：{', '.join(G.DOMAINS)}")
    ap.add_argument("--glossary", default=None,
                    help="自定义词库文件（格式见 glossary/*.txt），与 --domain 叠加")
    ap.add_argument("--inplace", action="store_true",
                    help="原地覆盖原稿（默认输出 <原名>_polished.txt）")
    ap.add_argument("--suffix", default="_polished",
                    help="非 inplace 模式下的输出后缀，默认 _polished")
    ap.add_argument("--report", action="store_true",
                    help="额外输出一份 Markdown 矫正报告")
    ap.add_argument("--no-pinyin", action="store_true",
                    help="关掉拼音兜底，只做词库显式映射（零误伤，但漏网多）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印会改哪些词，不写文件")
    args = ap.parse_args()

    try:
        gloss = G.Glossary.load(domain=args.domain, path=args.glossary)
    except ValueError as e:
        raise SystemExit(str(e))
    if not gloss:
        raise SystemExit(
            "没有启用任何词库。用 --domain 指定行业，或 --glossary 指定词库文件。\n"
            f"内置词库：{', '.join(G.DOMAINS)}")

    use_pinyin = not args.no_pinyin
    files = collect_inputs(args.input)
    if not files:
        raise SystemExit(f"目录里没有 txt/md 文件: {args.input}")

    log(f"{gloss.describe()}")
    log(f"待处理 {len(files)} 个文件，拼音兜底={'开' if use_pinyin else '关'}")

    total = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
        fixed, hits = polish_text(original, gloss, use_pinyin=use_pinyin)
        n = sum(h[2] for h in hits)
        total += n

        if args.dry_run:
            log(f"\n[体检] {path}")
            for wrong, right, cnt, how in hits:
                log(f"   {wrong}  ->  {right}   x{cnt}  ({how})")
            if not hits:
                log("   未命中（该子领域词库可能未覆盖）")
            continue

        if n == 0:
            log(f"[跳过] {os.path.basename(path)} —— 无命中")
            continue

        if args.inplace:
            out_path = path
        else:
            base, ext = os.path.splitext(path)
            out_path = f"{base}{args.suffix}{ext}"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(fixed)
        log(f"[完成] {os.path.basename(out_path)}  修正 {n} 处")

        if args.report:
            rp = (os.path.splitext(out_path)[0] + "_矫正报告.md")
            with open(rp, "w", encoding="utf-8") as f:
                f.write(build_report(path, hits, gloss, use_pinyin))
            log(f"[报告] {os.path.basename(rp)}")

    log(f"\n共修正 {total} 处。")
    if not args.inplace and not args.dry_run:
        log("原稿未改动。确认无误后可加 --inplace 覆盖。")


def _env_default_domain():
    return G.default_domain()


if __name__ == "__main__":
    main()

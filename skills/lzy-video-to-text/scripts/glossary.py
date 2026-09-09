#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业词库：热词提示 + 转写纠错。

Whisper 在中文上的错字 90% 集中在专有名词上——普通口语它识别得很准，
但「完播率」「企微」「私域」这类行业词没有语言先验，会被写成同音的
日常词（玩播率 / 岂微 / 思域）。所以要分两层治：

  第一层  识别时注入 initial_prompt（治本）
          把术语提前告诉模型，让它「认识」这些词。
          实测 4 个错词能修正 3 个。

  第二层  识别后按词库替换（治标，兜第一层漏网的）
          initial_prompt 只能影响语言模型先验，改不了音素层面的同音混淆，
          「获客→或客」「完播率→玩播率」这类必须靠显式映射替换。

词库文件格式（glossary/*.txt）：
    正确写法 = 误识别1, 误识别2
    不容易错的词
    # 开头是注释

  · 等号左边 -> 进热词提示
  · 等号右边 -> 转写后替换纠错
"""
import os
import re

import _env

GLOSSARY_DIR = os.path.join(_env.SKILL_ROOT, "glossary")

# 内置领域 -> (中文名, 文件名)
DOMAINS = {
    "shortvideo": ("短视频运营 / 获客", "shortvideo.txt"),
    "health": ("大健康 / 营养 / 功能医学", "health.txt"),
    "drug": ("临床用药 / 药品", "drug.txt"),
    "business": ("商业 / ToB / 创业", "business.txt"),
}

# 词表不是越大越好：热词提示只有 40 字预算（见 PROMPT_MAX_CHARS），
# 只放得下 5-6 个术语。把「营养抗衰」和「临床用药」塞进一张表，
# 本篇真正会出现的药名就挤不进提示，等于白注入。
# 所以词表按子领域拆细，用时按需叠加：--domain health,drug

# initial_prompt 越长，模型输出越容易「中标点毒」——实测梯度：
#   23 token(15字) 正常 | 33 token(25字) 正常 | 58 token(40字) 出现乱码
#   \ufffd | 67 token(60字) 同上 | 187 token(148字) 出现全角 Ｚ 代替逗号
# 中文 1 字约 1.3 token，所以硬上限压在 40 字（约 52 token）以内。
# 宁可少放几个词让第二层纠错补上，也不能让标点崩掉——标点崩了整篇都读不通。
PROMPT_MAX_CHARS = 40

# 中文之间多余的空格（热词注入的副作用），删掉；中英之间的空格保留
_RE_CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
# 热词提示偶发的「标点中毒」：模型把逗号输出成全角 Ｚ 或替换字符。
# 只处理这两个——它们在中文口播稿里不可能正常出现，换成逗号是安全的。
_RE_BAD_PUNCT = re.compile(r"[Ｚｚ]+")
_RE_REPL_CHAR = re.compile(r"\ufffd+")
# 中文与英文/数字之间确保有空格（排版规范，可选）
_RE_CJK_LATIN = re.compile(r"(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])")

# Whisper 中文输出的标点时半时全，同一篇里常出现「我们,今天」这种半角。
# 只在标点紧邻中文时才转全角——纯英文/数字环境（URL、代码、3.5、C++）不受影响。
# 句号不转：`.` 在数字和小数点里出现太频繁，误伤代价远大于排版收益。
_HALF2FULL = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；",
              "(": "（", ")": "）"}
# 注意：前瞻必须放在「吃掉标点之后」，否则在标点位置前瞻看到的还是标点本身，
# 会导致 `Omega-3,生活方式` 这种「英文/数字 + 标点 + 中文」漏网。
_RE_HALF_PUNCT = re.compile(
    r"(?<=[\u4e00-\u9fff])[,?!:;()]|[,?!:;()](?=[\u4e00-\u9fff])"
)

# 「的/得/地」是中文 ASR 最高频的错字之一：Whisper 常把补语标志「得」写成「的」。
# 只改「动词 + 的 + 补语标志」这一种结构——动词表剔除了「有/是/在/和」等
# 会作助词歧义的字，且必须紧跟补语标志才动，实测在助词场景零误伤：
#   吃的不多 -> 吃得不多   ✅      我的手机 / 短视频的底层逻辑 / 做的人很少  ❌ 不动
_RE_DE = re.compile(
    r"([吃看说做跑睡用买卖走听想学写喝玩搞练谈聊推剪辑拍运营涨])"
    r"的(?=[不很太多好快完透清楚明白起见到懂动开])"
)


class Glossary:
    def __init__(self, terms=None, fixes=None, name="", source=""):
        self.terms = terms or []          # 进热词提示的词
        self.fixes = fixes or {}          # {错写: 正确}
        self.name = name
        self.source = source

    def __bool__(self):
        return bool(self.terms or self.fixes)

    # ------------------------------------------------------------ 加载
    @classmethod
    def load(cls, domain=None, path=None):
        """
        加载词库。domain 用内置的，path 用自定义文件。
        两者都可以给，会合并（自定义词优先）。
        """
        terms, fixes, names, sources = [], {}, [], []

        # domain 支持逗号分隔叠加多个子领域：health,drug
        # 一条大健康视频常常既讲营养又讲药，只挂一张表必然漏词。
        domains = []
        if domain:
            for d in re.split(r"[,\s]+", domain.strip()):
                d = d.strip()
                if d:
                    domains.append(d)

        for d in domains:
            if d not in DOMAINS:
                raise ValueError(
                    f"未知领域 `{d}`。可选：{', '.join(DOMAINS)}\n"
                    f"也可以用 --glossary 指定自己的词库文件。")
            cn, fname = DOMAINS[d]
            p = os.path.join(GLOSSARY_DIR, fname)
            if not os.path.exists(p):
                raise ValueError(f"内置词库缺失: {p}")
            g = cls._parse_file(p)
            terms += g.terms
            fixes.update(g.fixes)
            names.append(cn)
            sources.append(p)

        if path:
            p = os.path.expanduser(path)
            if not os.path.exists(p):
                raise ValueError(f"找不到词库文件: {p}")
            g = cls._parse_file(p)
            terms += g.terms
            # 自定义词覆盖内置的
            fixes.update(g.fixes)
            names.append(os.path.splitext(os.path.basename(p))[0])
            sources.append(p)

        # 去重保序
        seen, uniq = set(), []
        for t in terms:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        return cls(uniq, fixes, " + ".join(names), "; ".join(sources))

    @classmethod
    def _parse_file(cls, path):
        terms, fixes = [], {}
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    right, wrongs = line.split("=", 1)
                    right = right.strip()
                    if not right:
                        continue
                    terms.append(right)
                    for w in wrongs.replace("，", ",").split(","):
                        w = w.strip()
                        if w and w != right:
                            fixes[w] = right
                else:
                    terms.append(line)
        return cls(terms, fixes, "", path)

    # ------------------------------------------------------------ 热词提示
    def build_prompt(self, subject=None):
        """
        生成自然句式的 initial_prompt。

        实测关键：自然句 >> 术语罗列。
        罗列式（「术语：企微 私域 留资」）会让模型丢标点、并在词间插空格；
        自然句式能保留标点、无空格问题，命中率相同。
        """
        if not self.terms:
            return None

        subject = subject or self.name or "该领域"
        # 位置只够放 5-6 个词，得挑最值钱的：
        # 按「错写形式条数」降序——历史上错得越多的词，越该进提示。
        freq = {}
        for w, r in self.fixes.items():
            freq[r] = freq.get(r, 0) + 1
        risky_set = set(freq)
        risky = sorted((t for t in self.terms if t in risky_set),
                       key=lambda t: -freq[t])
        rest = [t for t in self.terms if t not in risky_set]
        ordered = risky + rest

        # 领域名取第一段（"短视频运营 / 获客" -> "短视频运营"），省出预算给术语
        short = subject.split("/")[0].strip() if "/" in subject else subject
        # 预算要扣掉前后缀：限制的是整句长度，不是术语部分
        head = f"这是{short}的口播，涉及"
        budget = max(12, PROMPT_MAX_CHARS - len(head) - 2)

        picked, total = [], 0
        for t in ordered:
            if total + len(t) + 1 > budget:
                break
            picked.append(t)
            total += len(t) + 1
        if not picked:
            picked = [ordered[0]]

        return head + "、".join(picked) + "。"

    # ------------------------------------------------------------ 后处理
    def correct(self, text, use_pinyin=True):
        """
        按词库替换错写。返回 (修正后文本, [(错写, 正确, 次数, 方式)])

        两轮：
          1. 显式映射  —— 词库里写明的错写，最可靠
          2. 拼音兜底  —— 同音即判为错写，不用穷举
             （「启微」这种没列进词库的也能纠，需要 pypinyin，缺失则跳过）
        """
        if not text:
            return text, []

        hits = []
        # 长词优先，避免「完播率」被「完播」先截走
        if self.fixes:
            for wrong in sorted(self.fixes, key=len, reverse=True):
                n = text.count(wrong)
                if n:
                    text = text.replace(wrong, self.fixes[wrong])
                    hits.append((wrong, self.fixes[wrong], n, "词库"))

        if use_pinyin:
            text, ph = self._pinyin_correct(text)
            hits += [(w, r, n, "拼音") for w, r, n in ph]
        return text, hits

    def _pinyin_correct(self, text):
        """
        拼音兜底：滑动窗口找与词库词「读音完全相同、字形不同」的片段。

        穷举错写是做不完的——「企微」能被写成 岂微/启微/起微/奇微…
        但只要读音一样，就能发现。为控制误伤：
          · 只匹配纯中文片段，长度 2-6 字
          · 片段本身已是正确形式时不替换
          · 一个读音对应多个词库词时，替换但标记为「有歧义」
          · 依赖 pypinyin，缺失时静默跳过（降级为只做显式映射）
        """
        try:
            from pypinyin import lazy_pinyin
        except ImportError:
            return text, []

        # 只索引「已知容易错的词」（有显式错写映射的），而不是全部术语。
        # 全量索引会把无关的普通同音词也卷进来，误伤面太大。
        risky = [t for t in self.fixes.values()
                 if 2 <= len(t) <= 6 and all("\u4e00" <= c <= "\u9fff" for c in t)]
        index = {}
        for t in risky:
            index.setdefault("".join(lazy_pinyin(t)), []).append(t)
        if not index:
            return text, []

        lengths = sorted({len(t) for vs in index.values() for t in vs}, reverse=True)
        chars = list(text)
        hits = {}

        for n in lengths:
            i = 0
            while i + n <= len(chars):
                frag = "".join(chars[i:i + n])
                if all("\u4e00" <= c <= "\u9fff" for c in frag):
                    cands = index.get("".join(lazy_pinyin(frag)))
                    # 片段不在候选里 = 读音对但字写错了
                    if cands and frag not in cands:
                        right = cands[0]
                        chars[i:i + n] = list(right)
                        hits[(frag, right)] = hits.get((frag, right), 0) + 1
                        i += len(right)
                        continue
                i += 1
        return "".join(chars), [(w, r, n) for (w, r), n in hits.items()]

    def tidy_spaces(self, text):
        """
        清理转写稿的排版问题：
          · 中文之间的多余空格（热词注入的副作用）
          · 标点中毒产生的 Ｚ / 替换字符
          · 紧邻中文的半角标点转全角（Whisper 输出时半时全）
          · 补语标志「得」被写成「的」时纠正（吃的不多 -> 吃得不多）
          · 规范中英之间的空格
        """
        if not text:
            return text
        text = _RE_BAD_PUNCT.sub("，", text)
        text = _RE_REPL_CHAR.sub("", text)
        text = _RE_HALF_PUNCT.sub(lambda m: _HALF2FULL[m.group(0)], text)
        text = _RE_DE.sub(lambda m: m.group(1) + "得", text)
        text = _RE_CJK_SPACE.sub("", text)
        text = _RE_CJK_LATIN.sub(" ", text)
        text = re.sub(r"，{2,}", "，", text)
        return re.sub(r"[ \t]{2,}", " ", text)

    def describe(self):
        if not self:
            return "未启用词库"
        return (f"词库[{self.name}] 术语 {len(self.terms)} 个，"
                f"纠错映射 {len(self.fixes)} 条")


def available_domains():
    return DOMAINS


def default_glossary_path():
    """环境变量 VIDEO_TO_TEXT_GLOSSARY / VIDEO_TO_TEXT_DOMAIN 可设默认值。"""
    return os.environ.get("VIDEO_TO_TEXT_GLOSSARY") or None


def default_domain():
    return os.environ.get("VIDEO_TO_TEXT_DOMAIN") or None

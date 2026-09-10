# -*- coding: utf-8 -*-
"""解析抖音视频详情页评论 -> 结构化，并识别客户咨询 / 留资钩子信号"""
import json, re, os, sys, glob, collections

TIME = re.compile(r"^(刚刚|\d+\s*秒前|\d+\s*分钟前|\d+\s*小时前|昨天|前天|\d+\s*天前|\d+\s*周前|\d+\s*个月前|\d+\s*年前|\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2})(\s*·\s*\S+)?$")
NUM = re.compile(r"^[\d.]+\s*[万wW]?$")
REPLY = re.compile(r"^展开(\d+)条回复$")
FIXED = {"分享", "回复", "...", "举报", "更多", "翻译", "作者", "置顶"}

# ============ 分类体系 ============
# A1 强意向线索（真金白银：问价 / 要联系方式 / 求服务 / 求合作）
# A2 求方法求资料（弱意向但可转化）
# A3 钩子留资（评论区暗号）
# A4 AI 截流（@豆包 等 AI 助手，需求真实但流向 AI 而非博主）
# B  同行共鸣（自报身份陈述、讨论、吐槽，非客户）
# D  求带求学（同行/学员线索）
# C  泛互动

AI_BOT = re.compile(r"@?\s*(豆包|元宝|元包|kimi|Kimi|豆包AI|AI助手|deepseek|DeepSeek|纳米AI|智谱|文心|通义|即梦|扣子)")
ASK_VERB = re.compile(r"(帮我|给我|替我|教我|带我|怎么|如何|咋样|咋|能不能|可不以|可(不|否)|可以吗|求|想要|发我|生成|写(一)?个|出个|来个|整理|总结|做(一)?个|弄|搞|搞一?个|试试|想要)")

# ---------- A1 强意向客户线索 ----------
A1_PAT = [
    (r"(多少(钱|米|银子|块)|怎么收费|收费(标准|多少)|报价|贵不贵|价(格)?(多少|如何|怎样|太贵|偏高)|费用(多少|怎么)|一年多少|一个月多少|收多少钱)", "问价"),
    (r"(联系方式|电话|手机号|加个?微|加个?v|加你|留个?方式|怎么加你|怎么联系(你|到)|怎么找你|哪里找你)", "求联系方式"),
    (r"(已?私信(你|了)?|私你了|已?私聊你|加了你|关注你了.{0,6}(私|发))", "求私信"),
    (r"(帮我|给我|替我)[^。!？\n]{0,10}(做|拍|策划|设计|弄|诊断|看看|出个|搞|写|搭|运营|投)", "求服务"),
    (r"(合作|加盟|代理|招商|对接|接(单|活|项目)|收(不收|吗)|做(不做|吗)|接(不接|吗))", "求合作"),
    (r"(怎么|如何)[^。!？\n]{0,6}(联系|找到你|找你|咨询|合作|加入|报名|买|下单|开通)", "求对接"),
    (r"(我想|我要|我需要|我也想|打算|准备)[^。!？\n]{0,12}(做|搞|投|开|买|弄|找|学|参加|报名|加入)", "明确意向"),
    (r"(上门|到店|来我(们)?这|派单|能不能来)", "求上门"),
]
# ---------- A2 求方法 / 求资料 ----------
A2_PAT = [
    (r"(有没有|有没|求|想要|发我|给我|来一份|分享下)[^。!？\n]{0,10}(资料|模板|话术|方案|课程|教程|清单|表格|脚本|文案|SOP|工具|链接|地址|名单|系统|软件|小程序|表|一份)", "求资料"),
    (r"(怎么|如何|在哪|哪里)[^。!？\n]{0,8}(弄|做|搞|设置|操作|下载|获取|领取|安装|开通|找到|开始|起号|投|引流|获客)", "求方法"),
    (r"(这个|那个)[^。!？\n]{0,8}(怎么|咋|如何)[^。!？\n]{0,8}(弄|做|搞|弄的|来的|买的|设置|操作|实现)", "求工具"),
    (r"(能(不能|否)?|可(不|以))[^。!？\n]{0,4}(发|分享|给我)[^。!？\n]{0,6}(一|份|个|下)", "求发资料"),
]
# ---------- B 同行共鸣（自报身份但无求助动作） ----------
B_PAT = [
    (r"(我(也|就|现在)?(是|在|这边|们)?[^。!？\n]{0,14}(做|开|干|搞|经营|卖|从事|负责)[^。!？\n]{0,16})", "同行自述"),
    (r"^(就是|说的就是我|我也是|我也是这样|我们也是|同款|一样|确实如此|感同身受|我已经干|我干了|我做了)\S{0,20}", "同行共鸣"),
    (r"(已经干了|干了\d+年|做了\d+年|入行\d+年|我这边也是|我们这边)", "同行共鸣"),
    (r"(求带|带带我|带我|带上我|求教|请教|拜师|收徒|收我|带一个)", "求带"),
    (r"(教(教)?我|讲讲|讲一下|细讲|详细讲|展开讲讲|多讲点|再讲讲|能不能讲讲|再详细讲讲)", "求学"),
    (r"(怎么入门|怎么开始|新手怎么|小白怎么|0基础|零基础|从哪开始|在哪学|怎么学)", "求学"),
    (r"(有(没有)?课|开课|报名|怎么报名|线下课|训练营|社群|进群|拉我|拉群|收学员)", "求课程"),
]
# ---------- A3 钩子留资 ----------
A3_PAT = [
    (r"^(扣|打|评论|留)\s*\S{0,6}$", "暗号动作"),
    (r"(评论区|下方|后台)[^。!？\n]{0,6}(扣|打|留|说|回复)", "暗号动作"),
]
# ---------- C 泛互动 ----------
C_PAT = [
    (r"(谢谢|感谢|学到|受教|受用|认同|认可|支持|点赞|说(得|的)?(太|真|很)?(好|对|透)|讲(得|的)?(真|太|很)?好|有道理|确实|厉害|牛|666|👍|💪|👏|优秀|太对了|没错|真实|扎心|不错|赞|干货|到位|通透|高级)", "泛认同"),
    (r"(沙发|板凳|路过|打卡|前排|来了|来咯|顶|冲)", "泛互动"),
    (r"(互关|互粉|互赞|串门|回访|已赞|求回|抱团)", "互刷"),
]

# 常见留资暗号短词（当同视频重复出现 >=3 次时判定为钩子）
HOOK_WORDS = {"想要", "需要", "求", "已关", "报名", "领", "资料", "1", "666", "已私",
              "求带", "来了", "是", "对", "打卡", "求资料", "已关注", "要", "有", "我",
              "领资料", "求分享", "给我", "发我", "想要资料", "学习", "求教", "安排"}


def is_short_code(t):
    """短暗号：纯数字/纯短英文/常见钩子词，长度<=8"""
    t = t.strip()
    if not t or len(t) > 8:
        return False
    if re.fullmatch(r"[0-9\s]+", t):
        return True
    if re.fullmatch(r"[a-zA-Z0-9]{1,6}", t):
        return True
    return t in HOOK_WORDS


def detect_hook(comments):
    """检测视频是否设置了留资钩子：返回 (hook_word, count) 或 None"""
    c = collections.Counter(x["content"].strip() for x in comments if x.get("content"))
    for w, n in c.most_common(30):
        if n >= 3 and is_short_code(w):
            return (w, n)
    return None


def configure(cfg=None):
    """用 config 模块覆盖分类模式（A1/A2/B/A3/C 话术与 HOOK_WORDS）。
    cfg 为 None 时不改动（保持当前模块内置的通用 B 端默认值）。
    适配新搜索词：在 config_<词>.py 中定义这些变量，引擎调用 configure(cfg) 即可注入。"""
    if cfg is None:
        return
    for name in ("A1_PAT", "A2_PAT", "B_PAT", "A3_PAT", "C_PAT", "HOOK_WORDS"):
        if hasattr(cfg, name):
            globals()[name] = getattr(cfg, name)


def classify(text, hook_word=None):
    t = (text or "").strip()
    if not t:
        return "", []
    # 1) 钩子暗号
    if hook_word and t.strip() == hook_word:
        return "A3", ["钩子留资"]
    # 2) AI 截流：@豆包 等，需求真实但流向 AI
    if AI_BOT.search(t[:12]):
        return "A4", ["@AI代写"]
    # 3) 强意向线索
    for rx, tag in A1_PAT:
        if re.search(rx, t, re.I):
            return "A1", [tag]
    # 5) 求方法 / 求资料（含求助动词才成立）
    for rx, tag in A2_PAT:
        if re.search(rx, t, re.I):
            return "A2", [tag]
    # 6) 同行共鸣 / 求带求学
    for rx, tag in B_PAT:
        if re.search(rx, t, re.I):
            # 自报身份 + 明确求助动词 -> 升级为方法类线索
            if tag.startswith("同行") and ASK_VERB.search(t):
                for rx2, tag2 in A2_PAT:
                    if re.search(rx2, t, re.I):
                        return "A2", [tag2]
                return "A1", ["自报身份+求助"]
            return "B", [tag]
    # 7) 暗号动作兜底
    for rx, tag in A3_PAT:
        if re.search(rx, t, re.I):
            return "A3", [tag]
    # 8) 泛互动兜底（有认同词且无求助动词）
    if not ASK_VERB.search(t):
        for rx, tag in C_PAT:
            if re.search(rx, t):
                return "C", [tag]
    return "", []


def parse_comment(lines):
    if not lines:
        return None
    author = lines[0]
    tidx = -1
    for i, s in enumerate(lines):
        if i == 0:
            continue
        if TIME.match(s):
            tidx = i
            break
    if tidx > 0:
        body_parts = [s for s in lines[1:tidx] if s not in FIXED]
        time_loc = lines[tidx]
        rest = lines[tidx + 1:]
    else:
        body_parts = [s for s in lines[1:] if s not in FIXED and not NUM.match(s) and not REPLY.match(s)]
        time_loc = ""
        rest = lines[1:]
    likes, replies, is_author = 0, 0, False
    for s in rest:
        if s in FIXED:
            continue
        if REPLY.match(s):
            replies = int(REPLY.match(s).group(1))
        elif NUM.match(s) and likes == 0:
            m = re.match(r"^([\d.]+)\s*(万|w|W)?$", s)
            v = float(m.group(1))
            if m.group(2):
                v *= 10000
            likes = int(v)
        elif s in ("作者", "置顶"):
            is_author = True
    content = " ".join(body_parts).strip()
    return dict(author=author, content=content, time=time_loc, likes=likes,
                replies=replies, is_author=is_author)


def load_dir(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.json")):
        vid = os.path.basename(p).replace(".json", "")
        try:
            out[vid] = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
    return out


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hktest"
    data = load_dir(d)
    for vid, v in list(data.items()):
        cs = [x for x in (parse_comment(c) for c in v.get("comments", [])) if x]
        hook = detect_hook(cs)
        print(f"== {vid}  n={len(cs)}  hook={hook}")
        for c in cs[:10]:
            cls, tag = classify(c["content"], hook[0] if hook else None)
            print(f"   [{cls or '-'}] {','.join(tag):<8} | 赞{c['likes']:>3} | {c['author'][:12]:<12} | {c['content'][:56]}")
        print()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 chat.jsonl 提取"对方"的说话风格，生成人设卡草稿。

用法:
    python3 persona.py chat.jsonl --name 阿澈 -o persona-draft.md
    python3 persona.py chat.jsonl --name 阿澈 --who them --samples 12

输出是 Markdown：前半部分是统计（脚本算的），后半部分是空位（模型/你补的）。
只依赖标准库。
"""
import argparse
import datetime
import json
import re
import statistics
import sys

FMT = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"]

TAIL = "啊吧呢嘛呗哦咯呀啦哈嘿嗯么哇诶"
EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "\u2b00-\u2bff" "]"
)
BRACKET_EMOJI = re.compile(r"\[[^\[\]]{1,6}\]")
CONFLICT = re.compile(r"别|不要|不用|算了|随便|烦|累|忙|没空|再说|无所谓|不知道|不想|没必要|以后")
PUNCT = {
    "句号": "。", "问号": "?", "感叹号": "!", "省略号": "…", "波浪号": "~", "逗号": "，",
}


def parse_time(s):
    for f in FMT:
        try:
            return datetime.datetime.strptime(str(s), f)
        except (ValueError, TypeError):
            continue
    return None


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            m["text"] = str(m.get("text") or "")
            m["sender"] = str(m.get("sender") or "")
            m["dt"] = parse_time(m.get("time"))
            rows.append(m)
    return rows


def pct(a, b):
    return 0.0 if not b else round(a * 100.0 / b, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--name", default="TA", help="对方在记录里的昵称/代称")
    ap.add_argument("--who", default="them", help="要分析谁：them（默认）/ me / 具体昵称")
    ap.add_argument("--samples", type=int, default=10, help="典型台词条数")
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()

    rows = load(args.input)
    if not rows:
        sys.exit("没有可分析的消息")

    who = args.who
    mine = [r for r in rows if r["sender"] == who]
    if not mine and who == "them":
        # 记录里用的是昵称，没有 me/them 标签：把非 me 里最多的那个人当成"对方"
        from collections import Counter

        others = [r for r in rows if r["sender"] not in ("me", "我", "")]
        if others:
            who = Counter(r["sender"] for r in others).most_common(1)[0][0]
            mine = [r for r in rows if r["sender"] == who]
            print("提示: 用昵称 %s 作为「对方」" % who, file=sys.stderr)
    if not mine:
        sys.exit("没有找到 %s 的消息（检查 sender 字段）" % who)

    n = len(mine)
    lens = [len(r["text"]) for r in mine]
    texts = [r["text"] for r in mine if r["text"].strip()]
    n_t = len(texts) or 1

    # 标点习惯
    end_punct = {k: 0 for k in PUNCT}
    for t in texts:
        tail = t.rstrip()
        for k, ch in PUNCT.items():
            if tail.endswith(ch) or (k == "省略号" and tail.endswith("...")):
                end_punct[k] += 1
    no_punct = sum(1 for t in texts if t.rstrip() and t.rstrip()[-1] not in "。！？!?…~～.")

    # 语气词结尾
    tail_words = {}
    for t in texts:
        s = re.sub(r"[。！？!?…~～\.\s]+$", "", t.strip())
        if s and s[-1] in TAIL:
            tail_words[s[-1]] = tail_words.get(s[-1], 0) + 1

    # 表情
    n_emoji = sum(len(EMOJI.findall(t)) for t in texts)
    n_bracket = sum(len(BRACKET_EMOJI.findall(t)) for t in texts)

    # 高频片段
    cnt = {}
    for t in texts:
        for run in re.findall(r"[\u4e00-\u9fa5]+", t):
            for L in (2, 3):
                for i in range(len(run) - L + 1):
                    s = run[i:i + L]
                    cnt[s] = cnt.get(s, 0) + 1
    phrases = [w for w, c in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:14] if c >= 3]

    # 回复延迟（对方回我的间隔）
    lat = []
    prev = None
    for r in rows:
        if r["dt"] is None:
            continue
        if r["sender"] == "me":
            prev = r
        elif prev is not None and r["dt"] >= prev["dt"]:
            gap = (r["dt"] - prev["dt"]).total_seconds()
            if 0 < gap <= 12 * 3600:
                lat.append(gap)
            prev = None

    # 连发
    streak = best = 0
    prev = None
    for r in rows:
        if prev is not None and r["sender"] == prev:
            streak += 1
        else:
            streak = 1
        prev = r["sender"]
        if r["sender"] == who:
            best = max(best, streak)

    # 典型台词：优先中短句、去重
    seen = set()
    samples = []
    for t in sorted(texts, key=lambda x: (abs(len(x) - 12), len(x))):
        key = t
        if key in seen or len(t) < 2:
            continue
        seen.add(key)
        samples.append(t)
        if len(samples) >= args.samples:
            break

    conflict = [t for t in texts if CONFLICT.search(t)][:8]

    span = ""
    timed = [r["dt"] for r in rows if r["dt"]]
    if timed:
        span = "%s → %s" % (timed[0].strftime("%Y-%m-%d"), timed[-1].strftime("%Y-%m-%d"))

    out = []
    w = out.append
    w("# 人设卡 · %s" % args.name)
    w("")
    w("> 由 `persona.py` 从 %d 条消息里提取%s。统计是客观的，解释要你来补。"
      % (n, ("，" + span) if span else ""))
    w("")
    w("## 一、客观统计")
    w("")
    w("| 项目 | 数值 |")
    w("|---|---|")
    w("| 消息数 | %d 条 |" % n)
    w("| 长度中位数 / 均值 / 90分位 | %d / %.1f / %d 字 |"
      % (statistics.median(lens), sum(lens) / n, sorted(lens)[max(int(n * 0.9) - 1, 0)]))
    w("| 单字消息占比 | %s%% |" % pct(sum(1 for x in lens if x <= 2), n))
    w("| 不带句末标点的比例 | %s%% |" % pct(no_punct, n_t))
    w("| 表情 / [表情] | %d 个 / %d 处 |" % (n_emoji, n_bracket))
    if lat:
        w("| 回复我的中位延迟 | %.0f 秒 |" % statistics.median(lat))
    w("| 最多连发 | %d 条 |" % best)
    w("")
    mark = [k for k, v in end_punct.items() if v]
    if mark:
        w("**句末标点**： " + "，".join("%s %s%%" % (k, pct(end_punct[k], n_t)) for k in mark))
    else:
        w("**句末标点**： 几乎不用（%s%% 的消息没有句末标点）" % pct(no_punct, n_t))
    if tail_words:
        w("")
        w("**爱用的语气词结尾**： " + "、".join(
            "%s（%d 次）" % (k, v) for k, v in sorted(tail_words.items(), key=lambda x: -x[1])[:6]))
    if phrases:
        w("")
        w("**高频片段**： " + "、".join(phrases))
    w("")
    w("## 二、典型台词（原样，别改写）")
    w("")
    for s in samples:
        w("> " + s.replace("\n", " / "))
    if conflict:
        w("")
        w("## 三、冲突/推脱时的台词")
        w("")
        for s in conflict:
            w("> " + s.replace("\n", " / "))
    w("")
    w("## 四、需要补全（模型读完后填，或者你直接改）")
    w("")
    w("```")
    w("称呼我：            （TA 平时怎么叫你：全名/外号/什么都不叫）")
    w("说话长度：          （一句话几个字，会不会连发三段）")
    w("标点习惯：          （不用句号 / 爱用省略号 / 全是感叹号）")
    w("口头禅：            ")
    w("生气时：            （变短？变客气？翻旧账？直接不回？）")
    w("心软时：            （会主动找话题？会发长文？会损你一句再和好？）")
    w("回避话题的方式：    （转话题 / 说忙 / 发表情 / 只回嗯）")
    w("绝对不会说的话：    （说这些就 OOC 了）")
    w("雷区：              （提到什么会立刻冷下来）")
    w("```")
    w("")
    w("## 五、边界")
    w("")
    w("- 这是**模拟**，不是 TA 本人；TA 真实的想法只有 TA 能说。")
    w("- 统计只说明 TA 怎么说话，不说明 TA 怎么想；别把语气当承诺。")

    text = "\n".join(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("已写入 %s（%d 条消息）" % (args.output, n), file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()

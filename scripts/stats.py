#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对统一后的 chat.jsonl 做客观统计。

用法:
    python3 stats.py chat.jsonl
    python3 stats.py chat.jsonl --json

只输出数字和事实，不做判断；判断留给模型。
"""
import argparse
import datetime
import json
import re
import statistics
import sys

FMT = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
       "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]


def parse_time(s):
    if not s:
        return None
    s = str(s).strip()
    for f in FMT:
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def fmt_dur(sec):
    if sec < 60:
        return "%d 秒" % sec
    if sec < 3600:
        return "%.0f 分钟" % (sec / 60)
    if sec < 86400:
        return "%.1f 小时" % (sec / 3600)
    return "%.1f 天" % (sec / 86400)


def load(path):
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            m["dt"] = parse_time(m.get("time"))
            m["text"] = str(m.get("text") or "")
            m["sender"] = str(m.get("sender") or "unknown")
            msgs.append(m)
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--me", default="me")
    args = ap.parse_args()

    msgs = load(args.input)
    if not msgs:
        print("没有可统计的消息", file=sys.stderr)
        sys.exit(1)

    me, them = args.me, "them"
    n = len(msgs)
    n_me = sum(1 for m in msgs if m["sender"] == me)
    n_them = sum(1 for m in msgs if m["sender"] == them)
    timed = [m for m in msgs if m["dt"]]

    res = {
        "total": n,
        "me": n_me,
        "them": n_them,
        "other": n - n_me - n_them,
        "with_time": len(timed),
    }

    if timed:
        times = [m["dt"] for m in timed]
        res["start"] = times[0].strftime(FMT[0])
        res["end"] = times[-1].strftime(FMT[0])
        res["span_days"] = round((times[-1] - times[0]).total_seconds() / 86400, 1)
        res["active_days"] = len({t.date() for t in times})
        res["per_active_day"] = round(n / max(res["active_days"], 1), 1)

        hours = {}
        for t in times:
            hours[t.hour] = hours.get(t.hour, 0) + 1
        res["by_hour"] = {str(h): hours[h] for h in sorted(hours)}
        night = sum(v for h, v in hours.items() if h >= 23 or h < 5)
        res["night_ratio"] = round(night / len(times), 3)

        # 回复延迟：对方切换后的间隔（>0 且 <6h 才算"对话中的回复"）
        lat = {me: [], them: []}
        for a, b in zip(timed, timed[1:]):
            if a["sender"] == b["sender"]:
                continue
            gap = (b["dt"] - a["dt"]).total_seconds()
            if 0 < gap <= 6 * 3600 and b["sender"] in lat:
                lat[b["sender"]].append(gap)
        res["reply_median"] = {
            k: (round(statistics.median(v)) if v else None) for k, v in lat.items()
        }
        res["reply_count"] = {k: len(v) for k, v in lat.items()}

        # 谁先开启对话：>6h 沉默后的第一条
        init = {me: 0, them: 0}
        last = None
        for m in timed:
            if last is None or (m["dt"] - last).total_seconds() > 6 * 3600:
                if m["sender"] in init:
                    init[m["sender"]] += 1
            last = m["dt"]
        res["initiations"] = init

        # 最长沉默
        gaps = [(b["dt"] - a["dt"]).total_seconds() for a, b in zip(timed, timed[1:])]
        res["longest_silence"] = fmt_dur(int(max(gaps))) if gaps else None

        # 单方面连发
        run = best = 0
        prev = None
        for m in timed:
            if m["sender"] == prev:
                run += 1
            else:
                run = 1
                prev = m["sender"]
            best = max(best, run)
        res["max_streak"] = best

        # 时段分布（早/午/晚/深夜）
        buckets = {"清晨(5-9)": 0, "白天(9-18)": 0, "晚上(18-23)": 0, "深夜(23-5)": 0}
        for t in times:
            h = t.hour
            if 5 <= h < 9:
                buckets["清晨(5-9)"] += 1
            elif 9 <= h < 18:
                buckets["白天(9-18)"] += 1
            elif 18 <= h < 23:
                buckets["晚上(18-23)"] += 1
            else:
                buckets["深夜(23-5)"] += 1
        res["buckets"] = buckets

    lens = [len(m["text"]) for m in msgs]
    res["avg_len"] = round(sum(lens) / n, 1)
    res["max_len"] = max(lens)
    res["avg_len_me"] = round(sum(len(m["text"]) for m in msgs if m["sender"] == me) / max(n_me, 1), 1)
    res["avg_len_them"] = round(sum(len(m["text"]) for m in msgs if m["sender"] == them) / max(n_them, 1), 1)

    # 高频短语：只在连续的中文片段里统计，避免把标点算进去
    cnt = {}
    for m in msgs:
        for run in re.findall(r"[\u4e00-\u9fa5]+", m["text"]):
            for L in (2, 3, 4):
                for k in range(len(run) - L + 1):
                    s = run[k:k + L]
                    cnt[s] = cnt.get(s, 0) + 1
    top = [w for w, c in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:12] if c >= 5]
    res["frequent_phrases"] = top

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    p = print
    p("消息总数: %d  (me=%d, them=%d, 其他=%d)" % (n, n_me, n_them, res["other"]))
    if timed:
        p("时间范围: %s → %s  (跨度 %s 天, 活跃 %d 天, 日均 %.1f 条)"
          % (res["start"], res["end"], res["span_days"], res["active_days"], res["per_active_day"]))
        med = res["reply_median"]
        p("回复中位延迟: me 回 %s ｜ them 回 %s"
          % (fmt_dur(med["me"]) if med["me"] else "无", fmt_dur(med["them"]) if med["them"] else "无"))
        p("谁先开口(>6h 沉默后): me=%d, them=%d" % (res["initiations"][me], res["initiations"][them]))
        p("最长沉默: %s ｜ 单方最多连发: %d 条" % (res["longest_silence"], res["max_streak"]))
        p("时段分布: " + " / ".join("%s %d" % (k, v) for k, v in res["buckets"].items()))
        p("深夜占比: %.0f%%" % (res["night_ratio"] * 100))
    p("平均长度: 总体 %.1f 字 ｜ me %.1f ｜ them %.1f ｜ 最长 %d"
      % (res["avg_len"], res["avg_len_me"], res["avg_len_them"], res["max_len"]))
    if top:
        p("高频片段: " + "、".join(top[:8]))


if __name__ == "__main__":
    main()

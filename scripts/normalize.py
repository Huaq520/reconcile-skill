#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 QQ / 微信 / 通用聊天记录导出统一成 JSONL。

用法:
    python3 normalize.py 记录.txt -o chat.jsonl --me 我的昵称
    python3 normalize.py wechat.csv --format wechat-csv -o chat.jsonl
    python3 normalize.py chat.jsonl --format jsonl -o out.jsonl
    cat 粘贴.txt | python3 normalize.py - --format paste -o chat.jsonl

输出每行:
    {"time": "2024-06-01 12:00:01", "sender": "me|them|昵称", "text": "...", "kind": "text"}

只依赖标准库。
"""
import argparse
import csv
import io
import json
import os
import re
import sys

TS_RE = re.compile(
    r"^\[?(\d{4}[-/]\d{1,2}[-/]\d{1,2})[ T](\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.*)$"
)
PEER_RE = re.compile(r"^=+\s*消息对象[:：]\s*(.+?)\s*=+$")
NICK_ID_RE = re.compile(r"\s*[\(（<][^()（）<>]*[\)）>]\s*$")
PASTE_RE = re.compile(
    r"^\s*(?:\[?(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?"
    r"([^\s:：]{1,12})\s*[:：]\s*(.*)$"
)
ME_ALIASES = {"我", "me", "本人", "自己"}

TIME_KEYS = ("time", "strtime", "createtime", "date", "ts", "timestamp", "msgtime")
SENDER_KEYS = ("sender", "from", "name", "nickname", "nick", "role", "talker", "username")
TEXT_KEYS = ("text", "content", "msg", "message", "strcontent", "displaycontent", "body")
KIND_KEYS = ("kind", "type", "msgtype")

WECHAT_TYPE = {
    "3": "image",
    "34": "voice",
    "43": "video",
    "47": "emoji",
    "49": "file",
    "10000": "system",
}


# ---------------------------------------------------------------- io helpers
def read_text(path):
    if path == "-":
        raw = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            raw = f.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def clean_nick(s):
    s = (s or "").strip()
    s = NICK_ID_RE.sub("", s)
    return s.strip()


def norm_ts(m):
    date, clock = m.group(1).replace("/", "-"), m.group(2)
    if len(clock.split(":")) == 2:
        clock += ":00"
    parts = [int(x) for x in date.split("-")]
    h, mi, se = (int(x) for x in clock.split(":"))
    return "%04d-%02d-%02d %02d:%02d:%02d" % (parts[0], parts[1], parts[2], h, mi, se)


def make(time_s, sender, text, kind="text"):
    return {"time": time_s, "sender": sender, "text": text, "kind": kind}


# ------------------------------------------------------------------ qq text
def parse_qq_txt(text, me):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    msgs = []
    peer = None
    sender = None
    buf = []
    cur_time = None

    def flush():
        nonlocal buf, sender, cur_time
        body = "\n".join(buf).strip()
        if body:
            msgs.append(make(cur_time, sender, body))
        buf = []

    for i, line in enumerate(lines):
        m = PEER_RE.match(line.strip())
        if m:
            flush()
            peer = clean_nick(m.group(1))
            sender = peer
            continue
        m = TS_RE.match(line)
        if m:
            flush()
            cur_time = norm_ts(m)
            rest = m.group(3).strip()
            if rest:
                sender = clean_nick(rest)
            else:
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if nxt and not TS_RE.match(nxt) and len(nxt) <= 40:
                    sender = clean_nick(nxt)
                    lines[i + 1] = ""
            continue
        if not line.strip():
            continue
        if line.strip().startswith("====="):
            # 新的消息分组/对象分隔：结束上一条
            flush()
            cur_time = None
            continue
        if cur_time is None:
            # 首个时间戳之前的说明文字，跳过
            continue
        buf.append(line)

    flush()

    # 映射自己/对方：只在"恰好两个人"时才敢自动判定谁是 me
    names = {clean_nick(m["sender"]) for m in msgs if m["sender"]}
    others = names - {peer} if peer else names
    auto_me = (not me) and bool(peer) and len(others) == 1
    out = []
    for m in msgs:
        name = clean_nick(m["sender"])
        if name in ("我", "me", "本人", "自己") or (me and name == me):
            m["sender"] = "me"
        elif peer and name == peer:
            m["sender"] = "them"
        elif auto_me and name in others:
            m["sender"] = "me"
        elif not name:
            m["sender"] = "them" if peer else "unknown"
        else:
            m["sender"] = name
        out.append(m)
    return out


# --------------------------------------------------------------- wechat csv
def pick(row, keys):
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for k in keys:
        if k in lower and str(lower[k]).strip() != "":
            return lower[k]
    return None


def to_time(v):
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d{10}", s):
        import datetime

        return datetime.datetime.fromtimestamp(int(s)).strftime("%Y-%m-%d %H:%M:%S")
    if re.fullmatch(r"\d{13}", s):
        import datetime

        return datetime.datetime.fromtimestamp(int(s) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    m = TS_RE.match(s)
    return norm_ts(m) if m else s


def parse_wechat_csv(text, me):
    reader = csv.DictReader(io.StringIO(text))
    msgs = []
    for row in reader:
        raw_text = pick(row, TEXT_KEYS)
        raw_text = "" if raw_text is None else str(raw_text).strip()
        sender_raw = pick(row, SENDER_KEYS)
        is_sender = str(pick(row, ("issender", "is_sender", "issend")) or "").lower()
        kind_raw = str(pick(row, KIND_KEYS) or "").strip()

        if is_sender in ("1", "true", "yes", "是"):
            sender = "me"
        else:
            s = clean_nick(str(sender_raw or ""))
            sender = "me" if (me and s == me) else "them"
        kind = WECHAT_TYPE.get(kind_raw, "text")
        if not raw_text:
            if kind == "text":
                continue
            raw_text = "[%s]" % {"image": "图片", "voice": "语音", "video": "视频",
                                 "emoji": "表情", "file": "文件", "system": "系统消息"}[kind]
        if kind == "system":
            continue
        msgs.append(make(to_time(pick(row, TIME_KEYS)), sender, raw_text, kind))
    return msgs


# --------------------------------------------------------------- json / jsonl
def parse_json_like(text, me, fmt="json"):
    text = text.strip()
    items = []
    if fmt == "jsonl":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    elif text.startswith("["):
        items = json.loads(text)
    else:
        obj = json.loads(text)
        items = obj.get("messages", obj.get("data", [obj])) if isinstance(obj, dict) else obj

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = pick(it, TIME_KEYS) or ""
        s = clean_nick(str(pick(it, SENDER_KEYS) or ""))
        body = pick(it, TEXT_KEYS)
        if body is None:
            continue
        if me and s == me:
            s = "me"
        elif s in ("我", "me", "本人", "自己"):
            s = "me"
        elif s in ("对方", "他", "她", "ta", "TA"):
            s = "them"
        kind = str(pick(it, KIND_KEYS) or "text")
        out.append(make(to_time(t), s or "unknown", str(body), kind))
    return out


# -------------------------------------------------------------------- paste
def parse_paste(text, me):
    msgs = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        m = PASTE_RE.match(line)
        if m:
            ts = ""
            if m.group(1):
                tm = TS_RE.match(m.group(1) + " ")
                ts = norm_ts(tm) if tm else m.group(1)
            who = m.group(2)
            if who in ME_ALIASES or (me and who == me):
                sender = "me"
            elif who in ("对方", "他", "她", "ta", "TA", "T", "you", "u"):
                sender = "them"
            else:
                sender = clean_nick(who)
            msgs.append(make(ts, sender, m.group(3).strip()))
        else:
            msgs.append(make("", "them", line.strip()))
    return msgs


# --------------------------------------------------------------------- main
def detect(path, text):
    ext = os.path.splitext(path)[1].lower() if path != "-" else ""
    if ext == ".jsonl":
        return "jsonl"
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "wechat-csv"
    head = text[:2000]
    if re.search(r"StrContent|StrTime|IsSender", head, re.I):
        return "wechat-csv"
    if re.search(r"消息对象[:：]", head) or re.search(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2} ", head, re.M):
        return "qq-txt"
    if re.search(r"^\s*(我|对方|他|她|ta|TA)\s*[:：]", head, re.M):
        return "paste"
    return "paste"


def main():
    ap = argparse.ArgumentParser(description="聊天记录 → 统一 JSONL")
    ap.add_argument("input", help="输入文件；- 表示标准输入")
    ap.add_argument("-o", "--output", default="chat.jsonl")
    ap.add_argument("--me", default="", help="你自己在记录里的昵称（用于区分 me/them）")
    ap.add_argument("--format", default="auto",
                    choices=["auto", "qq-txt", "wechat-csv", "jsonl", "json", "paste"])
    args = ap.parse_args()

    text = read_text(args.input)
    fmt = detect(args.input, text) if args.format == "auto" else args.format

    if fmt == "qq-txt":
        msgs = parse_qq_txt(text, args.me)
    elif fmt == "wechat-csv":
        msgs = parse_wechat_csv(text, args.me)
    elif fmt in ("jsonl", "json"):
        msgs = parse_json_like(text, args.me, fmt)
    else:
        msgs = parse_paste(text, args.me)

    msgs = [m for m in msgs if m["text"]]
    with open(args.output, "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    me = sum(1 for m in msgs if m["sender"] == "me")
    them = sum(1 for m in msgs if m["sender"] == "them")
    print("格式: %s | 消息: %d 条 (me=%d, them=%d, 其他=%d)"
          % (fmt, len(msgs), me, them, len(msgs) - me - them), file=sys.stderr)
    if msgs:
        print("时间范围: %s → %s" % (msgs[0]["time"] or "?", msgs[-1]["time"] or "?"), file=sys.stderr)
    if me == 0 and them == 0:
        print("提示: 未能识别出 me/them，建议加 --me <你的昵称>", file=sys.stderr)
    print("已写入 %s" % args.output, file=sys.stderr)


if __name__ == "__main__":
    main()

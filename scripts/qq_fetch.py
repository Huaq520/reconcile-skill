#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经用户授权，从本机 NapCat (OneBot v11 HTTP) 拉取 QQ 聊天记录 → JSONL。

用法:
    export NAPCAT_TOKEN=你的token
    python3 qq_fetch.py --user 123456789 --count 100 --consent -o chat.jsonl
    python3 qq_fetch.py --group 987654321 --count 200 --consent -o chat.jsonl

要求:
    - 本机已运行 NapCat，HTTP 服务可访问（默认 127.0.0.1:3000）
    - --consent 是必须的：确认你已获得查看/分析这些记录的授权

只输出条数和时间范围，不打印消息内容。只依赖标准库。
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_API = "http://127.0.0.1:3000"


def call(api, token, action, payload=None, timeout=20):
    url = "%s/%s" % (api.rstrip("/"), action)
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:200]))
    except urllib.error.URLError as e:
        raise SystemExit("连不上 NapCat (%s)：%s\n请确认服务在跑，或用 --api 指定地址。" % (url, e.reason))
    if body.get("status") != "ok" or body.get("retcode") not in (0, None):
        raise SystemExit("NapCat 返回失败: %s" % (body.get("message") or body.get("wording") or body))
    return body.get("data")


def seg_text(segs):
    out = []
    for s in segs or []:
        t = s.get("type")
        d = s.get("data") or {}
        if t == "text":
            out.append(str(d.get("text", "")))
        elif t == "image":
            out.append("[图片]")
        elif t == "record":
            out.append("[语音]")
        elif t == "video":
            out.append("[视频]")
        elif t in ("face", "mface"):
            out.append("[表情]")
        elif t == "at":
            out.append("@" + str(d.get("qq", "")))
        elif t == "file":
            out.append("[文件]")
        elif t == "forward":
            out.append("[聊天记录]")
        elif t == "reply":
            continue
        elif t == "json":
            out.append("[卡片]")
        elif t == "poke":
            out.append("[拍一拍]")
        else:
            out.append("[%s]" % t)
    return " ".join(x for x in out if x).strip()


def main():
    ap = argparse.ArgumentParser(description="从 NapCat 拉取 QQ 聊天记录")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--user", help="好友 QQ 号")
    g.add_argument("--group", help="群号")
    ap.add_argument("--count", type=int, default=100, help="每页条数，默认 100")
    ap.add_argument("--pages", type=int, default=1, help="翻页次数，默认 1")
    ap.add_argument("--api", default=os.environ.get("NAPCAT_API", DEFAULT_API))
    ap.add_argument("--token", default=os.environ.get("NAPCAT_TOKEN", ""))
    ap.add_argument("-o", "--output", default="chat.jsonl")
    ap.add_argument("--consent", action="store_true", help="确认已获得授权（必须）")
    ap.add_argument("--tz", default=os.environ.get("RECONCILE_TZ", "Asia/Shanghai"),
                    help="消息时间按哪个时区显示，默认 Asia/Shanghai")
    args = ap.parse_args()

    if not args.consent:
        raise SystemExit("需要 --consent：确认你有权查看并分析这些聊天记录，且对方知情或你已获得授权。"
                         "\n（这是隐私底线，不是形式。）")
    if not args.token:
        raise SystemExit("缺少 token：export NAPCAT_TOKEN=... 或用 --token 指定。"
                         "\n可在 NapCat 的 onebot11_<QQ>.json 里找到 network.httpServers[].token。")

    login = call(args.api, args.token, "get_login_info")
    self_id = str(login.get("user_id"))
    print("当前账号: %s (%s)" % (self_id, login.get("nickname")), file=sys.stderr)

    action = "get_friend_msg_history" if args.user else "get_group_msg_history"
    key = "user_id" if args.user else "group_id"
    target = args.user or args.group
    seq = None
    seen = {}
    for page in range(max(args.pages, 1)):
        payload = {key: int(target), "count": args.count}
        if seq:
            payload["message_seq"] = seq
        data = call(args.api, args.token, action, payload, timeout=30)
        msgs = (data or {}).get("messages") or []
        if not msgs:
            break
        for m in msgs:
            seen[str(m.get("message_id"))] = m
        seq = min(int(m.get("message_seq") or 0) for m in msgs)
        if seq <= 1:
            break

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(args.tz)
    except Exception:
        tz = None
        print("提示: 时区 %s 不可用，按本机时区输出。" % args.tz, file=sys.stderr)

    rows = []
    for m in seen.values():
        sender = str((m.get("sender") or {}).get("user_id"))
        who = "me" if sender == self_id else "them"
        t = m.get("time")
        ts = (datetime.datetime.fromtimestamp(int(t), tz) if tz else datetime.datetime.fromtimestamp(int(t))
              ).strftime("%Y-%m-%d %H:%M:%S") if t else ""
        body = m.get("raw_message") if isinstance(m.get("message"), str) else seg_text(m.get("message"))
        rows.append({"time": ts, "sender": who, "text": body or "", "kind": "text",
                     "nick": (m.get("sender") or {}).get("nickname", "")})

    rows.sort(key=lambda r: r["time"])
    with open(args.output, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if rows:
        print("已拉取 %d 条，时间范围 %s → %s" % (len(rows), rows[0]["time"], rows[-1]["time"]),
              file=sys.stderr)
    else:
        print("没有拉到消息（可能超出服务端历史范围，或会话不可见）。", file=sys.stderr)
    print("已写入 %s" % args.output, file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""排练存档：记录尝试次数、每次的状态与一句话备注，支持读档回看。

用法:
    python3 state.py init --persona persona.md --chat chat.jsonl
    python3 state.py save "第1版 道歉" --temp 35 --note "她说再想想"
    python3 state.py list
    python3 state.py show 1
    python3 state.py reset            # 清空尝试记录，保留人设
    python3 state.py --dir .reconcile ...

存档只存"摘要"，不存完整对话；完整对话在当前会话里，读档靠摘要回忆。
"""
import argparse
import datetime
import json
import os
import sys

DEFAULT_DIR = ".reconcile"

STAGE_TEMP = {"A": 30, "B": 20, "C": 15, "D": 5, "E": 60}


def now_str():
    try:
        from zoneinfo import ZoneInfo

        return datetime.datetime.now(ZoneInfo(os.environ.get("RECONCILE_TZ", "Asia/Shanghai"))).strftime(
            "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def path_of(d):
    return os.path.join(d, "state.json")


def load(d):
    p = path_of(d)
    if not os.path.exists(p):
        return {"persona": "", "chat": "", "attempts": [], "current": 0}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_file(d, st):
    os.makedirs(d, exist_ok=True)
    with open(path_of(d), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--persona", default="")
    p_init.add_argument("--chat", default="")
    p_init.add_argument("--stage", default="", choices=["", "A", "B", "C", "D", "E"],
                        help="处境：A 刚吵完 / B 冷战 / C 分手想复合 / D 断联 / E 修复")
    p_init.add_argument("--goal", default="", help="这一次想做到什么，一句话")

    p_save = sub.add_parser("save")
    p_save.add_argument("label")
    p_save.add_argument("--temp", type=int, default=None, help="温度 0-100")
    p_save.add_argument("--note", default="")

    p_show = sub.add_parser("show")
    p_show.add_argument("id", type=int)

    sub.add_parser("list")
    sub.add_parser("reset")

    args = ap.parse_args()
    st = load(args.dir)

    if args.cmd == "init":
        st["persona"] = args.persona or st.get("persona", "")
        st["chat"] = args.chat or st.get("chat", "")
        st["stage"] = args.stage or st.get("stage", "")
        st["goal"] = args.goal or st.get("goal", "")
        st["baseline_temp"] = STAGE_TEMP.get(st["stage"], 30)
        save_file(args.dir, st)
        print("已初始化 %s" % path_of(args.dir))
        print("  人设：%s" % (st["persona"] or "未设置"))
        print("  处境：%s（初始温度 %d）" % (st["stage"] or "未设置", st["baseline_temp"]))
        if st["goal"]:
            print("  目标：%s" % st["goal"])

    elif args.cmd == "save":
        nid = (max([a["id"] for a in st["attempts"]], default=0)) + 1
        st["attempts"].append({
            "id": nid,
            "label": args.label,
            "temp": args.temp,
            "note": args.note,
            "at": now_str(),
        })
        st["current"] = nid
        save_file(args.dir, st)
        print("存档 #%d：%s%s" % (nid, args.label, "（温度 %d）" % args.temp if args.temp is not None else ""))

    elif args.cmd == "list":
        if not st["attempts"]:
            print("还没有存档。")
            return
        for a in st["attempts"]:
            temp = "?" if a.get("temp") is None else str(a["temp"])
            print("#%-3d %-28s 温度 %-4s %s" % (a["id"], a["label"][:28], temp, a.get("note", "")))

    elif args.cmd == "show":
        hit = [a for a in st["attempts"] if a["id"] == args.id]
        if not hit:
            sys.exit("没有 #%d 这个存档" % args.id)
        print(json.dumps(hit[0], ensure_ascii=False, indent=2))
        print("\n人设文件：%s" % (st.get("persona") or "未设置"))
        if st.get("stage"):
            print("处境：%s（初始温度 %d）%s" % (
                st["stage"], st.get("baseline_temp", 30),
                "｜目标：" + st["goal"] if st.get("goal") else ""))

    elif args.cmd == "reset":
        st["attempts"] = []
        st["current"] = 0
        save_file(args.dir, st)
        print("已清空尝试记录（人设保留）")


if __name__ == "__main__":
    main()

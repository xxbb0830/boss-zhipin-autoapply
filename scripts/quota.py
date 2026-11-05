# -*- coding: utf-8 -*-
"""Count how many jobs were contacted TODAY, so the daily cap can be respected."""
import os, sys, time, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from lxml import etree

DAILY_LIMIT = 150


def parse_buckets(xml):
    root = etree.fromstring(xml.encode("utf-8"))
    items = []
    for n in root.iter("node"):
        b = C._b(n)
        t = (n.get("text") or "").strip()
        if b and t:
            items.append((b[1], C.rid(n), t))
    items.sort()
    cur, order, counts = None, [], {}
    for y, r, t in items:
        if r == "tv_time_line" and re.match(r"^(\d+月\d+日|昨天|今天)$", t):
            cur = t
            if t not in order:
                order.append(t)
            counts.setdefault(t, 0)
        elif r == "tv_position_name":
            counts[cur] = counts.get(cur, 0) + 1
    return counts, order


def today_key():
    lt = time.localtime()
    return f"{lt.tm_mon}月{lt.tm_mday}日"


def count(verbose=True):
    """Open 求职记录 → 沟通过, count today's entries. Returns dict."""
    from history import open_record_list
    if not open_record_list():
        return {"error": "cannot_open_record_list", "used": None}
    for _ in range(16):                      # to the very top, gently
        C.swipe(720, 1150, 720, 2900, 0.45, 0.5)

    best, order = {}, []
    for s in range(7):
        counts, o = parse_buckets(C.dump_xml())
        for k, v in counts.items():
            if k:
                best[k] = max(best.get(k, 0), v)
        for d in o:
            if d not in order:
                order.append(d)
        if verbose:
            print(f"  screen {s}: {counts}", flush=True)
        if len(order) >= 2:
            break
        C.swipe(720, 2900, 720, 1200, 0.4, 1.0)

    tk = today_key()
    used = best.get(tk, best.get(order[0], 0) if order else 0)
    out = {"today": tk, "used": used, "limit": DAILY_LIMIT,
           "remaining": max(0, DAILY_LIMIT - used), "buckets": best,
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(C.DATA, "quota.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def main():
    q = count()
    if q.get("error"):
        print("[fatal]", q["error"], flush=True)
        return
    print("\n=== 日期分桶 ===")
    for k, v in q["buckets"].items():
        print(f"  {k}: {v}")
    print(f"\nTODAY={q['today']} 已沟通={q['used']}  剩余={q['remaining']}/{q['limit']}")


if __name__ == "__main__":
    main()

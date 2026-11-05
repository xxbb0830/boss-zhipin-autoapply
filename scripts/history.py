# -*- coding: utf-8 -*-
"""Scrape 求职记录 → 沟通过 and summarise the user's application habits."""
import os, sys, time, json, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from lxml import etree

OUT = os.path.join(C.DATA, "history.jsonl")


def _tap_node(rid, timeout=8):
    """Tap a node by resource-id, using its bounds center (works for ViewGroups)."""
    d = C.dev()
    end = time.time() + timeout
    while time.time() < end:
        try:
            for n in etree.fromstring(C.dump_xml().encode("utf-8")).iter("node"):
                if C.rid(n) == rid:
                    b = C._b(n)
                    if b:
                        C.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, 2.5)
                        return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def open_record_list():
    """我的 → 沟通过 记录列表."""
    C.ensure_boss()
    if not C.tap_id("cl_tab_4", 6):
        return False
    time.sleep(1.5)
    return _tap_node("cl_geek_contacts_number")


def parse_page(xml):
    root = etree.fromstring(xml.encode("utf-8"))
    ns = []
    for n in root.iter("node"):
        b = C._b(n)
        t = (n.get("text") or "").strip()
        if b and t:
            ns.append((b, C.rid(n), t))
    anchors = sorted([(b, t) for b, r, t in ns if r == "tv_position_name"], key=lambda a: a[0][1])
    cards = []
    for i, (ab, at) in enumerate(anchors):
        lo = ab[1] - 40
        hi = anchors[i + 1][0][1] - 40 if i + 1 < len(anchors) else 10 ** 9
        rec = {"position": at, "salary": "", "company": "", "loc": "",
               "exp": "", "degree": "", "hr": "", "time": "", "date": ""}
        for b, r, t in ns:
            if not (lo <= b[1] < hi):
                continue
            if r == "tv_salary_statue":
                rec["salary"] = t
            elif r == "tv_company_name":
                rec["company"] = t
            elif r == "tv_employer":
                rec["hr"] = t
            elif r == "tv_active_time":
                rec["time"] = t
            elif r == "" and b[0] < 900:
                if re.search(r"(区|县|市)$|^北京$|^上海$|^深圳$|^杭州$|^广州$", t) and not rec["loc"]:
                    rec["loc"] = t
                elif re.search(r"(应届|在校|\d-\d年)$", t) and not rec["exp"]:
                    rec["exp"] = t
                elif re.fullmatch(r"(本科|大专|硕士|博士|中专|学历不限)", t) and not rec["degree"]:
                    rec["degree"] = t
        cards.append(rec)
    # attach the most recent date header above each card
    headers = sorted([(b[1], t) for b, r, t in ns
                      if r == "tv_time_line" and re.match(r"^(\d+月\d+日|昨天|今天)$", t)])
    for c in cards:
        pass
    return cards, headers


def scrape(scrolls=25, verbose=True):
    if not open_record_list():
        print("[fatal] cannot open 求职记录", flush=True)
        return {}
    seen = {}
    for s in range(scrolls):
        cards, headers = parse_page(C.dump_xml())
        new = 0
        for c in cards:
            k = (c["company"], c["position"])
            if c["position"] and k not in seen:
                seen[k] = c
                new += 1
        if verbose:
            print(f"scroll {s}: page={len(cards)} total={len(seen)} new={new}", flush=True)
        C.swipe(720, 2900, 720, 1100, 0.4, 1.2)
        if new == 0 and s > 3:
            break
    with open(OUT, "w", encoding="utf-8") as f:
        for c in seen.values():
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[saved] {len(seen)} records -> {OUT}", flush=True)
    return seen


def summarise(records=None):
    if records is None:
        if not os.path.exists(OUT):
            print("no history.jsonl — run scrape first")
            return
        records = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    rs = list(records.values()) if isinstance(records, dict) else records
    print(f"\n=== {len(rs)} 条沟通记录 ===")
    for field in ("salary", "exp", "degree"):
        c = collections.Counter(r[field] for r in rs if r.get(field))
        print(f"\n-- {field} --")
        for k, v in c.most_common(10):
            print(f"  {v:3d}  {k}")
    kw = collections.Counter()
    keys = ["AI", "大模型", "LLM", "Agent", "算法", "Python", "全栈", "后端",
            "数据", "开发工程师", "研发", "RAG", "NLP", "应届"]
    for r in rs:
        p = r.get("position", "")
        for k in keys:
            if k.lower() in p.lower():
                kw[k] += 1
    print("\n-- 岗位关键词 --")
    for k, v in kw.most_common():
        print(f"  {v:3d}  {k}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rec = scrape(scrolls=n)
    summarise(rec)

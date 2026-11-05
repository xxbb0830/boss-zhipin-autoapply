# -*- coding: utf-8 -*-
"""BOSS直聘 bulk auto-apply core.

Exposes run() so it can be driven by auto.py unattended.
Per job: open card -> read JD -> classify -> 立即沟通 -> send ONE fixed
category message -> back.  Resumable ledger, app guards, human pacing.
"""
import os, sys, time, json, random, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import messages as M
import targeting as T
import fit as F
from lxml import etree

DATA = C.DATA
LEDGER = os.path.join(DATA, "applied.jsonl")
EDIT_ID = C.EDIT_ID


def now():
    return time.strftime("%H:%M:%S")


def p(msg):
    print(f"[{now()}] {msg}", flush=True)


def key_of(title, company):
    return f"{(company or '').strip()}|{(title or '').strip()}"


def is_detail(act):
    """Job detail exists in several flavours (校招 uses BossJobActivity)."""
    act = act or ""
    return ("BossJobPager" in act or "BossJobActivity" in act
            or "geekjd" in act.lower() or "jobdetail" in act.lower())


def is_list(act):
    return "MainActivity" in (act or "")


def load_done():
    done = set()
    if os.path.exists(LEDGER):
        for line in open(LEDGER, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("status") == "ok":
                    done.add(r["key"])
            except Exception:
                pass
    return done


def log(rec):
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def chat_msgs(xml):
    root = etree.fromstring(xml.encode("utf-8"))
    return [(n.get("text") or "").strip() for n in root.iter("node")
            if C.rid(n) == "tv_content_text"]


PANEL_MARKERS = ('"图片"', '"语音"', '"语音通话"')


def _panel_open(xml):
    return any(k in xml for k in PANEL_MARKERS)


def _clear_input(et):
    try:
        et.set_text("")
        time.sleep(0.35)
    except Exception:
        pass


def send_message(text, tries=3):
    """Type and send exactly one message. Returns (ok, how).

    Row layout is [voice][EditText][emoji][send]; the send control has no id
    and the emoji button is closer, so we take the RIGHTMOST control.
    Verified by looking for the bubble in tv_content_text; a draft is always
    cleared so nothing half-typed is left behind.
    """
    d = C.dev()
    last = "unknown"
    for attempt in range(1, tries + 1):
        et = d(resourceId=EDIT_ID)
        if not et.exists(timeout=6):
            return False, "no_edittext"
        et.click()
        time.sleep(0.8)
        _clear_input(et)

        try:
            et.set_text(text)
        except Exception as e:
            last = f"set_text:{str(e)[:40]}"
            continue
        time.sleep(1.3)

        cur = ""
        try:
            cur = et.get_text() or ""
        except Exception:
            pass
        if text[:8] not in cur:
            try:
                et.set_text(text)
                time.sleep(1.0)
                cur = et.get_text() or ""
            except Exception:
                cur = ""
            if text[:8] not in cur:
                last = "text_not_typed"
                continue

        cands = []
        try:
            _, cands = C.chat_input_row(C.dump_xml())
        except Exception:
            pass
        positions = []
        if cands:
            positions.append((cands[-1][0], cands[-1][1]))
        try:
            b = et.info.get("bounds") or {}
            cy = (b.get("top", 3060) + b.get("bottom", 3144)) // 2
            positions.append((1335, cy))
        except Exception:
            pass
        if not positions:
            positions = [(1335, 3070)]

        for (px, py) in positions:
            C.tap(px, py, 1.6)
            if C.cur_pkg() != C.PKG:
                return False, "trap_app_switch"
            for _ in range(3):
                try:
                    msgs = chat_msgs(C.dump_xml())
                except Exception:
                    msgs = []
                if any(text[:10] in m for m in msgs):
                    return True, f"sent(try{attempt})@{px},{py}"
                time.sleep(0.9)
            try:
                if _panel_open(C.dump_xml()):
                    last = "panel_opened"
                    C.back(1.0)
                    break
            except Exception:
                pass
            last = "send_unverified"

        _clear_input(et)
    return False, last


def return_to_list(max_steps=8):
    """Get back to the scrollable job list, whatever screen we ended on."""
    for _ in range(max_steps):
        act = C.cur_act()
        if is_list(act):
            try:
                if 'tv_position_name' in C.dump_xml():
                    return True
            except Exception:
                pass
        if C.cur_pkg() != C.PKG:
            C.ensure_boss()
            continue
        C.back(1.2)
    return C.ensure_job_list()


def open_card(card):
    """Tap a list card and land on its detail page. Tries a few tap points."""
    pts = [(720, card["y_mid"]), (400, card["y_mid"]),
           (720, card["y_mid"] + 120), (720, card["y_mid"] - 80)]
    for (x, y) in pts:
        C.tap(x, y, 2.6)
        if is_detail(C.cur_act()):
            return True
        time.sleep(0.8)
    return False


def apply_one(card, dry=False):
    title, company = card["title"], card["company"]

    if not is_list(C.cur_act()):
        return_to_list()

    if not open_card(card):
        return {"status": "open_fail", "activity": C.cur_act(),
                "job": title, "company": company}

    det = C.parse_detail(C.dump_xml())
    job = det["job"] or title
    comp = det["company"] or company
    btn = det["btn"]

    if not det["job"]:
        return_to_list()
        return {"status": "detail_parse_fail", "job": job, "company": comp}

    if btn and "立即沟通" not in btn:
        return_to_list()
        return {"status": "already", "btn": btn, "job": job, "company": comp}

    cat = M.classify(job, det["jd"])
    ok_fit, why, hits, score = F.judge(job, det["jd"])

    if dry:
        return_to_list()
        return {"status": "dry", "job": job, "company": comp, "cat": cat,
                "fit": ok_fit, "why": why, "score": score,
                "jd_len": len(det["jd"]), "jd": (det["jd"] or "")[:160],
                "btn": btn}

    # 读完 JD 再判断能不能胜任：没有我懂的技术就不打扰对方
    if not ok_fit:
        return_to_list()
        return {"status": "no_fit", "why": why, "score": score,
                "jd": (det["jd"] or "")[:160],
                "job": job, "company": comp, "cat": cat}

    # 校招/实习岗不一定是 btn_chat，可能叫「投递简历」等
    tapped = C.tap_id("btn_chat", 6)
    if not tapped:
        for label in ("立即沟通", "投递简历", "申请职位", "我要投递", "沟通"):
            if C.tap_text(label, 3):
                tapped = True
                p(f"      used fallback button 「{label}」")
                break
    if not tapped:
        return_to_list()
        return {"status": "btn_fail", "job": job, "company": comp}
    time.sleep(3.0)

    if "ChatRoom" not in C.cur_act():
        txts = C.screen_texts(C.dump_xml())
        limit = any(k in t for t in txts for k in ("上限", "频繁", "明天再", "已达"))
        return_to_list()
        return {"status": "no_chat", "limit": limit, "job": job, "company": comp}

    _, msg = M.build(job, det["jd"], comp)
    ok, how = send_message(msg)
    time.sleep(0.5)
    return_to_list()
    return {"status": "ok" if ok else "msg_fail", "how": how, "cat": cat,
            "job": job, "company": comp, "msg_len": len(msg)}


def run(limit=150, dry=False, min_gap=7.0, max_gap=15.0, max_scrolls=600):
    """Run the apply loop. Returns a stats dict."""
    done = load_done()
    skipped = set()          # tried-and-failed / already handled this run
    p(f"ledger ok={len(done)}  limit={limit}  dry={dry}")
    if not C.ensure_job_list():
        p("FATAL: cannot reach job list")
        return {"ok": 0, "skip": 0, "fail": 0, "aborted": "no_job_list"}

    n_ok = n_skip = n_fail = n_dry = 0
    consec = scrolls = 0
    no_progress = 0
    cats = {}
    t0 = time.time()
    abort = None

    # dry 模式不会产生 ok，所以用它自己的计数来尊重 --limit
    while (n_dry if dry else n_ok) < limit and scrolls < max_scrolls:
        # never parse a chat/detail page: they contain tv_position_name too
        if not is_list(C.cur_act()):
            return_to_list()

        try:
            cards = C.parse_cards(C.dump_xml())
        except Exception as e:
            p(f"parse warn: {e}")
            C.ensure_job_list()
            continue

        target, n_filtered = None, 0
        for c in cards:
            k = key_of(c["title"], c["company"])
            if k in done or k in skipped:
                continue
            if not T.card_ok(c):
                skipped.add(k)
                n_filtered += 1
                continue
            target = c
            break
        if n_filtered:
            p(f"filtered {n_filtered} card(s) by salary band")

        if target is None:
            C.swipe(720, 2750, 720, 1150, 0.35, 1.2)
            scrolls += 1
            no_progress += 1
            if no_progress >= 25:
                abort = "end_of_list"
                break
            if scrolls % 10 == 0:
                p(f"scroll {scrolls} ok={n_ok} skip={n_skip} fail={n_fail}")
            continue

        no_progress = 0
        k = key_of(target["title"], target["company"])
        skipped.add(k)
        try:
            r = apply_one(target, dry=dry)
        except Exception as e:
            p(f"ERR {k}: {type(e).__name__} {str(e)[:90]}")
            try:
                return_to_list()
            except Exception:
                pass
            n_fail += 1
            consec += 1
            if consec >= 4:
                abort = "consecutive_failures"
                break
            continue

        st = r.get("status")
        k2 = key_of(r.get("job") or target["title"], r.get("company") or target["company"])
        r.update({"key": k2, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "title": r.get("job") or target["title"],
                  "company": r.get("company") or target["company"],
                  "salary": target.get("salary", "")})
        skipped.add(k2)
        if r.get("cat"):
            cats[r["cat"]] = cats.get(r["cat"], 0) + 1

        if st == "ok":
            n_ok += 1
            consec = 0
            done.add(k2)                      # in-memory dedup — critical
            log(r)
            p(f"[{n_ok:3d}] OK [{r.get('cat')}] {r['company']} | {r['job']}")
            time.sleep(random.uniform(min_gap, max_gap))
            if n_ok % 15 == 0:
                C.ensure_job_list()
        elif st in ("already", "dry", "no_fit"):
            n_skip += 1
            if st == "dry":
                n_dry += 1
                mark = f"fit={'Y' if r.get('fit') else 'N'}/{r.get('score')}"
            elif st == "no_fit":
                mark = f"fit=N({r.get('why')})"
            else:
                mark = ""
            consec = 0
            log(r)
            p(f"      {st:<7} {mark:<20} [{r.get('cat')}] "
              f"{r.get('company')} | {r.get('job')}")
            time.sleep(0.6)
        elif st == "no_chat" and r.get("limit"):
            log(r)
            p("STOP: daily-limit signal from app")
            abort = "daily_limit"
            break
        else:
            n_fail += 1
            consec += 1
            log(r)
            p(f"      FAIL {st} {r.get('job','')} act={r.get('activity','')}")
            if consec >= 4:
                abort = "consecutive_failures"
                break
            time.sleep(1.5)

    dt = (time.time() - t0) / 60
    p(f"DONE ok={n_ok} skip={n_skip} dry={n_dry} fail={n_fail} scrolls={scrolls} {dt:.1f}min abort={abort}")
    return {"ok": n_ok, "skip": n_skip, "dry": n_dry, "fail": n_fail, "scrolls": scrolls,
            "minutes": round(dt, 1), "cats": cats, "aborted": abort}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--min-gap", type=float, default=7.0)
    ap.add_argument("--max-gap", type=float, default=15.0)
    ap.add_argument("--max-scrolls", type=int, default=600)
    a = ap.parse_args()
    run(a.limit, a.dry, a.min_gap, a.max_gap, a.max_scrolls)

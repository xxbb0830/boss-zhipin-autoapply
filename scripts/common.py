# -*- coding: utf-8 -*-
"""Shared driver + app guards + UI parsers for the BOSS直聘 apply skill."""
import os, sys, time, re, functools, random, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _cfg_paths():
    """从 config/profile.yaml 的 paths 段取路径（没有就返回空 dict）。"""
    try:
        import profile as P
        return (P.load() or {}).get("paths") or {}
    except Exception:
        return {}


def profile_limits():
    """config/profile.yaml 的 limits 段（daily / reserve / log_keep_days）。"""
    try:
        import profile as P
        return (P.load() or {}).get("limits") or {}
    except Exception:
        return {}


_PATHS = _cfg_paths()


def _find_adb():
    for c in (os.path.join(ROOT, "tools", "platform-tools", "adb.exe"),
              os.path.join(ROOT, "tools", "platform-tools", "adb"),
              os.path.join(ROOT, "tools", "adb.exe"),
              os.path.join(ROOT, "tools", "adb")):
        if os.path.exists(c):
            return c
    return shutil.which("adb") or "adb"


# 三级回退：环境变量 → profile.paths → 自动探测
ADB = os.environ.get("BOSS_ADB") or _PATHS.get("adb") or _find_adb()
DATA = (os.environ.get("BOSS_DATA") or _PATHS.get("data")
        or os.path.join(ROOT, "data"))
LIBS = os.environ.get("BOSS_LIBS") or _PATHS.get("libs") or ""

os.environ.setdefault("ADBUTILS_ADB_PATH", ADB)
if LIBS and os.path.isdir(LIBS):
    sys.path.insert(0, LIBS)
os.makedirs(DATA, exist_ok=True)

import uiautomator2 as u2
from lxml import etree

PKG = "com.hpbr.bosszhipin"
ID = "com.hpbr.bosszhipin:id/"
EDIT_ID = ID + "editText_with_scrollbar"

_dev = None


def dev(force=False):
    global _dev
    if _dev is None or force:
        for i in range(5):
            try:
                d = u2.connect()
                d.settings["wait_timeout"] = 8.0
                _dev = d
                return d
            except Exception as e:
                print(f"[drv] connect retry {i}: {e}", flush=True)
                time.sleep(3)
        raise RuntimeError("u2 connect failed")
    return _dev


def robust(fn=None, *, tries=4, delay=2.0):
    def deco(f):
        @functools.wraps(f)
        def wrapper(*a, **kw):
            last = None
            for i in range(tries):
                try:
                    return f(*a, **kw)
                except Exception as e:
                    last = e
                    print(f"[drv] {f.__name__} try{i}: {type(e).__name__} {str(e)[:100]}", flush=True)
                    time.sleep(delay * (i + 1))
                    try:
                        dev(force=True)
                    except Exception:
                        pass
            raise last
        return wrapper
    return deco(fn) if fn else deco


# ---------------- housekeeping ----------------
def _file_date(path):
    """从文件名里的 YYYYMMDD 取日期，取不到就用 mtime。"""
    import datetime
    m = re.search(r"(\d{8})", os.path.basename(path))
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    return datetime.date.fromtimestamp(os.path.getmtime(path))


def cleanup_logs(keep_days=1, max_reports=5, verbose=True):
    """只保留最近 keep_days 天（含今天）的日志和报告，默认只留当天。

    按文件名里的日期判断，而不是按 mtime —— 这样「昨天 17:43 的日志」
    在今天早上就会被清掉，不用等满 24 小时。
    台账 applied.jsonl、quota.json、history.jsonl 一律不碰，
    那些是断点续跑要用的，删了会重复投递。
    """
    import datetime
    import glob
    today = datetime.date.today()
    oldest = today - datetime.timedelta(days=max(0, int(keep_days) - 1))
    removed = []
    for pat in ("auto_*.log", "report_*.md"):
        for f in glob.glob(os.path.join(DATA, pat)):
            try:
                if _file_date(f) < oldest:
                    os.remove(f)
                    removed.append(os.path.basename(f))
            except OSError:
                pass

    # 报告一次运行一份，同一天会攒很多，只留最新的几份
    reports = sorted(glob.glob(os.path.join(DATA, "report_*.md")),
                     key=os.path.getmtime, reverse=True)
    for f in reports[max_reports:]:
        try:
            os.remove(f)
            removed.append(os.path.basename(f))
        except OSError:
            pass

    if verbose and removed:
        print(f"[cleanup] 清理 {len(removed)} 个过期日志/报告"
              f"（保留最近 {keep_days} 天、最多 {max_reports} 份报告）", flush=True)
    return removed


# ---------------- primitives ----------------
# 所有坐标都是按 1440x3200 写死的（脚本就是在这台机器上标定出来的）。
# 换手机时按实际分辨率等比缩放，调用方不用改一行代码。
BASE_W, BASE_H = 1440, 3200
_scale = None


def scale():
    """返回 (sx, sy)。首次调用时读一次设备分辨率。"""
    global _scale
    if _scale is None:
        _scale = (1.0, 1.0)
        try:
            info = dev().info or {}
            w, h = info.get("displayWidth"), info.get("displayHeight")
            if w and h:
                _scale = (w / BASE_W, h / BASE_H)
        except Exception:
            pass
    return _scale


@robust
def dump_xml():
    return dev().dump_hierarchy()


@robust
def tap(x, y, wait=1.0):
    sx, sy = scale()
    dev().click(int(round(x * sx)), int(round(y * sy)))
    time.sleep(wait)


@robust
def swipe(x1, y1, x2, y2, dur=0.35, wait=1.0):
    sx, sy = scale()
    dev().swipe(int(round(x1 * sx)), int(round(y1 * sy)),
                int(round(x2 * sx)), int(round(y2 * sy)), dur)
    time.sleep(wait)


@robust
def back(wait=1.2):
    dev().press("back")
    time.sleep(wait)


@robust
def tap_id(rid, timeout=6.0):
    d = dev()
    el = d(resourceId=ID + rid)
    if el.wait(timeout=timeout):
        el.click()
        time.sleep(1.0)
        return True
    return False


@robust
def tap_text(txt, timeout=5.0):
    d = dev()
    el = d(text=txt)
    if el.wait(timeout=timeout):
        el.click()
        time.sleep(1.2)
        return True
    return False


def cur_pkg():
    try:
        return dev().app_current().get("package", "")
    except Exception:
        return ""


def cur_act():
    try:
        return dev().app_current().get("activity", "")
    except Exception:
        return ""


# ---------------- app guards ----------------
def ensure_boss(max_steps=8):
    """Make BOSS直聘 the foreground app and return to its main activity."""
    d = dev()
    for _ in range(max_steps):
        if cur_pkg() != PKG:
            print("[guard] other app foreground -> relaunch BOSS", flush=True)
            try:
                d.app_start(PKG, stop=False)
            except Exception:
                pass
            time.sleep(3.5)
            continue
        if "MainActivity" in cur_act():
            return True
        back(1.3)
    return "MainActivity" in cur_act()


def ensure_job_list(max_steps=8):
    """Ensure we are on the 职位 tab showing a scrollable job list."""
    ensure_boss()
    d = dev()
    for _ in range(max_steps):
        xml = dump_xml()
        if 'resource-id="' + ID + 'tv_position_name"' in xml:
            return True
        # try the 职位 tab
        try:
            if d(resourceId=ID + "cl_tab_1").exists(timeout=2):
                d(resourceId=ID + "cl_tab_1").click()
                time.sleep(2.0)
                continue
        except Exception:
            pass
        back(1.2)
    xml = dump_xml()
    return 'tv_position_name' in xml


# ---------------- parsing ----------------
def _b(n):
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", n.get("bounds") or "")
    return tuple(int(g) for g in m.groups()) if m else None


def rid(n):
    return (n.get("resource-id") or "").replace(ID, "")


def _clean(s):
    return re.sub(r"[\s@&%·•]+$", "", (s or "").strip())


def parse_cards(xml):
    """Visible job cards on a list screen."""
    root = etree.fromstring(xml.encode("utf-8"))
    ns = []
    for n in root.iter("node"):
        b = _b(n)
        if b:
            ns.append((b, rid(n), (n.get("text") or "").strip()))
    anchors = sorted([(b, _clean(t)) for b, r, t in ns if r == "tv_position_name"],
                     key=lambda a: a[0][1])
    cards = []
    for i, (ab, at) in enumerate(anchors):
        lo = ab[1] - 40
        hi = anchors[i + 1][0][1] - 40 if i + 1 < len(anchors) else 10 ** 9
        rec = {"title": at, "company": "", "salary": "", "exp": "", "degree": "",
               "y": ab[1], "y_mid": (ab[1] + ab[3]) // 2}
        for b, r, t in ns:
            if not (lo <= b[1] < hi):
                continue
            if r == "tv_company_name":
                rec["company"] = _clean(t)
            elif r == "tv_salary_statue":
                rec["salary"] = t
            elif r == "" and t and b[0] < 900:
                if not rec["exp"] and re.search(r"(应届|在校|\d-\d年)$", t):
                    rec["exp"] = t
                elif not rec["degree"] and re.fullmatch(r"(本科|大专|硕士|博士|中专|学历不限)", t):
                    rec["degree"] = t
        if rec["title"]:
            cards.append(rec)
    return cards


def parse_detail(xml):
    """Job detail page fields."""
    root = etree.fromstring(xml.encode("utf-8"))
    out = {"job": "", "company": "", "salary": "", "btn": "", "jd": "",
           "exp": "", "degree": "", "boss": ""}
    for n in root.iter("node"):
        r = rid(n)
        t = (n.get("text") or "").strip()
        if r == "tv_job_name":
            out["job"] = _clean(t)
        elif r == "tv_boss_title":
            out["company"] = _clean(t.split("•")[0])
        elif r == "tv_job_salary":
            out["salary"] = t
        elif r == "btn_chat":
            out["btn"] = t
        elif r == "tv_description":
            out["jd"] = t
        elif r == "tv_required_work_exp":
            out["exp"] = t
        elif r == "tv_required_degree":
            out["degree"] = t
        elif r == "tv_boss_name":
            out["boss"] = t
    return out


def find_send_button(xml):
    """Locate the send control in the chat input row.

    The row is: [voice] [EditText] [emoji] [send].  There is NO resource-id on
    the send button, and the emoji button is also clickable and sits closer to
    the EditText — so we must take the RIGHTMOST clickable node of the row,
    never the leftmost (that bug tapped emoji and never sent).
    """
    root = etree.fromstring(xml.encode("utf-8"))
    et_b = None
    for n in root.iter("node"):
        if rid(n) == "editText_with_scrollbar":
            et_b = _b(n)
            break
    if not et_b:
        return None
    cands = []
    for n in root.iter("node"):
        if n.get("clickable") != "true":
            continue
        b = _b(n)
        if not b:
            continue
        same_row = b[1] <= et_b[3] and b[3] >= et_b[1]
        right_of = b[0] >= et_b[2] - 40
        small = (b[2] - b[0]) < 400 and (b[3] - b[1]) < 400
        if same_row and right_of and small:
            cands.append(b)
    if not cands:
        return None
    cands.sort(key=lambda b: b[2])          # rightmost by right edge
    b = cands[-1]
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def chat_input_row(xml):
    """All clickable nodes in the chat input row, right of the EditText, by x."""
    root = etree.fromstring(xml.encode("utf-8"))
    et_b = None
    for n in root.iter("node"):
        if rid(n) == "editText_with_scrollbar":
            et_b = _b(n)
            break
    out = []
    if not et_b:
        return et_b, out
    for n in root.iter("node"):
        if n.get("clickable") != "true":
            continue
        b = _b(n)
        if not b:
            continue
        if b[1] <= et_b[3] and b[3] >= et_b[1] and b[0] >= et_b[2] - 40:
            if (b[2] - b[0]) < 400:
                out.append(((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, b))
    out.sort(key=lambda t: t[2][2])
    return et_b, out


def screen_texts(xml):
    root = etree.fromstring(xml.encode("utf-8"))
    return [(n.get("text") or "").strip() for n in root.iter("node")
            if (n.get("text") or "").strip()]


def sleep(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))

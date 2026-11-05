# -*- coding: utf-8 -*-
"""One-shot unattended runner: device check -> quota -> apply -> report.

    python auto.py                 # full run, respects the 150/day cap
    python auto.py --limit 20      # cap this run
    python auto.py --dry           # open details only, send nothing
    python auto.py --report-only   # just rebuild the report from the ledger

Everything is appended to auto_YYYYMMDD.log and a Markdown report is written
next to the ledger. Safe to re-run: the ledger makes it resumable.
"""
import os, sys, time, json, argparse, traceback, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

DATA = C.DATA
LEDGER = os.path.join(DATA, "applied.jsonl")
DAILY_LIMIT = 150
RESERVE = 2          # leave a couple of the daily budget untouched


class Tee:
    """Duplicate stdout into a log file."""
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8")

    def write(self, s):
        sys.__stdout__.write(s)
        sys.__stdout__.flush()
        self.f.write(s)
        self.f.flush()

    def flush(self):
        sys.__stdout__.flush()
        self.f.flush()


def p(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_device(timeout=300, label=""):
    """Block until an authorized device shows up."""
    import subprocess
    end = time.time() + timeout
    last = 0
    while time.time() < end:
        try:
            r = subprocess.run(f'"{C.ADB}" devices', shell=True, capture_output=True,
                               text=True, timeout=15, encoding="utf-8", errors="replace")
            lines = [l for l in (r.stdout or "").splitlines()
                     if l.strip() and "List of devices" not in l]
            if any("device" in l and "offline" not in l and "unauthorized" not in l
                   for l in lines):
                return True
            state = "offline" if any("offline" in l for l in lines) else \
                    "unauthorized" if any("unauthorized" in l for l in lines) else "absent"
        except Exception:
            state = "adb-error"
        waited = int(time.time() - (end - timeout))
        if waited - last >= 30:
            last = waited
            print(f"[{time.strftime('%H:%M:%S')}] waiting for device "
                  f"({waited}s/{timeout}s) state={state} {label}", flush=True)
        time.sleep(5)
    return False


def build_report(stats, quota, extra=""):
    rs = []
    if os.path.exists(LEDGER):
        for line in open(LEDGER, encoding="utf-8"):
            try:
                rs.append(json.loads(line))
            except Exception:
                pass
    ok = [r for r in rs if r.get("status") == "ok"]
    today = time.strftime("%Y-%m-%d")
    ok_today = [r for r in ok if (r.get("ts") or "").startswith(today)]
    cats = collections.Counter(r.get("cat") for r in ok_today)
    comps = collections.Counter(r.get("company") for r in ok_today)

    lines = []
    lines.append(f"# BOSS直聘 自动投递报告 {time.strftime('%Y-%m-%d %H:%M')}\n")
    if quota and quota.get("used") is not None:
        lines.append(f"- 今日运行前已沟通：**{quota['used']}** / {quota['limit']}"
                     f"（剩余 {quota['remaining']}）")
    if stats:
        lines.append(f"- 本次成功投递：**{stats.get('ok', 0)}** ｜ 跳过 {stats.get('skip', 0)}"
                     f" ｜ 失败 {stats.get('fail', 0)} ｜ 耗时 {stats.get('minutes', 0)} 分钟")
        if stats.get("aborted"):
            lines.append(f"- 结束原因：`{stats['aborted']}`")
    lines.append(f"- 台账累计成功：**{len(ok)}** ｜ 今日台账成功：**{len(ok_today)}**")
    lines.append("")
    if cats:
        lines.append("## 话术分类分布（今日）\n")
        lines.append("| 类别 | 数量 |\n| --- | --- |")
        for k, v in cats.most_common():
            lines.append(f"| `{k}` | {v} |")
        lines.append("")
    if ok_today:
        lines.append("## 今日投递明细\n")
        lines.append("| 时间 | 公司 | 岗位 | 薪资 | 类别 |\n| --- | --- | --- | --- | --- |")
        for r in ok_today[-200:]:
            lines.append(f"| {r.get('ts','')[11:16]} | {r.get('company','')} | "
                         f"{r.get('title','')} | {r.get('salary','')} | `{r.get('cat','')}` |")
        lines.append("")
    if extra:
        lines.append("## 备注\n")
        lines.append(extra)
        lines.append("")

    path = os.path.join(DATA, f"report_{time.strftime('%Y%m%d_%H%M')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    p(f"report -> {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DAILY_LIMIT)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-quota", action="store_true", help="skip the quota probe")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--wait-device", type=int, default=300,
                    help="seconds to wait for the phone before giving up")
    a = ap.parse_args()

    logpath = os.path.join(DATA, f"auto_{time.strftime('%Y%m%d')}.log")
    sys.stdout = Tee(logpath)
    p("=" * 60)
    p(f"auto.py start  dry={a.dry}  limit={a.limit}  log={logpath}")

    if a.report_only:
        build_report(None, None)
        return

    if not wait_device(a.wait_device, "initial"):
        p("FATAL: no authorized device in 5 min — 检查 USB 调试授权")
        build_report(None, None, "设备未连接，未执行投递。")
        return
    p("device OK")

    try:
        C.ensure_boss()
    except Exception as e:
        p(f"warn ensure_boss: {e}")

    # ---- quota ----
    quota = None
    if not a.no_quota:
        import quota as Q
        try:
            p("counting today's 沟通 ...")
            quota = Q.count(verbose=False)
            p(f"quota: used={quota.get('used')} remaining={quota.get('remaining')}")
        except Exception as e:
            p(f"quota probe failed: {type(e).__name__} {e}")
    if quota and quota.get("remaining") is not None:
        remaining = quota["remaining"]
        limit = min(a.limit, max(0, remaining - RESERVE))
        if limit <= 0:
            p("nothing left in today's budget — stopping")
            build_report(None, quota, "今日额度已用完（或接近上限），未执行投递。")
            return
    else:
        limit = min(a.limit, 100)
        p(f"quota unknown -> conservative limit={limit}")

    p(f"will apply up to {limit}")
    C.ensure_job_list()

    # ---- apply with device-loss retry ----
    import apply as A
    stats, attempt = None, 0
    while attempt < a.max_attempts:
        attempt += 1
        p(f"--- attempt {attempt}/{a.max_attempts} ---")
        try:
            s = A.run(limit=limit, dry=a.dry)
            stats = s if stats is None else {k: (stats.get(k, 0) + s.get(k, 0))
                                             if isinstance(s.get(k), (int, float)) else s.get(k)
                                             for k in s}
            if a.dry or s.get("ok", 0) > 0 or s.get("aborted") in ("daily_limit",):
                break
        except Exception as e:
            p(f"attempt {attempt} crashed: {type(e).__name__} {e}")
            traceback.print_exc(file=sys.stdout)
        p("waiting 30s before retry ...")
        time.sleep(30)
        if not wait_device(min(180, a.wait_device), "retry"):
            p("device lost — stopping")
            break
        try:
            C.dev(force=True)
            C.ensure_job_list()
        except Exception:
            pass

    build_report(stats, quota,
                 "话术为按 JD 归类的预制文案（每类固定，仅替换岗位名）；"
                 "同一公司不会重复投递（台账去重）。")
    p("auto.py finished")


if __name__ == "__main__":
    main()

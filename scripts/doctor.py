# -*- coding: utf-8 -*-
"""Read-only health check: ADB, device, app, uiautomator2, ledger state."""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def sh(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


def main():
    print("== BOSS直聘 autoapply doctor ==\n")
    print(f"adb      : {C.ADB}  exists={os.path.exists(C.ADB)}")
    print(f"libs     : {C.LIBS}  exists={os.path.exists(C.LIBS)}")
    print(f"data dir : {C.DATA}")

    rc, out = sh(f'"{C.ADB}" devices -l')
    lines = [l for l in out.splitlines() if l.strip() and "List of devices" not in l]
    if any("device" in l and "offline" not in l for l in lines):
        print(f"{OK} device: {lines[0].strip()}")
    else:
        print(f"{BAD} no authorized device — enable USB调试, choose MTP, accept the prompt")
        print("       raw:", out.strip()[:200])
        return

    rc, out = sh(f'"{C.ADB}" shell pm list packages com.hpbr.bosszhipin')
    print(f"{OK if 'bosszhipin' in out else BAD} app installed: {'yes' if 'bosszhipin' in out else 'NO'}")

    rc, out = sh(f'"{C.ADB}" shell wm size')
    print(f"       screen: {out.strip()}")

    try:
        d = C.dev()
        print(f"{OK} uiautomator2 connected")
        print(f"       current: {d.app_current().get('package')} / {d.app_current().get('activity')}")
    except Exception as e:
        print(f"{BAD} uiautomator2: {e}")
        return

    # app in foreground?
    if C.cur_pkg() == C.PKG:
        print(f"{OK} BOSS is foreground")
    else:
        print(f"{WARN} foreground is {C.cur_pkg()!r} — apply.py will re-focus BOSS")

    # ledger / quota
    led = os.path.join(C.DATA, "applied.jsonl")
    if os.path.exists(led):
        n = sum(1 for l in open(led, encoding="utf-8")
                if l.strip() and json.loads(l).get("status") == "ok")
        print(f"{OK} ledger: {n} applied ({led})")
    else:
        print(f"       ledger: none yet")
    q = os.path.join(C.DATA, "quota.json")
    if os.path.exists(q):
        print("       quota:", json.load(open(q, encoding="utf-8")))
    else:
        print("       quota: unknown — run quota.py")
    print("\nready.")


if __name__ == "__main__":
    main()

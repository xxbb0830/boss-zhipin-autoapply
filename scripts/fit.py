# -*- coding: utf-8 -*-
"""胜任度判断：进详情页读完 JD 后，判断「这个活我干得了吗」。

判断依据全部来自 config/profile.yaml，代码里没有任何硬编码的个人信息：

  1. 岗位名称命中 block_titles（销售/客服/运营…）→ 不投
  2. 岗位名称是技术岗（dev_titles）→ 看 JD 里有没有 skills 里的技术；
     一个都没有 → 不投（技术栈不对，如嵌入式/C++）
  3. 岗位名称看不出是什么岗（BOSS 上大量「线上面试（离职优先）」
     「急招/内推/双休」这类钩子标题）→
       · JD 里技术权重 ≥ fit.min_score → 投
       · JD 正文命中 block_body（门店/提成/销售指标…）→ 不投
       · JD 短于 fit.short_jd 字 → **放行**（信息不足不判死）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile as P


def _hits(text, table):
    return [k for k in table if k in text]


def judge(title, jd=""):
    """返回 (ok, reason, hits, score)。

    reason: 'ok' / 'ok_short_jd' / 'blocked:<词>' / 'blocked_body:<词>' /
            'non_tech' / 'no_tech_match'
    """
    cfg = P.load()
    known = P.skills()
    min_score = cfg["fit"]["min_score"]
    short_jd = cfg["fit"]["short_jd"]

    t = (title or "").lower()
    body = ((title or "") + "\n" + (jd or "")).lower()
    jd_len = len(jd or "")

    for b in cfg["block_titles"]:
        if str(b).lower() in t:
            return False, f"blocked:{b}", [], 0

    title_hits = _hits(t, known)
    jd_hits = _hits(body, known)
    score = sum(known[k] for k in jd_hits)
    is_dev = any(str(d).lower() in t for d in cfg["dev_titles"])

    # ① 标题就是技术岗：技术栈对不上就不投
    if is_dev or title_hits:
        if jd_hits:
            return True, "ok", jd_hits, score
        return False, "no_tech_match", [], 0

    # ② 标题看不出岗位（钩子标题）
    if score >= min_score:
        return True, "ok", jd_hits, score
    for b in cfg["block_body"]:
        if str(b).lower() in body:
            return False, f"blocked_body:{b}", jd_hits, score
    if jd_len < short_jd:
        return True, "ok_short_jd", jd_hits, score
    return False, "non_tech", jd_hits, score


def can_do(title, jd=""):
    return judge(title, jd)[0]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"配置: {P.info()}\n")
    cases = [
        ("AI Agent开发工程师", "负责ReAct智能体、工具调用、LangGraph编排，Python"),
        ("大模型算法工程师", "要求硕士，5年以上，熟悉Transformer、LoRA微调、PyTorch"),
        ("Java开发工程师（AI方向）", "Java、SpringBoot，了解大模型应用"),
        ("销售代表", "负责AI产品销售，底薪6-8K"),
        ("嵌入式开发工程师", "C++、STM32、驱动开发"),
        ("产品经理（AI）", "负责大模型产品规划，需求分析"),
        ("数据分析师", "SQL、Excel、BI报表，pandas"),
        ("资深后端开发工程师", "Go语言，K8s，高并发微服务"),
        # 钩子标题：JD 写得潦草，信息不足 → 放行
        ("线上面试（离职优先）", "岗位职责：负责公司AI相关产品研发，本科以上，双休，五险一金。"),
        ("急招！双休", "负责门店日常运营，接待客户，完成销售指标，底薪加提成。"),
    ]
    for t, jd in cases:
        ok, why, hits, sc = judge(t, jd)
        flag = "投" if ok else "跳过"
        print(f"[{flag}] {t:<24} {why:<18} score={sc:<3} hits={hits[:6]}")

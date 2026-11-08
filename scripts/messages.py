# -*- coding: utf-8 -*-
"""一次性开场话术：固定短句，按岗位类别分档。

话术和类别关键词都来自 config/profile.yaml（由 onboard.py 读简历生成），
代码里不写任何具体文案 —— 换个人用 = 换一份配置。

设计约束（用户口径）：
  * 话术「分几类」，按对方招的岗位类型分 —— 不按岗位实时生成
  * 用提前做好的固定模板，不替换岗位名
  * 字数上限由 fit.max_message_len 控制（默认 80 字）
  * 口语化，像自己说话：我做过什么 + 怎么做的
  * 结尾不要「可聊」这种轻浮收尾，落在具体动作上：
      技术岗反问一句（您这边…？），通用岗直接说「合适的话我把简历发您」

BOSS 点「立即沟通」时 App 会自动发一条默认打招呼，
这条是我们紧接着补的第二句。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile as P


def classify(title, jd=""):
    """Return the best-matching category key from job title + JD text."""
    cats = P.categories()
    text = ((title or "") + " " + (jd or "")).lower()
    best, best_score = "default", 0
    for cat, kws in cats.items():
        score = 0
        for kw in kws:
            score += text.count(kw)
        t = (title or "").lower()
        score += 3 * sum(1 for kw in kws if kw in t)
        if score > best_score:
            best, best_score = cat, score
    return best


def build(job, jd="", company=""):
    """Return (category, message)。固定模板，不替换岗位名。"""
    cat = classify(job, jd)
    tpl = P.messages()
    msg = tpl.get(cat) or tpl.get("default") or ""
    return cat, msg


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"配置: {P.info()}\n")
    max_len = P.load()["fit"]["max_message_len"]
    tpl = P.messages()
    for k, v in tpl.items():
        flag = "OK " if len(v) <= max_len else "超长"
        print(f"  [{flag}] {k:<8} {len(v):>2}字  {v}")
    print()
    tests = [
        ("大模型开发工程师", "负责RAG知识库检索增强，向量数据库，召回优化"),
        ("Agent Harness工程师", "智能体工作流编排，工具调用，ReAct"),
        ("AI全栈开发（应届生）", "后端接口开发，Python FastAPI 并发"),
        ("数据开发工程师（ai agent）", "数仓 ETL Hive Spark 数据治理"),
        ("AI应用开发工程师", "参与大模型应用落地"),
    ]
    for t, jd in tests:
        c, m = build(t, jd)
        print(f"[{c:<7}] {len(m):>2}字  {m}   <- {t}")
    probs = P.validate()
    if probs:
        print("\n配置有问题：")
        for p in probs:
            print("  -", p)
    else:
        print("\n配置校验通过")

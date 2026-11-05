# -*- coding: utf-8 -*-
"""Targeting rules — 只看「还在招」，不看学历 / 经验 / 薪资。

用户口径（2026-11-05 明确）：
  * 学历、经验、薪资 **一律不筛**，写硕士博士、写 6-8K 都照投
  * 唯一的硬门槛：岗位还在招（停止招聘 / 已关闭 才跳过）
  * 「能不能胜任」不在这里判断 —— 列表卡片上没有 JD，
    真正的判断在 fit.py，进详情页读完岗位职责后再决定投不投
"""

import re

# 停招 / 下线标记
CLOSED_MARKS = ("停止招聘", "已停止招聘", "职位已关闭", "已下线", "已结束")


def parse_salary(s):
    """'15-30K·13薪' -> (15,30);  '面议'/'停止招聘' -> None.

    Only the numbers BEFORE the first K/千 belong to the range; trailing
    13薪/14薪 must not be read as part of it.
    仅用于报告展示，不再参与筛选。
    """
    if not s:
        return None
    if any(k in s for k in ("面议", "停止招聘", "薪资面议")):
        return None
    m = re.search(r"(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)\s*[Kk千]", s.replace(" ", ""))
    if not m:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(1))]
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0], nums[0])
    return (min(nums), max(nums))


def still_open(s):
    """还在招 = 没有停招标记。薪资高低、面议都放行。"""
    s = s or ""
    return not any(k in s for k in CLOSED_MARKS)


def card_ok(card):
    """列表卡片唯一门槛：岗位还在招。

    学历、经验年限、薪资区间都不看 —— 用户口径是「只要能投就投，
    能不能干进详情页看完 JD 再判断」。
    """
    return still_open(card.get("salary"))


if __name__ == "__main__":
    samples = ["15-30K·13薪", "面议", "6-8K", "50-80K", "停止招聘", "3-5K"]
    for s in samples:
        print(f"  {s:<14} band={str(parse_salary(s)):<12} keep={still_open(s)}")

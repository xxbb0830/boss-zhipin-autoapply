# -*- coding: utf-8 -*-
"""统一加载 config/profile.yaml —— 项目里所有「个人化」内容都从这里来。

设计原则：**代码里不写任何个人信息**。
技能清单、话术模板、岗位类别、拦截词全部来自配置文件，
换一个人用 = 换一个 profile.yaml（由 scripts/onboard.py 读简历生成）。

查找顺序：
  1. $BOSS_PROFILE 指定的路径
  2. <项目根>/config/profile.yaml          ← 你自己的（.gitignore，不入库）
  3. <项目根>/config/profile.example.yaml  ← 仓库里的通用模板
"""
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
USER_PROFILE = os.path.join(CONFIG_DIR, "profile.yaml")
EXAMPLE_PROFILE = os.path.join(CONFIG_DIR, "profile.example.yaml")

_cache = {}


def resolve_path():
    p = os.environ.get("BOSS_PROFILE")
    if p and os.path.exists(p):
        return p, "env"
    if os.path.exists(USER_PROFILE):
        return USER_PROFILE, "user"
    if os.path.exists(EXAMPLE_PROFILE):
        return EXAMPLE_PROFILE, "example"
    raise FileNotFoundError(
        "找不到 config/profile.yaml。\n"
        "先跑一次：python scripts/onboard.py --resume 你的简历.pdf\n"
        "它会读你的简历生成配置；也可以复制 config/profile.example.yaml 手动改。"
    )


def load(reload=False):
    """返回配置 dict（带默认值兜底）。"""
    if _cache and not reload:
        return _cache["data"]
    if yaml is None:
        raise RuntimeError("缺少 PyYAML：pip install -r requirements.txt")
    path, source = resolve_path()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data.setdefault("candidate", {})
    data.setdefault("paths", {})
    data.setdefault("skills", {})
    data.setdefault("categories", {})
    data.setdefault("messages", {})
    data.setdefault("block_titles", [])
    data.setdefault("block_body", [])
    data.setdefault("dev_titles", ["开发", "工程师", "研发", "算法", "技术"])
    data.setdefault("fit", {})
    data["fit"].setdefault("min_score", 3)
    data["fit"].setdefault("short_jd", 200)
    data["fit"].setdefault("max_message_len", 80)
    data.setdefault("limits", {})
    data["limits"].setdefault("daily", 150)
    data["limits"].setdefault("reserve", 2)
    data["limits"].setdefault("log_keep_days", 1)      # 超过 1 天自动删
    data["limits"].setdefault("log_enabled", True)     # False = 压根不写日志

    data["_path"] = path
    data["_source"] = source
    _cache["data"] = data
    return data


def skills():
    """{技术词: 权重} —— 权重 3 核心 / 2 熟练 / 1 了解。"""
    return {str(k).lower(): int(v) for k, v in load()["skills"].items()}


def categories():
    return {k: [str(x).lower() for x in v] for k, v in load()["categories"].items()}


def messages():
    return {k: str(v) for k, v in load()["messages"].items()}


def candidate():
    return load()["candidate"]


def info():
    d = load()
    return f"{d['_path']} (source={d['_source']})"


def validate(data=None):
    """返回问题列表，空列表表示配置可用。"""
    d = data or load()
    problems = []
    if not d["skills"]:
        problems.append("skills 为空：没有技能清单就没法判断「能不能胜任」")
    if not d["categories"]:
        problems.append("categories 为空：没有分类就没法挑话术")
    if not d["messages"]:
        problems.append("messages 为空：没有话术模板")
    max_len = d["fit"]["max_message_len"]
    for cat, msg in d["messages"].items():
        if len(msg) > max_len:
            problems.append(f"messages.{cat} 有 {len(msg)} 字，超过 {max_len} 字上限")
        if not msg.strip():
            problems.append(f"messages.{cat} 是空的")
    missing = [c for c in d["categories"] if c not in d["messages"]]
    if missing:
        problems.append(f"这些类别没有对应话术：{missing}")
    return problems


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = load()
    print(f"配置文件 : {d['_path']}  (source={d['_source']})")
    print(f"候选人   : {d['candidate'].get('name') or '(未填)'} / "
          f"{d['candidate'].get('city', '')}")
    print(f"技能     : {len(d['skills'])} 个")
    print(f"类别     : {list(d['categories'])}")
    for c, m in d["messages"].items():
        print(f"  {c:<8} {len(m):>2}字  {m}")
    probs = validate(d)
    print("\n校验:", "通过" if not probs else "")
    for p in probs:
        print("  -", p)

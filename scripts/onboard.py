# -*- coding: utf-8 -*-
"""读简历 → 生成 config/profile.yaml 草稿。

别人的使用姿势：
    python scripts/onboard.py --resume 我的简历.pdf --city 北京
    # 看一眼生成的 config/profile.yaml，把话术改成自己的项目
    python scripts/onboard.py --check

它会做三件事：
  1. 从简历里抽出你真会的技术词（带权重），生成 skills
  2. 从简历里挑出项目相关的句子，打印出来给你写话术当素材
  3. 按类别生成话术草稿（**草稿，必须人工改**）

支持 .pdf / .docx / .txt / .md
"""
import argparse
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile as P

# ---- 岗位类别 → 关键词（通用，不含个人信息）----
CATEGORIES = {
    "rag": ["rag", "检索增强", "知识库", "向量", "faiss", "chroma", "milvus",
            "embedding", "召回", "bm25", "问答", "语义检索", "文档解析"],
    "agent": ["agent", "智能体", "工作流", "编排", "工具调用", "react", "mcp",
              "function calling", "多智能体", "coze", "dify", "自动化流程"],
    "llm": ["大模型", "llm", "算法", "nlp", "微调", "lora", "dpo", "transformer",
            "pytorch", "tensorflow", "深度学习", "机器学习", "模型训练", "推理优化"],
    "eng": ["后端", "服务端", "python", "fastapi", "django", "flask", "全栈",
            "接口", "并发", "asyncio", "微服务", "docker", "linux", "java",
            "spring", "go", "kubernetes", "redis", "mysql", "postgresql"],
    "data": ["数据开发", "数仓", "etl", "hive", "spark", "flink", "爬虫",
             "采集", "sql", "数据分析", "bi", "数据治理", "pandas", "hadoop"],
}

# 补充技术词（不在类别里但值得写进 skills）
EXTRA_VOCAB = [
    "pydantic", "sqlalchemy", "aiohttp", "streamlit", "git", "hbase",
    "numpy", "opencv", "kafka", "nginx", "jenkins", "ci/cd", "vue",
    "typescript", "javascript", "html", "css", "c++", "c#", "php", "ruby",
    "restful", "grpc", "单元测试", "分布式", "高并发", "消息队列",
    "langchain", "langgraph", "llamaindex", "提示词", "prompt",
    "推荐系统", "搜索引擎", "排序", "aigc", "生成式",
]

BLOCK_TITLES = ["销售", "客服", "运营", "人事", "行政", "财务", "会计", "法务",
                "教师", "讲师", "主播", "司机", "配送", "导购", "中介", "房产",
                "文案", "编辑", "平面设计", "视频剪辑", "机械", "电气", "土木",
                "施工", "医药代表", "护士", "翻译", "产品经理", "项目经理"]

BLOCK_BODY = ["门店", "销售指标", "提成", "接待客户", "地推", "电销",
              "招商", "加盟", "导购", "收银", "美容", "健身", "保险代理"]

DEV_TITLES = ["开发", "工程师", "研发", "算法", "架构", "技术", "程序",
              "全栈", "后端", "数据", "ai", "人工智能", "机器学习"]

PROJECT_HINTS = ("项目", "系统", "平台", "负责", "实现", "落地", "优化",
                 "架构", "设计", "开发")

# 技术词的正常写法（简历里是小写，写进话术要好看）
DISPLAY = {
    "rag": "RAG", "llm": "LLM", "agent": "Agent", "python": "Python",
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask",
    "hive": "Hive", "etl": "ETL", "sql": "SQL", "nlp": "NLP",
    "lora": "LoRA", "dpo": "DPO", "pytorch": "PyTorch",
    "tensorflow": "TensorFlow", "transformer": "Transformer",
    "docker": "Docker", "mysql": "MySQL", "redis": "Redis",
    "postgresql": "PostgreSQL", "hbase": "HBase", "pandas": "pandas",
    "numpy": "numpy", "asyncio": "asyncio", "aiohttp": "aiohttp",
    "faiss": "FAISS", "bm25": "BM25", "mcp": "MCP", "react": "ReAct",
    "dify": "Dify", "coze": "Coze", "langchain": "LangChain",
    "langgraph": "LangGraph", "spring": "Spring", "java": "Java",
    "go": "Go", "linux": "Linux", "kubernetes": "K8s", "kafka": "Kafka",
    "spark": "Spark", "flink": "Flink", "hadoop": "Hadoop",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
    "opencv": "OpenCV", "streamlit": "Streamlit", "git": "Git",
}


def display(term):
    return DISPLAY.get(term, term)


# ---------------------------------------------------------------- 读文件
def read_resume(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("读 PDF 需要 pypdf：pip install pypdf（或把简历另存为 .txt）")
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if ext in (".txt", ".md"):
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                with open(path, encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        sys.exit(f"读不了 {path} 的编码，另存为 UTF-8 再试")
    sys.exit(f"不支持的格式 {ext}，支持 .pdf / .docx / .txt / .md")


# ---------------------------------------------------------------- 抽技能
def count_term(text, term):
    """统计技术词出现次数。英文按词边界，避免 rag 命中 storage。"""
    if re.fullmatch(r"[a-z0-9+#./]+", term):
        pat = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        return len(re.findall(pat, text))
    return text.count(term)


def extract_skills(text):
    low = text.lower()
    vocab = set(EXTRA_VOCAB)
    for kws in CATEGORIES.values():
        vocab.update(kws)
    found = {}
    for term in vocab:
        n = count_term(low, term)
        if n:
            found[term] = 3 if n >= 3 else (2 if n >= 2 else 1)
    return dict(sorted(found.items(), key=lambda kv: (-kv[1], kv[0])))


def extract_highlights(text, limit=8):
    lines = []
    for raw in text.splitlines():
        s = raw.strip(" \t·•-—*|")
        if not (12 <= len(s) <= 90):
            continue
        if any(h in s for h in PROJECT_HINTS):
            lines.append(s)
    # 去重且保持顺序
    seen, out = set(), []
    for s in lines:
        k = s[:24]
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out[:limit]


def draft_messages(text, max_len):
    """按类别生成话术草稿：只把简历里真实出现的类别关键词拼进去。

    草稿也走口语化 + 具体动作的写法，不要「可聊」这种收尾。
    """
    low = text.lower()
    drafts = {}
    for cat, kws in CATEGORIES.items():
        present = [k for k in kws if count_term(low, k)]
        if present:
            pick = "、".join(display(k) for k in present[:2])
            msg = f"我之前做过{pick}相关的项目，从需求到上线都是自己跟的。您这边主要做哪块？"
        else:
            msg = "我做过这个方向的项目，能直接上手。您这边主要做哪块？"
        if len(msg) > max_len:
            msg = msg[:max_len - 1] + "…"
        drafts[cat] = msg
    drafts["default"] = "我这一年主要做AI应用落地，Python后端也能写。合适的话我把简历发您。"
    return drafts


# ---------------------------------------------------------------- 写配置
def render_yaml(skills, messages, city, name, resume_path, highlights):
    L = []
    L.append("# ============================================================")
    L.append("#  由 scripts/onboard.py 自动生成 —— 请人工过一遍再跑")
    L.append(f"#  来源简历：{os.path.basename(resume_path)}")
    L.append(f"#  生成时间：{time.strftime('%Y-%m-%d %H:%M')}")
    L.append("# ============================================================")
    L.append("")
    L.append("# ⚠ 重点检查两处：")
    L.append("#   1) skills —— 删掉你不会的。写进去了，脚本就会替你投干不了的岗")
    L.append("#   2) messages —— 现在是按简历关键词拼的草稿，改成你自己做过的项目")
    L.append("")
    L.append("candidate:")
    L.append(f'  name: "{name}"')
    L.append(f"  city: {city}")
    L.append("  note: 随时到岗")
    L.append("")
    L.append("# 从简历里识别出的技术词；权重 3=核心 2=熟练 1=了解")
    L.append("skills:")
    for k, v in skills.items():
        L.append(f"  {k}: {v}")
    L.append("")
    L.append("# 岗位类别 → 关键词（决定用哪条话术，一般不用改）")
    L.append("categories:")
    for cat, kws in CATEGORIES.items():
        L.append(f"  {cat}:")
        for k in kws:
            L.append(f"    - {k}")
    L.append("")
    L.append("# 一次性开场话术（≤80 字，固定文本，不按岗位生成）")
    L.append("# 下面是草稿：把「做过XX相关项目」换成你真做过的那个项目，")
    L.append("# 口语一点、像自己说话；结尾别写「可聊」，要么反问一句要么说把简历发过去")
    L.append("messages:")
    for cat, msg in messages.items():
        L.append(f'  {cat}: "{msg}"')
    L.append("")
    L.append("# 不投的岗位")
    L.append("block_titles:")
    for t in BLOCK_TITLES:
        L.append(f"  - {t}")
    L.append("")
    L.append("block_body:")
    for t in BLOCK_BODY:
        L.append(f"  - {t}")
    L.append("")
    L.append("dev_titles:")
    for t in DEV_TITLES:
        L.append(f"  - {t}")
    L.append("")
    L.append("fit:")
    L.append("  min_score: 3")
    L.append("  short_jd: 200")
    L.append("  max_message_len: 80")
    L.append("")
    L.append("limits:")
    L.append("  daily: 150")
    L.append("  reserve: 2")
    L.append("")
    L.append("# 节奏：默认全速（gap=0）。担心频率就改成 7 / 15")
    L.append("pacing:")
    L.append("  gap: 0")
    L.append("  gap_max: 0")
    L.append("")
    if highlights:
        L.append("# ------------------------------------------------------------")
        L.append("# 简历里可以当话术素材的句子（写话术时参考，脚本不读这段）")
        for h in highlights:
            L.append(f"#   · {h}")
        L.append("# ------------------------------------------------------------")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="读简历生成 config/profile.yaml")
    ap.add_argument("--resume", help="简历路径：.pdf / .docx / .txt / .md")
    ap.add_argument("--city", default="北京", help="目标城市，默认 北京")
    ap.add_argument("--name", default="", help="姓名，可留空")
    ap.add_argument("--out", default=P.USER_PROFILE, help="输出路径")
    ap.add_argument("--check", action="store_true", help="只校验现有配置，不生成")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 profile.yaml")
    a = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    if a.check:
        probs = P.validate(P.load(reload=True))
        print(f"配置：{P.info()}")
        if probs:
            print("\n有问题：")
            for p in probs:
                print("  -", p)
            sys.exit(1)
        print("校验通过，可以跑 run.bat 了")
        return

    if not a.resume:
        sys.exit("用法：python scripts/onboard.py --resume 你的简历.pdf --city 北京")
    if os.path.exists(a.out) and not a.force:
        sys.exit(f"{a.out} 已存在，加 --force 才会覆盖（先备份你的话术！）")

    text = read_resume(a.resume)
    if len(text.strip()) < 50:
        sys.exit("简历里几乎没读到文字，可能是扫描件/图片版；请另存为 txt 再试")

    skills = extract_skills(text)
    highlights = extract_highlights(text)
    messages = draft_messages(text, 40)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render_yaml(skills, messages, a.city, a.name, a.resume, highlights))

    print(f"简历读取：{len(text)} 字")
    print(f"识别技能：{len(skills)} 个 → {list(skills)[:12]}{' ...' if len(skills) > 12 else ''}")
    print(f"项目素材：{len(highlights)} 句")
    print(f"已写入：{a.out}")
    print("\n话术草稿（**请改成你自己的项目**）：")
    for c, m in messages.items():
        print(f"  {c:<8} {len(m):>2}字  {m}")
    print("\n下一步：")
    print(f"  1. 打开 {a.out} 检查 skills / messages")
    print("  2. python scripts/onboard.py --check")
    print("  3. python scripts/doctor.py  然后 run.bat")


if __name__ == "__main__":
    main()

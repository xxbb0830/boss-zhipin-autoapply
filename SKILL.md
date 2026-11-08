---
name: boss-zhipin-autoapply
description: Automate BOSS直聘 (com.hpbr.bosszhipin) job applications on a USB-connected Android phone through ADB + uiautomator2. Reads the user's resume profile and past-application habits, opens each recommended/searched job, classifies it by the professional terms in its JD, sends one pre-written category message, and respects the daily 沟通 cap with a resumable ledger. Use when asked to auto-apply / 自动投递 / 批量沟通 on BOSS直聘, to analyze 投递习惯, or to send first-contact messages at scale.
metadata:
  version: "1"
---

# BOSS直聘 自动投递

End-to-end automation for applying to jobs on the BOSS直聘 Android app.

**Core principle (user instruction):** never regenerate wording per target.
Classify the job from the professional terms in its JD, then send the
**fixed pre-written message for that category** — every message is **≤80 字**,
口语化，no per-job wording, no job-title substitution.

**Targeting principle (user instruction, 2026-11-05):** 学历、经验、薪资**一律不筛**。
列表卡片只判断「还在招」；真正的判断在进详情页读完岗位职责之后 ——
JD 里出现我真正会的技术（`fit.py` 的白名单）就投，没有就跳过。

---

## 1. Prerequisites

| Item | 默认值 / 说明 |
| --- | --- |
| ADB | `tools/platform-tools/adb.exe` → PATH 里的 `adb` → `BOSS_ADB` |
| Python libs | `pip install -r requirements.txt`（uiautomator2 / adbutils / lxml / PyYAML / pypdf） |
| Runtime data | 默认 `<项目>/data`，可被 `BOSS_DATA` 或 `profile.paths.data` 覆盖 |
| Phone | 标定机型 Xiaomi 22011211C / Android 14 / **1440×3200**；`common.tap/swipe` 会按实际分辨率等比缩放 |

路径解析三级回退：**环境变量 → `config/profile.yaml` 的 `paths` → 自动探测**。
换机器只需要改 profile，不用碰代码。

Install once (国内网络加清华源):

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

Phone setup: enable 开发者选项 → USB调试, connect the cable, choose
**传输文件/MTP**, accept 允许USB调试 (一律允许).
Xiaomi also needs **USB调试(安全设置)** on.

## 2. Quick start

**第 0 步：用你自己的简历生成配置**（只需一次）

```bash
python scripts/onboard.py --resume 我的简历.pdf --city 北京
# 改 config/profile.yaml 里的 skills（删掉不会的）和 messages（换成自己做过的事）
python scripts/onboard.py --check
```

**一键全自动（推荐）** — 双击 `run.bat`，或：

```bash
./run.bat                     # Windows
```

它会自己完成：等设备 → 体检 → 投递 → 写 Markdown 报告。
**启动不预查额度**（翻求职记录要 1 分钟，没必要），直接开投，
投到 App 拦住为止。全程日志进 `data/auto_YYYYMMDD.log`，可以随时 Ctrl+C，
重跑会从台账断点继续、不会重复打扰同一家公司。

命令行等价：

```bash
cd scripts
PY=../.venv/Scripts/python.exe     # 或用 config/env.local.cmd 里的 BOSS_PY

$PY auto.py                 # 全自动：投递 + 报告
$PY auto.py --wait-device 3600   # 手机还没插就先挂着，插上自动开跑
$PY auto.py --limit 20      # 本次最多 20 个
$PY auto.py --dry           # 只打开详情、不发送（校准用）
$PY auto.py --report-only   # 只按台账重生成报告
$PY auto.py --quota         # 启动时先数一遍今日已沟通（慢，可选）
```

单独跑某一步（调试时用）：

```bash
$PY doctor.py               # 设备 / App / 环境体检
$PY quota.py                # 手动查今日已沟通数 + 剩余额度（可选）
$PY history.py              # 抓求职记录刷新习惯画像
$PY apply.py --limit 150    # 只跑投递循环
```

## 3. The flow

```
职位 tab (job list)
  └─ for each visible card not in ledger:
       tap card  ─────────────► BossJobPagerActivity (detail)
       read tv_job_name / tv_boss_title / tv_description / btn_chat
       if btn_chat text != 立即沟通  → already contacted, back, skip
       judge fit: JD 里有没有我真正会的技术（fit.py）
                    没有 / 岗位不对口 → back, skip（no_fit，不打扰对方）
       classify(tv_job_name + tv_description) → category
       tap btn_chat ─────────► 可能弹「今日还能沟通 N 次」
                                 → handle_popup() 点掉「好」，再点一次沟通
                                 → 若弹「已达上限」→ abort=daily_limit
                               ChatRoomActivity
                                 app auto-sends the default greeting
                                 (= the 投递 itself, consumes 1 沟通 quota)
       type pre-written category message (≤80 字)
       tap the send control right of the EditText
       verify the message appears as tv_content_text
       back ×3（收键盘 → 退聊天 → 退详情）
       append ledger line
```

Pacing: 默认全速（`pacing.gap: 0`），每投一个 6–10 秒；想放慢改配置。
The ledger makes the run resumable — re-running continues where it stopped
and never double-messages a company.

## 4. Targeting & classification

**没有任何硬性筛选条件。** 用户 2026-11-05 明确：「不管任何学历、经验、薪资，
只要招聘的岗位对上了，你就进去看岗位职责，你判断我能够胜任、有我懂的技术，你就投。」

所以分两段判断：

**① 列表卡片（`targeting.card_ok`）** —— 只看一件事：还在招吗。
带 `停止招聘 / 职位已关闭 / 已下线` 才跳过。学历、经验年限、薪资区间
（6-8K、50-80K、面议）**全部放行**。

**② 详情页（`fit.judge`）** —— 读完 `tv_description` 再判断能不能胜任：

| 判断 | 结果 |
| --- | --- |
| 岗位名含销售/客服/运营/人事/财务/教师/产品经理… | ❌ `blocked:<词>` |
| 岗位名是技术岗，但 JD 里没有任何我会的技术词 | ❌ `no_tech_match`（技术栈不对，如嵌入式/C++） |
| 岗位名看不出是什么岗（「线上面试（离职优先）」「急招/双休」这类钩子标题），JD 技术权重 ≥3 | ✅ `ok` |
| 同上，但 JD 里有 门店/提成/销售指标/地推/电销… | ❌ `blocked_body:<词>`（其实是销售/门店岗） |
| 同上，JD 短于 200 字、根本没信息可判断 | ✅ `ok_short_jd`（**信息不足不判死**，按广撒口径放行） |
| JD 命中我会的技术词 | ✅ `ok` |

**关键原则：信息不足 ≠ 不投。** BOSS 上大量真实岗位用「线上面试（离职优先）」
「急招！双休」当标题，JD 只有一两句，按技术词匹配必然全灭。
这类一律放行，只在 JD 明确写了门店/提成/销售指标时才拦。

`config/profile.yaml` 的 `skills` 是**你真正会的技术**清单（带权重）：
LangChain / LangGraph / RAG / FAISS / ReAct / MCP / Python / FastAPI /
asyncio / Docker / MySQL / Hive / pandas / 爬虫 ……
**只写你真会的** —— 写进去，脚本就会替你投你干不了的岗位。
（这份清单由 `onboard.py` 读简历生成，再人工删减。）

调口径不用改代码，改配置就行：`skills` / `block_titles` / `block_body` /
`dev_titles` / `fit.min_score` / `fit.short_jd`。

`messages.classify(title, jd)` scores keywords against title + JD text
(title hits weigh 3×). Categories, in priority of specificity:

| cat | triggered by (examples) | 固定话术（≤80 字，示例） |
| --- | --- | --- |
| `rag` | RAG / 检索增强 / 知识库 / 向量 / FAISS / BM25 / 召回 / 问答 | `我之前做过RAG问答，从文档切片、向量检索到答不准就拒答，这几块都是我写的。您这岗位也是这个方向吗？` |
| `agent` | Agent / 智能体 / 工作流 / 编排 / 工具调用 / ReAct / Harness / Coze / Dify | `我做过Agent项目，工具调用、参数校验和防编造都是自己加的，线上跑过。您这边主要落在哪块业务？` |
| `llm` | 大模型 / LLM / 算法 / NLP / 微调 / LoRA / Transformer / 推理 | `我做过两个大模型落地的项目，原理和工程两边都碰过。您这岗位更偏哪一边？` |
| `eng` | 后端 / 服务端 / Python / FastAPI / 全栈 / 并发 / Docker / Java | `我主要写Python后端，异步并发和Docker部署都是自己弄的。您这边后端用什么栈？` |
| `data` | 数据开发 / 数仓 / ETL / Hive / 爬虫 / SQL | `我做过数据清洗到入库的全链路，ETL和数仓调优都做过。您这边数据这块现在缺哪一环？` |
| `default` | none matched | `我这一年主要做大模型应用落地，Python后端也能写。合适的话我把简历发您。` |

**话术是硬约束：≤ `fit.max_message_len` 字（默认 80），固定文本，
不替换岗位名、不自我介绍、不放简历请求。**
结尾**不要写「可聊」**（用户口径：太轻浮）—— 技术岗反问一句，通用岗说「把简历发您」。
真正在用的文案在 `config/profile.yaml` 的 `messages` 段；
`onboard.py --check` 会校验长度。**Do not** add per-job generation.

## 5. Pacing（节奏）

用户口径（2026-11-08）：**不要模拟人手，全速投**。他自己手动投也是几秒一个，
慢的只是「没有话术」，不是操作速度。所以所有固定 sleep 都拆掉了，
换成「轮询到界面就绪立刻往下走」。

| 环节 | 以前 | 现在 |
| --- | --- | --- |
| 两个岗位之间 | 固定随机 7–15 秒 | **0 秒**（`pacing.gap`） |
| 点开岗位卡片 | 固定等 2.6 秒 | 轮询到 `tv_job_name`+`btn_chat` 都在 |
| 点「立即沟通」 | 固定等 3 秒 | 轮询到 ChatRoom（正常 0.3 秒） |
| 输入话术 | 输完固定等 1.3 秒 | 轮询到输入框里真的有字 |
| 点发送 | 点完轮询 3×0.9 秒 | 轮询到气泡上屏 |
| 退出聊天页 | 逐页返回，每页等 1.2 秒 | `input keyevent 4 4 4` 一次 adb 调用 0.25 秒 |

实测：每投一个 **6–10 秒**（原来 20 秒左右），150 个额度约 20–25 分钟跑完。

几个实现要点，改代码时别踩回去：

- `common.cur_app()` 一次 adb 调用同时拿 package + activity，并缓存
  `pacing.act_ttl`（默认 0.2 秒）。原来 `cur_pkg()` 和 `cur_act()` 各查一次，
  一次 0.4 秒，一轮下来 35 次调用白花 13 秒。
- `common.press_multi(["4","4","4"])` 连按三次返回：**发完消息输入法还开着**，
  第一次返回只收键盘，第二次退聊天，第三次退详情 —— 少按一次就会卡在详情页。
- `open_card` 必须等到 `tv_job_name` + `btn_chat` 都渲染出来再点，
  只看 Activity 名会在转场动画中途返回，那一下点击会被吞掉（白等 5 秒）。
- 想恢复「像人一样慢慢投」：`pacing.gap: 7` / `gap_max: 15` 即可，代码不用改。

## 6. Quota policy

用户口径（2026-11-08）：**不要预查额度**，进来直接投，投到 150 次 App 自己就不让投了。
`quota.py` 只作为手动工具保留（`python quota.py`），`auto.py` 默认不调用。

1. `auto.py --limit` 默认 150，跑到上限或列表翻到底为止。
2. **弹窗处理（关键）**：沟通到 120 次左右，点「立即沟通」会弹
   「今日还能沟通 N 次」。`apply.handle_popup()` 找到弹窗上的确认按钮
   （`好`/`知道了`/`确定`…）**点掉它**，然后重新点沟通进聊天页。
   以前这里是按返回键，结果弹窗关了又点、点了又弹，死循环，得人工点一下。
3. 只有文案里出现 `已达上限 / 明天再 / 已用完` 才算真没额度
   （`common.HARD_LIMIT_TEXTS`），立刻 `abort=daily_limit` 停下。
   **不要**用「上限」「已达」这种泛词判断 —— 「已达 120 次，还能沟通 30 次」
   里也有，会误判成额度用尽。
4. 台账（`applied.jsonl`）记录每次尝试，重跑不会重复联系同一家公司。
5. 连续 4 次失败也停（防止界面坏掉时盲目烧额度）。

## 7. Guardrails (learned the hard way)

- **App guard.** A mis-tap can launch a third-party app (an Alipay ad was
  observed). `common.ensure_boss()` / `ensure_job_list()` re-focus
  `com.hpbr.bosszhipin` and walk back to the list before every job. Never
  trust `app_current()` blindly mid-flow.
- **u2 server dies on swipe storms.** The `app_process` server behind
  uiautomator2 drops when swiped rapidly. `common.robust()` retries and
  reconnects; swipes use `dur ≥ 0.35` with a sleep after.
- **Send button has no resource-id, and the emoji button sits closer to the
  input box.** The row is `[voice] [EditText] [emoji] [send]`. Taking the
  *leftmost* clickable node right of the EditText taps **emoji** — that was
  the real cause of "输入了内容但没发送就退出了": the panel opened, nothing
  was sent, and the flow backed out leaving a draft. `common.find_send_button`
  now takes the **rightmost** control of the row.
- **Send is verified, not assumed.** `apply.send_message` clears any leftover
  draft, types, re-checks the EditText actually holds the text, taps, then
  looks for the bubble in `tv_content_text`. On failure it closes the
  emoji/attachment panel and retries up to 3×, and always clears the draft
  before giving up so no half-typed message is left behind.
- **Card open and 沟通 button are retried.** `open_fail` retries the card tap
  once; if `btn_chat` is absent (some 校招/实习 posts use 投递简历), the engine
  falls back to text matches: 立即沟通 / 投递简历 / 申请职位 / 我要投递 / 沟通.
- **学历/经验/薪资不做过滤**（用户口径：只要岗位对上了就投，能不能干进详情页再判断）。
  `targeting.card_ok` 只看「是否还在招」，`fit.judge` 只看「JD 里有没有我懂的技术」。
- **投递前必须过 fit 判断。** 没有 `no_fit` 判断的版本会给完全不对口的岗位发消息，
  白烧沟通额度还可能被举报；`no_fit` 只写台账、不进聊天页。
- **Typing is via accessibility `set_text`**, so Chinese works without the
  IME; the Sogou keyboard may still open and shift the layout — read bounds
  *after* typing.
- **`发简历` on the chat toolbar is a no-op** (observed on this account).
  The 附件简历 already exists on the profile, so recruiters can see it;
  the first-contact message therefore offers to send the resume instead of
  pushing a card.
- **Search box in the header is not openable by tap.** Work from the list
  the app is already showing (a `Python`/`北京` search or the 职位 feed).
  To change keywords, tap a suggestion chip or restart the app with a
  different last search.

## 8. Files

```
SKILL.md                本文件：给 AI agent 看的操作手册
README.md               给人看的：原理、快速开始、配置、免责
requirements.txt
run.bat                 双击启动（.venv → env.local.cmd 的 BOSS_PY → python）
config/
  profile.example.yaml  通用模板（入库）
  profile.yaml          你自己的技能/话术/路径（.gitignore）
  env.local.cmd         本机 Python/adb/数据路径覆盖（.gitignore）
scripts/profile.py      配置加载 + 校验（所有个人化内容的唯一入口）
scripts/onboard.py      读简历 → 生成 profile.yaml 草稿
scripts/common.py       resilient u2 driver, app guards, UI parsers, 坐标缩放
scripts/messages.py     类别归类 + 取用固定话术（读 profile）
scripts/targeting.py    列表卡片门槛（只看还在招）
scripts/fit.py          胜任度判断：JD 里有没有我真正会的技术（读 profile）
scripts/apply.py        main apply loop（台账去重、断点续跑、弹窗处理）
scripts/auto.py         one-shot runner: apply -> report（不预查额度）
scripts/quota.py        手动查今日已沟通（可选，auto.py 默认不调用）
scripts/history.py      scrape 求职记录 → infer habits
scripts/doctor.py       environment / device / app health check
references/ui-map.md    every selector and activity used
references/messages.md  话术设计说明（文案本体在 config）
```

## 9. Reporting

After a run, summarise from the ledger:

```bash
$PY - <<'PY'
import json, collections
rs=[json.loads(l) for l in open(r"D:\User\DSH-download\downloads\tmp\bossjob\applied.jsonl",encoding="utf-8")]
ok=[r for r in rs if r.get("status")=="ok"]
print("applied:", len(ok))
print("categories:", collections.Counter(r.get("cat") for r in ok))
print("companies:", len({r.get("company") for r in ok}))
PY
```

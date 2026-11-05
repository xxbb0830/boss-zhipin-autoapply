# BOSS直聘 UI 地图（实测）

设备：Xiaomi 22011211C，Android 14，**1440×3200**，density 560。
包名 `com.hpbr.bosszhipin`。所有 `id` 均省略前缀 `com.hpbr.bosszhipin:id/`。

## Activities

| Activity | 含义 |
| --- | --- |
| `.module.main.activity.MainActivity` | 主界面（4 个底部 tab） |
| `.geekjd.activity.BossJobPagerActivity` | 职位详情（社招） |
| `.geekjd.activity.BossJobActivity` | 职位详情（**校招/实习走这个**，布局不同） |
| `.chat.single.activity.ChatRoomActivity` | 聊天 |
| `.module.my.activity.GeekRecordListActivity` | 求职记录 |
| `.module.newonlineresume.OnlineResumeActivity` | 在线简历 |
| `.module.my.activity.geek.resume.AttachmentResumeActivity` | 附件简历 |

## 主界面

底部 tab（可点击 ViewGroup）：

| id | tab |
| --- | --- |
| `cl_tab_1` | 职位 |
| `cl_tab_2` | 发现 |
| `cl_tab_3` | 消息 |
| `cl_tab_4` | 我的 |

职位列表页结构：

```
appBarLayout [0,0][1440,416]
 └ collapsing_toolbar / main_toolbar [0,0][1440,258]
    └ magic_indicator [70,125][1079,237]   ← 搜索栏容器（点不开，见"坑"）
       └ scroll_view → TextView 当前关键词 chip（clickable）
    └ ly_menu [1114,111][1405,251]         ← 右上两个图标
 └ filter_bar [0,258][1440,416]            ← 推荐 / 附近 / 最新 / 城市 / 筛选
```

职位卡片（每屏约 5 张，整卡是一个 `LinearLayout`，可点击）：

| id | 内容 |
| --- | --- |
| `tv_position_name` | 职位名（可能带 ` &@` / ` @%` 角标，需清理） |
| `tv_salary_statue` | 薪资 |
| `tv_company_name` | 公司 |
| `tv_stage` / `tv_scale` | 融资阶段 / 规模 |
| `tv_employer` | 招聘者 `姓名 · 职位` |
| `tv_active_status` | 如 `今日回复10+次` |
| `tv_distance` | 如 `海淀区  中关村` |
| `iv_improper` | "不合适" 小图标 |

## 职位详情 BossJobPagerActivity

| id | 内容 |
| --- | --- |
| `tv_job_name` | 职位名 |
| `tv_job_salary` | 薪资 |
| `tv_required_location` | 地点 |
| `tv_required_work_exp` | 经验要求 |
| `tv_required_degree` | 学历要求 |
| `tv_boss_name` / `tv_boss_title` | 招聘者姓名 / `公司 • 职位` |
| `boss_label_tv` | 回复活跃度 |
| `tv_description` | **JD 正文（归类数据源）** |
| `btn_chat` | 按钮，文本 `立即沟通` = 未沟通；已沟通会变成 `继续沟通` |

## 聊天 ChatRoomActivity

| 节点 | 说明 |
| --- | --- |
| `tv_content_text` | 消息正文（发送成功后用它校验） |
| `mMsgTvStatus` | `送达` / `已读` |
| `tv_contact_time` | 如 `11月4日 15:33 由你发起的沟通` |
| `editText_with_scrollbar` | **输入框**（EditText，hint `介绍自己回复率更高哦~`） |
| `mMoreIcon` | 输入框右侧 "+"，点开是 `图片/语音/语音通话` |
| 顶部横条 | `换电话 / 换微信 / 发简历 / 不感兴趣`（**实测点不动**） |

**发送按钮没有 resource-id**。输入行布局是 `[语音] [EditText] [表情] [发送]`：

| 键盘状态 | 表情按钮 | 发送按钮 |
| --- | --- | --- |
| 展开 | `[1142,1726][1240,1824]` | `[1286,1726][1384,1824]` → 中心 `(1335, EditText 中线)` |
| 收起 | `[1142,3046][1240,3144]` | `[1286,3046][1384,3144]` → 中心 `(1335, ~3095)` |

⚠️ **必须取最右侧**。按"EditText 右侧第一个可点节点"取会拿到**表情按钮**，
点了只弹表情面板、消息根本没发出去——这就是"输入了内容但没发送就退出"的根因。
`common.find_send_button()` 现在按 right edge 排序取最后一个，并过滤掉宽度 ≥400 的容器。

## 我的

| id | 内容 |
| --- | --- |
| `tv_my_resume` | 在线简历入口 |
| `cl_geek_contacts_number` | 沟通过（数字是自绘，取不到文本） |
| `cl_geek_post_resume_number` | 已投简历 |
| `cl_pre_interview` | 待面试 |
| `cl_geek_favor_position` | 收藏 |
| 常用功能 | 在线简历 / 附件简历 / 求职意向 / 求职道具（`tv_title` + `tv_sub_title`） |

坐标：在线简历 ≈ `(200,1620)`，附件简历 ≈ `(530,1620)`。

## 求职记录 GeekRecordListActivity

顶部 tab：`我看过 / 沟通过 / 交换过 / 面试`；`累计沟通职位数量 N` 在 `tv_tip_text`。

| id | 内容 |
| --- | --- |
| `tv_time_line` | 日期分隔（`11月4日` / `昨天`） |
| `tv_position_name` | 职位名 |
| `tv_salary_statue` | 薪资（`停止招聘` 也在这） |
| `tv_company_name` | 公司 |
| `tv_employer` | 招聘者 |
| `tv_active_time` | 时间 `13:05` |

## 坑（都踩过）

1. **u2 服务会死**：连续快速 swipe 后 `RemoteDisconnected`。
   → `common.robust()` 重连 + swipe `dur ≥ 0.35` 并 sleep。
2. **误触拉起支付宝**：聊天页底部有 `mPayCoverView` 之类覆盖层，
   坐标点偏会跳到 `com.eg.android.AlipayGphone`。
   → 每步后校验 `cur_pkg()`，`ensure_boss()` 拉回。
3. **顶部搜索栏点不开**：`magic_indicator` 区域 tap 无反应，只显示当前关键词 chip。
   → 直接用 App 当前列表（上次搜索词）或 职位 tab 的推荐流；换词需手动改。
4. **`发简历` 横条无响应**：点了没反应、不报错。
   → 简历挂在账号上（附件简历已存在），话术里邀请对方索要。
5. **键盘是搜狗**：`set_text` 走无障碍注入，不依赖输入法；但键盘会顶起布局，
   必须在**输入之后**再读 bounds。
6. **职位名带角标**：`xxx &@`、`xxx @%`，入库前要 `re.sub(r"[\s@&%·•]+$","",s)`。

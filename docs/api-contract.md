# 懂球帝接口核验记录

## 当前状态：曼城动态接口已核对；名单、赛程和球员接口仍待验证

此文档把 2026-10-18 Postman 集合里的名单、赛程和球员 URL 保存为**待复核线索**。用户另行提供了一份球队名单响应正文；它已用于核对响应字段并生成脱敏样本，但没有包含原始 HTTP 方法、请求头、HTTP 状态码或认证上下文。曼城动态接口已由用户在 mitmweb 抓到，并在 Postman 对该请求及 `data.next` 下一页成功重放。

五个 Postman 请求都记录为 GET，但集合没有保存对应响应示例。集合里未配置 `Authorization` 或 `Cookie`，也不能据此断定接口不需要登录态、设备信息或其他认证上下文。响应正文中 `seasons[].url` 是服务端给出的赛季链接，不等于本次 APP 实际发送请求的记录。

| 用途 | Postman 中观察到的请求线索 | 配置/依赖 | 必须重新核验 |
|---|---|---|---|
| 球员资料 | `GET https://api.dongqiudi.com/data/v1/detail/person/50259656?app=dqd&lang=zh-cn` | `person_id=50259656` | 当前路径、参数、认证要求、完整响应结构 |
| 球员统计 | `GET https://sport-data.dongqiudi.com/soccer/biz/dqd/person/statistic_new/50259656?lang=zh-cn` | `person_id=50259656` | 当前路径、参数、认证要求、分页/赛季语义、响应字段 |
| 球员能力值 | `GET https://sport-data.dongqiudi.com/soccer/data/sofifa/v1/player_ability/259656?player_type=` | 观察到的 `ability_id=259656` 与 `person_id` 不同 | ID 来源、空参数含义、认证要求、响应字段 |
| 球队名单 | `GET https://sport-data.dongqiudi.com/soccer/biz/dqd/v1/team/member_v2/50000529?app=dqd` | Postman 旧线索；样例球队 ID 为曼城 `50000529`；项目配置读取 `dqd_id` | 原始请求方法/URL/参数、HTTP 状态和认证仍待核验；响应字段见下节 |
| 球队赛程 | 用户提供的链接：`https://sport-data.dongqiudi.com/soccer/biz/dqd/team/schedule/50000529?app=dqd&version=444&lang=zh-cn&season=2026-2027` | 样例球队 ID、版本、语言和赛季；响应内当前赛季链接与该赛季一致 | 本次请求的真实 method、HTTP 状态、请求头与认证依赖；查询参数是否必需 |

## 曼城动态接口：请求与分页已核验

用户在 mitmweb 观察到曼城球队动态页的请求，并在 Postman 成功调用首屏和响应中 `data.next` 给出的下一页。请求中没有在项目里保存 Cookie、Token、签名或设备标识。

| 项 | 已观察内容 | 当前实现 |
|---|---|---|
| HTTP 方法和状态 | `GET`，Postman 响应 `200`；JSON 业务 `code=0` | 只发 GET；HTTP/业务失败时终止日报生成 |
| 首屏 URL | `https://api.dongqiudi.com/v3/archive/app/channel/feeds?id=50000529&type=team&version=444&platform=android&isDarkMode=0&android-channel=website&isTeenager=0&device_glb_type=1` | 按 `dynamics.team_id` 构造相同查询参数 |
| 分页 | `data.next` 是下一页完整 URL，首屏示例包含 `page=2`、`after` 和 `offset` | 原样请求 `data.next`，校验 host、path、球队 ID 和 `type=team` |
| 动态列表 | `data.articles` 数组 | 按动态 ID 去重，仅在本次运行内存去重 |
| 时间字段 | `data.articles[].show_time` 是 Unix 秒级时间戳；`created_at` 是字符串字段 | 用 `show_time` 转成上海本地时间筛选；首屏 `data.next.after` 与当前页最后一条 `show_time` 相同 |
| 文章字段 | `id`、`title`、`description`、`created_at`、`show_time`、`share`；部分记录含 `talk.content` | 只抽取日报筛选和展示所需字段；原始响应不落盘 |
| 循环上限 | `data.next` 可以继续提供分页 URL | 重复 URL 立即报错；仅当 `after` 和当前整页 `show_time` 都早于 `--since` 时停止；每次运行最多请求 50 页 |

原始动态响应只保留在用户提供的 Postman/mitmweb 会话，不复制到仓库 fixture，也不写 SQLite。分页边界把 `data.next` 的 `after` 时间戳和当前页的 `show_time` 与所选 `--since` 一起核对；筛选和日报展示按每条动态的 `show_time` 处理。兴趣筛选是配置字符串的大小写不敏感子串匹配，任一兴趣命中即入选；详见 `config.toml` 的 `[dynamics]`。

对名单、赛程和球员接口而言，上述请求头、User-Agent、Referer 和查询参数都只是旧抓包里出现过的值；当前实现没有重放这些请求，不得把它们直接当作必须发送的请求头或稳定参数。曼城动态请求使用 mitmweb 观察到的查询参数，并在 Postman 成功重放；当前 Python 客户端不额外复制会话头或设备标识。

## 球队名单响应：样本已确认的字段

样本文件：[team-roster.response.sample.json](../fixtures/team-roster.response.sample.json)。它从用户提供的响应正文裁剪生成，球员分组保留 `person_id`、`person_name` 和成员 `type`；教练分组额外保留主教练的 ID 与姓名，其他教练和工作人员只保留识别分组所需字段。年龄、图片链接、薪资等非必要字段未写入仓库。

| JSON 路径 | 样本中观察到的结构 | 当前处理 |
|---|---|---|
| `code` | 整数 `0` | 作为样本里的业务成功标记；HTTP 状态码仍未知 |
| `message` | 字符串，样本为空字符串 | 校验类型，不假定所有成功响应都为空 |
| `data.list` | 6 个分组 | 每组有 `type` 和 `data` 数组 |
| `data.list[].type` | `coach`、`manager`、`attacker`、`midfielder`、`defender`、`goalkeeper` | 提取四种球员位置分组和教练分组中的主教练；跳过其他教练组人员和工作人员 |
| `data.list[].data[].person_id` | 数字字符串 | 转成正整数后交给 SQLite；样本中的 24 个球员 ID 均不重复 |
| `data.list[].data[].person_name` | 球员和主教练记录中的非空字符串 | 写入 `players.person_name`；每次名单同步都按新响应更新姓名 |
| `data.list[].title` | 球员分组标题：前锋、中场、后卫、门将 | 写入 `players.attr`；主教练记录的 `attr` 固定为“主教练” |
| `coach` 分组中的 `data[].type` | 人员岗位字符串，样本中主教练为“主教练” | 只导入唯一一条 `type=主教练` 的记录作为球队名单的一行 |
| `seasons` | 赛季选项数组，包含 `url` | 作为响应数据保存；不能据此确认本次实际请求的 URL 或参数 |

样本共有 40 条成员记录：前锋 6、中场 6、后卫 9、门将 3，共 24 名球员；`coach` 分组包含 12 人，其中只导入唯一的主教练 1 人；`manager` 分组的 4 名工作人员不导入。清洗和解析器在 [team_roster.py](../src/dqd_scroll/lib/team_roster.py)，离线导入流程在 [workflow.py](../src/dqd_scroll/workflow.py)。因此样本会写入 25 条名单关联。每次得到新响应都会在同一数据库事务中更新 `players.person_name`、`players.attr`，并替换 `team_players` 中对应球队的人员关联；转会球员从旧队名单移除后，人员主表仍保留其记录。当前流程读取本地响应文件，真实网络请求尚未实现。这只是一个响应样本，不能证明所有球队、赛季和 APP 版本都返回相同字段。

样本的 `seasons[].url` 中可见当前赛季链接带有 `lang=zh-cn`、`season=0`、`current=1`，历史赛季链接使用不同的 `season` 值；旧 Postman 线索则出现 `app=dqd`。这些都是观察到的候选参数，只有抓到 APP 本次实际发出的原始请求后，才能确认哪些参数实际发送、哪些必需。

## 球队赛程响应：样本已确认的字段

样本文件：[team-schedule.response.sample.json](../fixtures/team-schedule.response.sample.json)。它由用户提供的赛程响应整理而来，完整保留 `season_list`、`data` 和顶层 `list` 字段，用于离线解析与导入。

| JSON 路径 | 样本中观察到的结构 | 当前处理 |
|---|---|---|
| `season_list` | 127 个赛季选项，按 `sort` 从 1 排到 127 | 选取唯一 `current=true` 项，并要求其 `sort` 是列表最大值 |
| `season_list[].name` | 当前项为 `2026/2027` | 写入 `league_seasons.season` |
| `season_list[].url` | 当前项指向球队赛程路径，含 `season=2026-2027` | 校验路径球队 ID 和赛季参数与当前项一致；不将其当成 HTTP 认证证据 |
| `data` | 52 场比赛记录 | 每条比赛必须包含目标球队；按 `match_id` 去重 |
| `data[].match_id` | 数字字符串；样本中的 52 个编号互不重复 | 转为整数写入 `team_schedules.match_id`；相同 ID 内容冲突时拒绝导入 |
| `competition_id`、`team_A_id`、`team_B_id` | 数字字符串 | 转为整数；球队 A/B 的接口字段映射到 `team_a_id`、`team_b_id` |
| 比赛名称、队名、状态、标题和链接字段 | 字符串 | 保留原值，字段统一转为下划线命名 |
| `fs_A`、`fs_B`、`ps_A`、`ps_B` 等比分/时间字段 | 字符串；未开赛数据可为空字符串 | 按接口原样保存，不用默认值填充 |
| 顶层 `list` | `null` | 当前赛程解析不使用此字段 |

样本中只有 `2026/2027` 标记为当前赛季，其 `sort=127` 为最大值；所有 52 场记录都包含曼城 `50000529`，比赛日期从 `2026-08-01` 到 `2027-05-30`。数据库通过 `league_seasons(league_serial, season)` 维护联赛与当前赛季关系，并为每个 `league_serial` 保留一条当前记录；`team_schedules` 保存该球队当前赛季的比赛。导入更高 `season_sort` 时，旧赛季赛程在同一事务中删除，避免不同赛季混存。当前表也保存所有比赛的原始 A/B 字段；报告加工时只标识目标球队是 A 侧还是 B 侧，并据此映射对手和比分，不把 A/B 擅自解释为主队/客队。

解析与加工代码位于 [team_schedule.py](../src/dqd_scroll/lib/team_schedule.py)，SQLite 写入和读取位于 [repository.py](../src/dqd_scroll/repository.py)，离线命令为 `schedule-import` 和 `schedule-report`。`schedule-import` 要求显式提供本次响应对应的 `--request-url`，并核验其球队 ID 与赛季参数匹配响应标记的最新赛季。这份响应样本不包含 HTTP 状态、请求头或认证上下文；在线赛程请求仍须完成相应请求契约核验。

目前仍缺：本次 APP 操作对应的原始 HTTP 请求方法和 URL、实际发送的参数与请求头、HTTP 状态码、认证字段是否必需，以及分页/赛季参数的语义。以上项目必须从授权设备的真实请求记录中核验。

## 后续接口实现顺序

曼城动态只读请求和日报已经实现。下一步仍可优先核验**球队名单**：`db-init` 从项目根目录 `teams.json` 读取球队映射并写入 SQLite；名单导入、赛程导入和赛程报告命令通过 `--database` 从 `teams` 表读取球队资料，不再从 JSON 重复读取。响应解析和本地 SQLite 导入已有样例实现。名单、赛程和球员接口仍须分别确认真实路径、参数、必要请求头和认证依赖后再实现在线请求。球员 ID 不手工维护在配置文件里。

## 核验后填写的契约

每个接口通过核验后，再补齐下列内容，并链接到脱敏请求/响应证据：

| 项 | 证据要求 |
|---|---|
| 采集范围 | APP 版本、设备系统版本、采集日期、用户授权范围 |
| 请求方法与 URL | 从本次 APP 正常操作抓到的完整 method、host、path |
| 参数 | 区分路径参数、必需查询参数、可选参数和空值语义 |
| 请求头 | 只记录重放所需且已验证的头；秘密值不进入仓库 |
| 鉴权方式 | 明确请求是否依赖登录态、Cookie、Token 或设备上下文；“抓包没出现”不等于“不需要” |
| 响应结构 | 保存脱敏 JSON 样本，确认根节点类型和必需字段路径 |
| 球员 ID | 确认名单项中 person ID 的字段、类型、唯一性及缺失时的处理 |
| 失败情形 | 记录 HTTP 状态、业务错误字段、限流/认证失败行为 |
| 复核结果 | 标注通过人、证据位置和是否允许独立只读重放 |

## 开始实现其余在线请求前的闸门

- [ ] 用户已确认名单、赛程和球员接口的调用范围符合授权及平台规则。
- [ ] 在授权设备上重新执行了“打开目标球队名单”的正常 APP 操作。
- [x] 已收到并保存裁剪后的球队名单响应正文样本；保留球员姓名和 ID 用于名单刷新示例，未保存年龄、图片、薪资或账号凭证。
- [x] 已收到球队赛程 URL 与响应正文样本，并确认当前赛季及比赛字段；离线赛程导入和 SQLite 写入已实现。
- [ ] 已从本次 APP 抓包确认请求方法、真实 URL、参数、必要请求头和认证依赖。
- [x] 已在提供的响应样本中确认球员分组、`person_id`、`person_name`、位置标题，以及主教练的 `type` 标记。
- [ ] 用户明确允许实现并发送对应的名单或赛程只读请求。

名单和赛程请求闸门全部确认后，再实现对应 API 方法。名单请求成功后调用 `save_team_roster_response()` 原子刷新人员与球队关联；赛程请求成功后调用 `save_team_schedule_response()` 解析当前赛季并原子替换最新赛程。当前 `roster-import` 和 `schedule-import` 仍只从本地响应文件导入，不会访问网络。动态日报由本项目的 Python CLI 和 DSH 每日调度运行，不实现 MCP 服务。

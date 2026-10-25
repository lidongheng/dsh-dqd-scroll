# 懂球帝接口核验记录

## 当前状态：动态、名单及球员联赛统计已接入；赛程在线请求仍待验证

此文档把 2026-10-18 Postman 集合里的名单、赛程和球员 URL 保存为**待复核线索**。用户另行提供了一份球队名单响应正文；它已用于核对响应字段并生成脱敏样本，但没有包含原始 HTTP 方法、请求头、HTTP 状态码或认证上下文。曼城动态接口已由用户在 mitmweb 抓到，并在 Postman 对该请求及 `data.next` 下一页成功重放。

五个 Postman 请求都记录为 GET，但集合没有保存对应响应示例。集合里未配置 `Authorization` 或 `Cookie`，也不能据此断定接口不需要登录态、设备信息或其他认证上下文。响应正文中 `seasons[].url` 是服务端给出的赛季链接，不等于本次 APP 实际发送请求的记录。

| 用途 | Postman 中观察到的请求线索 | 配置/依赖 | 核验状态与待核验内容 |
|---|---|---|---|
| 球员资料 | `GET https://api.dongqiudi.com/data/v1/detail/person/50259656?app=dqd&lang=zh-cn` | `person_id=50259656` | 当前路径、参数、认证要求、完整响应结构 |
| 球员统计 | `GET https://sport-data.dongqiudi.com/soccer/biz/dqd/person/statistic_new/50259656?lang=zh-cn` | `person_id=50259656` | 2026-10-26 已用 Python 只读 GET 实测 HTTP 200；当前实现筛选及字段见下文 |
| 球员能力值 | `GET https://sport-data.dongqiudi.com/soccer/data/sofifa/v1/player_ability/50259656?player_type=` | 本次用户提供 person_id 路径；历史线索 259656 未作为当前实现依据 | 2026-10-26 Python GET 实测 HTTP 200，曼城 24 人能力数据成功入库 |
| 球队名单 | `GET https://sport-data.dongqiudi.com/soccer/biz/dqd/v1/team/member_v2/50000529?app=dqd` | Postman 旧线索；样例球队 ID 为曼城 `50000529`；项目配置读取 `dqd_id` | 2026-10-26 已由 roster-sync 实际请求；不额外携带抓包会话头；响应字段见下节 |
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

对名单、赛程和球员接口而言，上述请求头、User-Agent、Referer 和查询参数都只是旧抓包里出现过的值；旧线索不能证明这些请求头必需；2026-10-26 的名单和球员统计 Python GET 未额外携带抓包会话或设备头，实际调用成功。曼城动态请求使用 mitmweb 观察到的查询参数，并在 Postman 成功重放；当前 Python 客户端不额外复制会话头或设备标识。

## 球队名单响应：样本已确认的字段

样本文件：[team-roster.response.sample.json](../fixtures/team-roster.response.sample.json)。它从用户提供的响应正文裁剪生成，球员分组保留 `person_id`、`person_name`、`shirtnumber`、`person_en_name`、`age`、`statistic` 中的“身价(欧)”和成员 `type`；教练分组额外保留主教练的 ID、姓名与年龄，其他教练和工作人员只保留识别分组所需字段。图片链接、薪资等非必要字段未写入仓库。

| JSON 路径 | 样本中观察到的结构 | 当前处理 |
|---|---|---|
| `code` | 整数 `0` | 业务成功标记；2026-10-26 在线名单请求返回 HTTP 200 |
| `message` | 字符串，样本为空字符串 | 校验类型，不假定所有成功响应都为空 |
| `data.list` | 6 个分组 | 每组有 `type` 和 `data` 数组 |
| `data.list[].type` | `coach`、`manager`、`attacker`、`midfielder`、`defender`、`goalkeeper` | 提取四种球员位置分组和教练分组中的主教练；跳过其他教练组人员和工作人员 |
| `data.list[].data[].person_id` | 数字字符串 | 转成正整数后交给 SQLite；样本中的 24 个球员 ID 均不重复 |
| `data.list[].data[].person_name` | 球员和主教练记录中的非空字符串 | 写入 `players.person_name`；每次名单同步都按新响应更新姓名 |
| 球员 `shirtnumber` | 字符串 | 写入 `players.shirt_number`；球员记录必须提供该字段 |
| 球员 `person_en_name` | 字符串 | 写入 `players.person_en_name`；球员记录必须提供该字段 |
| `age` | 非空字符串 | 原样写入 `players.age`，保留“岁”单位 |
| 球员 `statistic[].身价(欧)` | 字符串，必须唯一 | 原样写入 `players.social_status`，保留“万”“亿”单位；按键定位，不依赖数组顺序 |
| 主教练身价 | 响应中未提供 | `players.social_status` 保存为 SQL `NULL` |
| `data.list[].title` | 球员分组标题：前锋、中场、后卫、门将 | 写入 `players.attr`；主教练记录的 `attr` 固定为“主教练” |
| `coach` 分组中的 `data[].type` | 人员岗位字符串，样本中主教练为“主教练” | 只导入唯一一条 `type=主教练` 的记录作为球队名单的一行 |
| 主教练记录中的 `shirtnumber`、`person_en_name` | 用户提供的响应中均未出现 | `players.shirt_number` 和 `players.person_en_name` 保存为 SQL `NULL` |
| `seasons` | 赛季选项数组，包含 `url` | 作为响应数据保存；不能据此确认本次实际请求的 URL 或参数 |

样本共有 40 条成员记录：前锋 6、中场 6、后卫 9、门将 3，共 24 名球员；`coach` 分组包含 12 人，其中只导入唯一的主教练 1 人；`manager` 分组的 4 名工作人员不导入。清洗和解析器在 [team_roster.py](../src/dqd_scroll/lib/team_roster.py)，离线导入流程在 [workflow.py](../src/dqd_scroll/workflow.py)。因此样本会写入 25 条名单关联。每次得到新响应都会在同一数据库事务中更新 `players.person_name`、`players.attr`、`players.shirt_number`、`players.person_en_name`、`players.age`、`players.social_status`，并替换 `team_players` 中对应球队的人员关联；转会球员从旧队名单移除后，人员主表仍保留其记录。`roster-import` 读取本地响应文件；`roster-sync` 在线请求名单后逐个抓取本赛季球员联赛统计。这只是一个响应样本，不能证明所有球队、赛季和 APP 版本都返回相同字段。

样本的 `seasons[].url` 中可见当前赛季链接带有 `lang=zh-cn`、`season=0`、`current=1`，历史赛季链接使用不同的 `season` 值；旧 Postman 线索则出现 `app=dqd`。这些都是观察到的候选参数，只有抓到 APP 本次实际发出的原始请求后，才能确认哪些参数实际发送、哪些必需。

## 球员本赛季联赛统计：2026-10-26 实测

用户指定 `GET https://sport-data.dongqiudi.com/soccer/biz/dqd/person/statistic_new/{person_id}?lang=zh-cn`。Python 客户端实际调用成功，曼城整批同步共请求 24 次球员统计接口；没有请求主教练，实测最短请求起始间隔为 1.265 秒。当前连接的 Postman 工作区未返回收藏集合，此处实测证据来自 Python 真实请求和 SQLite 入库核对。

| 项 | 响应路径或处理 |
|---|---|
| 当前赛季 | 从 SQLite `teams.league_serial` 关联 `league_seasons.season` 读取，曼城当前为 `2026/2027` |
| 联赛筛选 | 只用根节点 `league` 数组，同时匹配 `season.name` 和 `competition.short_name = teams.match_league_name`；杯赛与总计不参与 |
| 出场数 `caps` | `base_info.appearances` |
| 首发数 `lineups` | `base_info.starts` |
| 进球数 `goals`、助攻数 `assists` | `base_info.goals`、`base_info.assists` |
| 门将扑救 `rescues` | `statistic.saves`；非门将为 SQL `NULL` |
| 多条联赛记录 | 同赛季、同联赛转会产生的不同记录累计；重复记录 ID 报错 |
| 缺失数据 | 未发布匹配赛季联赛记录时保存 `NULL`；存在记录但所需字段缺失、不是非负整数字符串时终止，不补零 |
| 入库范围 | 仅保存当前赛季统计到 `players`，以 `stats_season`、`stats_league_serial` 标记来源；全部球员成功解析后一次提交 |
| 节流与失败 | 同一球员统计后立即请求能力，完成后等 1 秒处理下一人；统计失败终止批次，能力失败仅记 INFO、写 NULL 并继续 |

命令：`python -m dqd_scroll roster-sync --database data/dqd_scroll.sqlite3 --team-id 50000529`。运行前需要 `db-init` 迁移新列，并已有所属联赛的 `league_seasons` 当前赛季记录；赛程导入切换赛季时会清除旧球员统计。

## 球员能力值与场上位置：2026-10-26 实测

当前请求直接使用名单中的 `person_id`，保留空查询参数 `player_type=`。能力响应根节点包含 `errno=0` 和 `data.fields`。解析参考用户指定的 `getAbilityPosition`：筛选 `lv` 后缀 `_f`，取最大 `val`；同分保留第一项，将对应 `name` 通过共享的 `src/dqd_scroll/shared/positionMap.json` 映射为位置代码。该文件含用户提供的 21 个位置映射，通过 `dqd_scroll.shared.load_position_map()` 供所有 Python 脚本共用，已验证随 wheel 打包并可直接读取。

哈兰德本次响应中选中的位置为“中锋”，`val=93`，入库为 `ability=93`、`position=ST`。本次曼城整批实际请求统计与能力接口各 24 次，统计完成到能力请求之间没有额外等待，能力完成到下一名球员请求的最短等待为 1 秒；24 人能力均已保存。

能力接口没有赛季参数或返回的赛季字段，当前能力快照关联 SQLite 当前 `league_seasons.season`；本次为 `2026/2027`，不声称从接口筛选了历史赛季能力。赛季切换时会连同统计清空旧能力和位置。

单名球员能力缺失、HTTP 失败、业务失败或解析无效时，仅记录一条 `INFO`，该球员 `ability`、`position` 都保存 SQL `NULL`，继续抓取下一人。已测试某人无能力时下一人仍正常抓取，也已测试全部能力请求失败时 24 名球员仍处理完成。

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

动态日报、在线球队名单、球员本赛季联赛统计及能力值已实现。`db-init` 从 `teams.json` 初始化球队映射并迁移 SQLite；`roster-sync` 从数据库读取球队和当前赛季，依次调用名单、球员统计和能力接口。在线赛程及其他球员资料接口仍需分别确认请求契约；现有 `schedule-import` 继续从本地响应文件导入赛程。

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

## 在线调用范围与待核验事项

用户已明确要求名单抓取后，逐个连续请求 `statistic_new` 和 `player_ability`，再间隔一秒处理下一名球员。该调用范围已由 `roster-sync` 实现；名单和本赛季联赛统计实际请求成功，响应解析与 SQLite 入库已经核对。当前客户端不额外保存或发送抓包中的 Cookie、Token、签名或设备标识。

球队赛程仍通过 `schedule-import` 读取本地响应，球员资料等其他在线接口尚未接入。实现这些接口前，继续核验各自真实方法、URL、参数、必要请求头与认证依赖。上述名单和统计成功不能替代其他接口的核验。

## 球员个人资料与独立联赛分析

个人资料 GET：`https://api.dongqiudi.com/data/v1/detail/person/{person_id}?app=dqd&lang=zh-cn`。使用 `api/config.py` 的 App 请求头及专题首页 Referer。`base_info.nationality` 为非空字符串；`height`、`weight` 为正整数或可转换为正整数的纯数字字符串，分别以厘米、公斤保存。缺少或无效字段直接报错；不使用名单国籍代替个人资料国籍，不补身高体重默认值。曼城实测哈兰德返回挪威、195、94。

名单、统计、能力值、个人资料分别负责基础资料、当前联赛累计、当前能力位置和身体/国籍资料。`roster-sync` 在每个球员的统计及能力值后紧接着请求个人资料，再间隔一秒处理下一名；详情批次校验当前赛季和名单后一起提交。个人资料不随赛季切换清空，名单导入也不会覆盖它。

`club-analyze` 的英超采集配置位于 `api/titan_config.py`：HTTPS 赛程 `zq.titan007.com/jsData/matchResult/{season}/s36.js`，HTTP 技术统计 `bf.titan007.com/detail/{match_id}cn.htm`，与原分析器地址一致。HTTPS 使用默认证书校验并限制 TLS 1.2，以兼容球探服务器。赛程与详情使用各自的请求头。只解析赋值数组中的 JSON5 数据，不执行远程 JavaScript；JS 稀疏数组中的缺位转换为 null 表示原始缺失，未读取的盘口缺位不会补成 0。

赛程 `arrLeague` 校验联赛和赛季；`jh['R_N']` 中状态为 -1、主客队含目标球探球队编号的比赛进入分析。比赛编号、主客侧、轮次来自球探，不与懂球帝比赛编号混用。详情读取实际阵型、首发、替补和事件图标，主客位置顺序与原脚本一致；替补仅在有登场事件时计算出场。固定主客场页面与原 JS 的事件、累计统计、阵型和推荐首发对照结果保存在 `fixtures/club-analysis/expected.json`。

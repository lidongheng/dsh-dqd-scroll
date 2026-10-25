# dqd-scroll

懂球帝只读阅读助手与 DSH 插件。球队动态日报会按用户配置的懂球帝球队名称解析球队 ID，逐队读取动态分页，并分别生成全部动态和兴趣命中动态两份 Markdown；动态仅在内存处理并写入日报，不进入 SQLite，也不会发送私信。球队名单和赛程仍按现有离线流程清洗、导入和加工。

## 开发进度与下一步

### 已完成

- [x] 创建 Conda 环境和 Python 包结构。
- [x] 提供 `status`、`db-init`、离线 `roster-import`、`schedule-import` 和 `schedule-report` CLI 命令。
- [x] 在 `config.toml` 中保存 20 支球队的懂球帝/球探映射，以及英超联赛信息。
- [x] 初始化 SQLite：`teams` 表已有 20 支球队映射；已导入曼城 24 名球员、1 名主教练，以及 `league_serial=36` 对应的 `2026/2027` 赛季和 52 场赛程；实时抓取仍未实现。
- [x] 根据用户提供的名单响应，确认球员分组位于 `data.list`，人员 ID 和姓名分别位于 `data.list[].data[].person_id`、`data.list[].data[].person_name`；球员位置取分组标题。
- [x] 编写离线响应校验和解析：导入前锋、中场、后卫、门将及唯一主教练，跳过其他教练和工作人员；共 25 条名单记录。
- [x] 增加 `roster-import` 命令：每次导入都会刷新人员姓名和 `attr` 并替换该队名单关联；这是读取本地样本，不是实时抓取。
- [x] 根据用户提供的球队赛程 URL 和响应样本，识别 `season_list` 当前赛季及 `data` 中的比赛字段。
- [x] 增加 `league_seasons` 中间表，以 `league_serial` 对应唯一最新 `season`；赛季升级时会在同一事务内删除该联赛旧赛季赛程。
- [x] 增加 `team_schedules` 表、赛程字段校验、按 `match_id` 去重和冲突拒绝；空赛程不会清空已有记录。
- [x] 增加赛程导入与 Markdown 加工输出；赛程按目标球队视角给出对手和比分，同时保留接口 A/B 侧别，不推断主客场。
- [x] 增加最小 `daily-report` 流程：从 SQLite 当前赛季 `team_schedules` 读取曼城赛程，筛选未来一个自然月并写入 `out/<日期>.md`；首次样例基于 2026-10-25，包含 6 场比赛。
- [x] 根据 mitmweb 与 Postman 中成功的曼城动态请求，实现只读 GET 与 `data.next` 分页跟随；按 `show_time` / `next.after` 到达用户所选开始时间后停止，检测重复 next URL，并设置 50 页上限。
- [x] 增加 `dynamics-report`：按 DSH 设置中的球队名称从 `teams[].dqd_name` 找到懂球帝 ID，每支球队分别生成全部动态和兴趣命中动态报告；不写数据库或原始响应文件。
- [x] 增加动态日报时间范围入口：可手动传 `--since` 和 `--until`，不传时生成上海时区当天 00:00 到当前时刻的日报。
- [x] 增加 DSH 插件每日调度：读取配置中的 `daily_run_time`，每天到点后运行动态日报 CLI。

### 第一版使用边界

- 动态日报和 DSH 每日调度属于第一版可用功能。
- 名单与赛程目前只支持本地样本导入，不包含实时请求；球员资料、统计和能力值接口仍待核验。
- DSH 设置页提供关注球队、关注内容、自动运行时间和 LDPlayer CA 维护工具；球队名称按 `config.toml` 的 `teams[].dqd_name` 精确匹配，Python 路径仍在 `[dynamics]` 中维护。

### 尚未完成

- [ ] 继续核验球队赛程和名单接口的真实 HTTP 方法、HTTP 状态、必要请求头和认证依赖；这些接口仍未实现在线请求。
- [ ] 按核验后的请求契约实现实时球队名单抓取命令。
- [ ] 用实时请求返回的名单刷新人员 ID、姓名、`attr` 和球队关联，并确认数据库记录与 APP 当前名单一致。
- [ ] 核验球员资料、球员统计、球员能力值这三个 Postman 请求线索；赛程 URL 和响应样本已收到，但 HTTP 状态、请求头与认证依赖待核验。
- [x] 增加 DSH 设置页：可编辑关注球队、动态日报运行时间和关注内容，并提供 LDPlayer mitmproxy CA 维护脚本入口。

### 现在的下一步

曼城动态只读请求已通过 mitmweb 与 Postman 核验并接入日报流程；日报会按设置中的球队名称从 `teams[].dqd_name` 映射 ID 并逐队请求。其他接口（球队名单、赛程、球员资料与统计）仍需分别核验请求契约；不要把真实 Cookie、Token 或账号标识写入项目或发给我。

把其余请求信息补入 [接口契约记录](docs/api-contract.md)。名单响应样本在 [team-roster.response.sample.json](fixtures/team-roster.response.sample.json)，赛程响应样本在 [team-schedule.response.sample.json](fixtures/team-schedule.response.sample.json)。赛程清洗和对阵视角加工位于 `src/dqd_scroll/lib/team_schedule.py`，导入流程位于 `src/dqd_scroll/workflow.py`；本地导入和报告命令分别是 `schedule-import`、`schedule-report`。赛程响应里的 `season_list[].url` 是服务端提供的赛季链接，不单独证明实际请求头或认证要求。名单、赛程等其他接口只有在契约核验后才实现在线请求。CLI 和 Python 脚本是 DSH 插件的后端调用方式；DeepSeek Harness bundle 入口已提供，项目不实现 MCP 服务。

## 在本机 DeepSeek Harness 中启用

项目已声明兼容 DSH `0.1.7-rc.1` 或更高版本的 bundle，并由 `cordis.patch.yml` 挂载每日动态日报插件。安装到 Electron 桌面版时，先从托盘菜单完全退出 DeepSeek Harness，再从项目根目录将工作区链接到 `desktop` profile；桌面版运行时会独占该 profile：

```powershell
dsh plugin --profile desktop add link:C:/www/dsh-dqd-scroll
dsh --profile desktop --dump-config
```

确认配置树中出现 `dsh-dqd-scroll` 后，重新启动 DeepSeek Harness。卸载时也先完全退出应用，再运行：

```powershell
dsh plugin --profile desktop remove dsh-dqd-scroll
```

此方式直接使用当前工作区，因此本地 `config.toml`、SQLite 数据库和日报目录仍在项目目录中。首次使用时在 DSH 设置 → 刷懂球帝中填写关注内容和运行时间；Python 可执行文件仍需在 `config.toml` 中配置，自动日报还要求本地 SQLite 已初始化。设置页将兴趣词与运行时间写回当前工作区的 `config.toml`。

## 创建并安装 Python 环境

在项目根目录运行：

```powershell
conda env create -f environment.yml
conda activate dqd
```

`environment.yml` 会创建 Python 3.11 环境，并通过 `pip install -e .` 将当前项目安装到环境中。项目当前只使用 Python 标准库；SQLite 由标准库 `sqlite3` 提供。

如果 `dqd` 环境已经创建，但尚未安装项目，或需要在已有环境中重新安装，在项目根目录运行：

```powershell
conda activate dqd
python -m pip install -e .
```

安装后可从项目根目录运行 `python -m dqd_scroll ...`，也可以使用项目命令 `dqd-scroll ...`。

## 配置球队

编辑根目录的 [config.toml](config.toml)：

```toml
database_path = 'data/dqd_scroll.sqlite3'

[[teams]]
dqd_id = 50000529
dqd_name = '曼城'
qiutan_name = '曼彻斯特城'
qiutan_serial = '26'
league_serial = 36
league_slug = 'epl'
match_league_name = '英超'
```

`teams` 是球队映射列表：`dqd_id` 和 `dqd_name` 来自懂球帝，`qiutan_name` 和 `qiutan_serial` 来自球探；`league_serial`、`league_slug`、`match_league_name` 描述所属联赛。完整的 20 条配置已经写入文件。

## 初始化 SQLite

```powershell
python -m dqd_scroll status
python -m dqd_scroll db-init --config config.toml
python -m dqd_scroll roster-import --database data/dqd_scroll.sqlite3 --team-id 50000529 --response-file fixtures/team-roster.response.sample.json
python -m dqd_scroll schedule-import --database data/dqd_scroll.sqlite3 --team-id 50000529 --response-file fixtures/team-schedule.response.sample.json --request-url 'https://sport-data.dongqiudi.com/soccer/biz/dqd/team/schedule/50000529?app=dqd&version=444&lang=zh-cn&season=2026-2027'
python -m dqd_scroll schedule-report --database data/dqd_scroll.sqlite3 --team-id 50000529
python -m dqd_scroll daily-report --database data/dqd_scroll.sqlite3 --team-id 50000529 --as-of 2026-10-25
```

`db-init` 只在初始化或更新球队映射时读取 `config.toml`，不访问懂球帝。它会把配置里的球队映射写入 `teams`，创建人员表 `players` 和人员关联表 `team_players`，并创建 `league_seasons` 与 `team_schedules`。`league_seasons` 通过 `(league_serial, season)` 建立联赛与赛季的关系；每个 `league_serial` 只保留当前最新赛季。数据库字段统一使用下划线命名，例如 `league_serial`、`league_slug`、`match_league_name`、`season_sort` 和 `team_a_id`。重复运行会按懂球帝球队 ID 更新配置映射，不会重复插入球队。数据库文件位于 `data/`，不会提交到版本库。名单导入、赛程导入和赛程报告命令直接接收 `--database`，球队名称和联赛编号都从 SQLite 的 `teams` 表读取；路径不存在时会报错，不会创建空数据库。

`roster-import` 使用 `--database` 指定已初始化的数据库，并读取本地 JSON 响应文件，不会访问懂球帝；导入前会确认球队已存在于 SQLite。它会校验人员 ID、姓名和 `attr`，在同一事务中刷新 `players` 人员资料并替换指定球队的 `team_players` 关联。`players.attr` 保存球员位置（前锋、中场、后卫、门将）；主教练也保存为一条人员记录，`attr` 为“主教练”。未来实现在线名单请求后，每次请求成功也要走同一同步流程，转会或更名才会反映到数据库。当前附带的是一份历史响应样本，导入它只会把数据库更新到该样本记录的名单状态，不代表懂球帝当前名单。

`schedule-import` 读取本地赛程响应文件，不会访问懂球帝。它要求 `season_list` 中恰有一个 `current=true` 的赛季，并校验其 `sort` 最大；命令还要求提供该响应对应的 `--request-url`，校验 URL 中的球队 ID 和 `season` 与响应当前赛季一致。`data` 中每场比赛都必须包含目标球队；同一 `match_id` 的完全相同记录会合并，字段冲突会报错。入库前会把 A/B 字段清洗成下划线命名；每队仅保留 `league_seasons` 所指向的当前赛季赛程。导入更高 `season_sort` 的新赛季时，会清掉该联赛所有球队的旧赛季赛程，然后保存当前球队的新赛程。`schedule-report` 从 SQLite 读取赛程，并按所选球队视角输出对手、比分、点球、比赛标题和状态；空字段按接口原样保留，不推断主客场。

`schedule-import`、`schedule-report` 和 `daily-report` 使用 `--database` 指向 SQLite；球队名称和联赛编号都从 `teams` 表读取，不再从 `config.toml` 重复读取。`daily-report` 从 `team_schedules` 表读取所选球队当前赛季赛程。懂球帝的 `start_play` 按 UTC 保存，数据库不改写；生成日报时转换为 UTC+8，再按本地日期筛选一个自然月：开始日期包含在内，下一月对应日期不包含在内。默认使用上海时区当天日期；传入 `--as-of YYYY-MM-DD` 可以复现指定日期的日报。请从项目根目录运行命令，Markdown 文件会写到 `out/<日期>.md`，重复生成同一日期会更新该文件。

日报每行依次显示 UTC+8 开球时间、星期、赛事、轮次、对阵和距上一场开球的间隔。轮次读取 `round_name`，该字段为空时从比赛标题中提取；文本已有“第”时原样显示，没有“第”但含阶段文本和数字 `gameweek` 时，组合为“阶段 第x轮”。没有阶段文本时保留 `gameweek` 原值。对阵按“对手vs所选球队”显示。间隔根据 SQLite 中该球队按开球时间排序的全部当前赛季比赛计算，首场比赛没有上一场时留空；间隔以小时显示。

## 球队动态日报

球队名称、动态兴趣词和插件调度设置保存在 `config.toml` 的 `[dynamics]` 中。DSH 设置 → 刷懂球帝可逐行填写关注球队和关注内容，并编辑每日运行时间。球队名称必须与上方 `[[teams]]` 中的 `dqd_name` 完全一致；程序会用该名称找到对应 `dqd_id`。填写多个名称后会逐队抓取，每支球队单独生成两份报告：`out/dynamics/<日期>/<懂球帝球队名称>-all.md` 保存所选时间范围内的全部动态；`out/dynamics/<日期>/<懂球帝球队名称>-interests.md` 只保存命中兴趣词的动态。

关注内容任一关键词出现在动态标题、描述或正文中，该条动态就会进入兴趣命中报告。时间按 `Asia/Shanghai` 解释；保存后调度器下一分钟检查时读取新设置。关注球队至少填一支；兴趣列表留空会暂停自动日报，手动运行时报错，不会自动放宽为全量动态。Python 可执行文件仍通过 `python_path` 配置。

```toml
[dynamics]
team_names = ['曼城', '阿森纳'] # 名称需与 teams[].dqd_name 完全一致
interests = ['伤病', '训练'] # 示例；请替换成你要关注的关键词
daily_run_time = '21:00'
python_path = 'C:/ProgramData/miniconda3/python.exe'
```

DSH 设置页的“关注球队（每行一个懂球帝球队名称）”会写入 `team_names`。可选名称来自 `config.toml` 已配置的 `[[teams]]` 清单；名称不匹配或重复时会报错，不会猜测球队 ID。

如果运行日报时提示“请先在 config.toml 的 dynamics.interests 中配置关注内容”，说明 `interests` 还是空列表 `[]`。打开项目根目录的 `config.toml`，在 `[dynamics]` 下把它改成非空关键词列表；每个词用单引号括起来，多个词用逗号分隔。上面的“伤病”和“训练”只是填写格式示例，请换成你自己的关注词。任意一个词出现在动态标题、描述或正文中，该条动态就会进入日报。保存配置后重新运行日报命令。

手动运行当前日期日报：

```powershell
python -m dqd_scroll dynamics-report --config config.toml
```

手动选定动态的起止时间：

```powershell
python -m dqd_scroll dynamics-report --config config.toml --since 2026-10-24T11:30:00 --until 2026-10-25T11:30:00
```

时间按上海本地时间解释，起止时间都包含在筛选范围内。每支球队都从最新页开始采集，用动态的 `show_time` 筛选；只有 `data.next.after` 和当前整页的 `show_time` 都早于 `--since` 时才停止。每支球队最多请求 50 页；到达上限仍未到开始时间时，该队报告会标记为不完整。重复 `data.next` 会立即报错停止。动态内容只在内存处理，报告按日期和球队名称分开放入 `out/dynamics/<日期>/`；每支球队各有 `-all.md` 和 `-interests.md` 两个文件。SQLite 中没有动态表，也不会保存原始接口响应。

DSH 插件必须保持运行，才能在 `daily_run_time` 到达后启动日报 CLI。插件只在 `data/dynamics-schedule-state.json` 记录当天是否已成功生成日报，不保存动态内容；命令失败时会在下一分钟重试。手动命令不依赖 DSH 定时器。

设置页的“刷新 LDPlayer mitmproxy CA”按钮会调用 `tools/refresh-dqd-mitm-ca.ps1`，执行前会显示确认。它要求 LDPlayer14 的 `emulator-5556` 在线并可用 root，且本机 mitmproxy CA 的 DER SHA-256 与脚本内固定值一致；证书挂载在模拟器重启后失效。脚本仅用于 Windows 本机维护，不是日报调度的一部分。

## 接口验证顺序

1. 在授权设备上通过懂球帝 APP 正常打开球队赛程和名单，抓取对应原始请求信息并记录 APP 版本、请求方法、HTTP 状态、请求头名称和认证依赖。
2. 把赛程 URL、名单样本和真实请求证据补进 [接口契约记录](docs/api-contract.md)，确认哪些请求头或登录态确实必要。
3. 对名单、赛程等尚未核验的接口，先确认请求契约，再实现对应只读 API 方法。
4. 曼城动态日报由 DSH 插件按配置时间调用 Python CLI；名单、赛程在线流程仍待核验后接入。

名单和赛程的旧 Postman URL、响应内的 `season_list[].url` 都不能单独证明请求头、认证要求或调用授权。曼城动态的 DSH 定时入口已实现；其他数据功能通过项目自己的 Python 命令和脚本提供，不使用 MCP。

## 项目结构

```text
config.toml                 db-init 的球队映射、SQLite 文件路径与动态日报用户偏好
package.json                Python 包与 DSH bundle 元数据
src/dqd_scroll/
  __main__.py               python -m dqd_scroll 入口
  cli.py                    项目状态、数据库、名单、赛程和动态日报命令
  config.py                 读取并验证 TOML 配置
  repository.py             数据库建表、查询和写入
  models.py                 名单、赛季、赛程与动态记录模型
  workflow.py               串联接口请求、数据清洗和数据库读写
  api/
    auth.py                 其他接口的认证来源占位
    client.py               标准库 GET JSON 客户端
  dqd_api.py              球队动态只读分页 API；其他 API 仍待核验
  lib/
    __init__.py             名单和赛程数据加工逻辑
    team_roster.py          校验、筛选、清洗并去重球队名单响应
    team_schedule.py        选择当前赛季、清洗去重并加工球队视角赛程
    report.py               筛选一个自然月的赛程并加工生成 Markdown 日报
    team_dynamics.py        校验动态字段并按用户兴趣词筛选
    dynamics_report.py      生成动态 Markdown 日报
index.js                    DSH 插件入口、设置 API 和每日动态日报调度
client.js                   DSH 设置页：运行时间、关注内容和维护工具
settings-api.js             配置读取与写回、固定维护脚本调用
cordis.patch.yml            DSH bundle 层，将每日动态调度入口挂载到 profile
tools/
  README.md                 开发和维护脚本说明
  refresh-dqd-mitm-ca.ps1   LDPlayer14 mitmproxy CA 维护脚本
docs/
  api-contract.md           接口核验记录与待确认项
fixtures/
  README.md                 响应样本规则
  team-roster.response.sample.json   脱敏球队名单响应样本
  team-schedule.response.sample.json 用户提供的球队赛程响应样本
prompts/
  duty.md                   后续的内容筛选与摘要口径
```

数据流按职责分层：`api` 负责发请求并返回原始响应；`src/dqd_scroll/lib` 是名单、赛程和动态的校验、筛选及加工逻辑位置；`repository` 负责 SQLite 查询和写入；`workflow` 负责把这些步骤串起来。动态日报流程不调用 `repository`，动态只在内存中生成全部动态与兴趣命中两种报告。根目录的 `index.js` 负责 DSH 每日调度；插件通过调用项目的 Python CLI 使用功能，不实现 MCP，也不重复实现 Python 业务逻辑。`tools/` 只放没有现成 CLI 入口的独立开发或维护脚本。名单按 `person_id` 去重、赛程按 `match_id` 去重，动态按本次运行的 `id` 去重；重复内容冲突时会报错。曼城动态 API 和 DSH 定时入口已实现；名单、赛程及球员信息等其他实时接口仍未实现。

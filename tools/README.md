# 开发工具脚本

DSH 插件通过运行项目自己的 Python 命令和脚本调用功能，不提供 MCP 服务。现有命令入口是 `python -m dqd_scroll`；名单清洗、数据库读写等业务逻辑只实现在 `src/dqd_scroll/`，这里不能再复制一份。

本目录留给需要独立运行的开发或维护脚本。`refresh-dqd-mitm-ca.ps1` 是 LDPlayer14 的 mitmproxy CA 维护工具，DSH 设置 → 刷懂球帝提供固定按钮调用入口；执行前会要求确认。该脚本核验本机 CA 的固定 SHA-256，并要求 `emulator-5556` 在线且 root 可用，应用重启后需要重新挂载。

若某项日报或数据处理功能已由 Python CLI 提供，DSH 入口应调用该 CLI，不再为同一功能增加第二个实现。

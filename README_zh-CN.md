# Elite Dangerous 中子星规划器

[English](README.md) · [简体中文](README_zh-CN.md)

为《Elite Dangerous》玩家提供的 Windows 桌面小工具：保存常用配船和目的地，按顺序设置途经点，再通过 Spansh 规划适合当前配船的中子星航线。

**它只是对 [Spansh 已有的舰船航线规划工具](https://spansh.co.uk/exact-plotter)做了一点桌面端扩展，本质上仍然是使用 Spansh 的规划服务，并非另写了一套规划算法。** 实际航线计算由 Spansh 完成，核心规划能力归功于 Spansh。如果不需要本地收藏和桌面操作，直接使用 Spansh 网页即可。

本工具非 Frontier／Spansh 官方产品。当前版本为 **0.1.0-beta.1（测试版）**，可能存在 Bug，请在游戏中核对路线和燃油情况。

## 能做什么

- **保存常用配船**：导入 Coriolis JSON 或 EDSY SLEF，为不同配船命名收藏。
- **收藏目的地**：保存常去的星系，之后一键填入终点；支持重命名和删除。
- **按途经点规划**：依次经过指定星系，可调整途经点顺序。
- **调整规划条件**：默认启用中子增压，可设置货物、储备燃油、注入和算法等选项。
- **查看和带走结果**：预览普通／中子增压满油跳距，复制结果星系名或导出 CSV。
- **按习惯使用**：中英文切换、跟随系统／浅色／深色主题，重启后恢复设置和收藏。

## 下载与启动

目前尚未发布正式的 Release 安装包，Windows 测试版可从 [Actions 构建页面](https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/actions/workflows/ci.yml)下载：

1. 登录 GitHub，打开最近一次成功的构建。
2. 在页面底部 **Artifacts** 下载 `EliteDangerousNeutronPlanner-Windows`。
3. 解压后运行 `EliteDangerousNeutronPlanner.exe`，无需安装 Python。

配船属性首次解析需要联网获取模组数据；航线规划需要连接 Spansh。

## 第一次规划

1. 点击“新增舰船配置”，输入收藏名称，粘贴配船 JSON，或点击“导入 JSON 文件”。**这里需要配船数据文件，不是 Coriolis／EDSY 网页链接。**
2. 保存并选中配船，检查显示的船型和满油跳距。
3. 填写起点与终点星系；如需中途停留，添加途经点并调整顺序。
4. 按实际情况设置货物、储备燃油等选项，然后点击“规划航线”。
5. 查看结果，按需复制星系名或导出 CSV。

### 收藏常去的目的地

在“终点星系”填写星系，点击“收藏当前终点”并命名。下次从“目的地收藏”中选择，点击“设为终点”即可复用。

收藏重启后仍保留，同名收藏不会被覆盖。保存收藏不会联网验证星系，也不会自动开始规划；星系会在规划时解析。

## 出发前请注意

- **每一段都假设主油箱满油出发。** 设置途经点后，不会继承上一段的到达油量，**也不保证途经点能够补油**。请自行确认补油条件。
- 跳距预览是理论满油数值，不代表当前位置可以中子增压，也不保证实际路线可行。
- “停止”会停止本地等待和后续分段提交，但不保证撤销 Spansh 已收到的任务。
- 规划中断或失败时，只保留已验证的完整分段；导出部分结果需要确认，不能当作完整路线使用。

更多细节见[规划说明](docs/route-planner.md)。

## 数据与隐私

设置和收藏保存在本机 `%LOCALAPPDATA%\EliteDangerousNeutronPlanner`。收藏目的地和保存配船本身不会提交航线任务。

**开始规划会将所选配船和航点发送到 Spansh。** 请先移除不希望传输的私人字段。配船属性预览需要获取模组数据，但不会提交路线任务。

### 从旧筛选器导入配船收藏

如果你用过 [Elite Dangerous 筛选器](https://github.com/kxdxzr/Elite_dangerous_Filter)中的规划器，可点击“导入旧版舰船收藏”，手动选择旧数据目录里的 `route_ship_favorites.json`。通常位于 `%LOCALAPPDATA%\EliteDangerousFilter`，旧源码版也可能在其项目 `data` 文件夹中。

导入不会修改或删除旧文件，名称冲突时会拒绝导入，不会覆盖。本工具与旧筛选器的数据分开保存。

## 反馈问题

欢迎通过 [Issues](https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/issues)反馈 Bug 或建议。请说明版本、操作步骤和错误提示；截图或附件中请遮盖私人配船及其他不希望公开的信息。

## 源码与许可

本项目从 Elite Dangerous 筛选器拆分，采用 GPL-3.0-only 许可。详见 [LICENSE](LICENSE) 与[来源及第三方数据说明](NOTICE.md)。

如需从源码运行，安装 Python 3.11+（含 tkinter），在项目目录执行 `python planner.py`。运行时无需第三方 Python 包。维护、测试和打包说明见 [HANDOFF.md](HANDOFF.md)，贡献前请阅读 [AGENTS.md](AGENTS.md)。

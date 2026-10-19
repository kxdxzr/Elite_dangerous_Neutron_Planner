# 中子星规划器维护交接

本文件面向接手此项目的新 session；首先阅读根目录 `AGENTS.md`。

## 1. 项目与当前状态

- 本地：`E:/opencode/bridge/Elite_dangerous_Neutron_Planner`
- GitHub：https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner
- 分支：`main`，远端 `origin`；使用 `git status` / `git log -3` 查看实时状态。
- 拆分基线提交：`1d3413462f0d31554e0ce35772a90fd44485311a`。
- 独立版本：`0.1.0-beta.1`，位于 `src/export_metadata.py`。
- 已推送并通过 Windows CI；**没有创建 GitHub Release，也没有发布版本标签**。
- CI 基线：https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/actions/runs/39213832840
- Windows 构建附件：该运行的 `EliteDangerousNeutronPlanner-Windows` artifact。
- 本地 EXE：`dist/EliteDangerousNeutronPlanner.exe`，不纳入 Git。

已完成的验证：

| 项目 | 结果与范围 |
| --- | --- |
| 独立仓库测试 | 45 项通过，包含原规划器核心／GUI、导出、排序、进度、DPI及迁移测试 |
| 源码离线冒烟 | 通过，验证主窗口、主题、语言、设置重启恢复、航点及 DPI |
| 本地 PyInstaller EXE | 构建成功；实际启动 EXE 的离线冒烟通过，`frozen=true`、DPI awareness=1 |
| GitHub Windows CI | 成功；包含源码测试、源码冒烟、构建和 EXE 冒烟 |
| 实际在线路线 | 本次独立拆分没有重新做在线路线查询；核心测试使用注入的模拟服务 |

`docs/upstream-route-planner.md` 中的在线验证属于上游历史，不能冒充独立版的新实测。

## 2. 用户确定的产品边界

拆分基线后新增（尚未重新构建本地 EXE）：目的地命名收藏，独立保存于
`destination_favorites.json`；界面支持收藏当前终点、设为终点、重命名及确认删除，
名称冲突拒绝覆盖。保存不联网验证星系，也不开始规划。
存储实现为 `src/destination_favorites.py`，对应单元测试及 GUI 测试已补充；
当前源码隔离测试 51 项通过，源码离线冒烟通过（DPI awareness=1）。
前述本地 EXE／CI 验证仍是拆分基线，不包含这次新功能。

这是从筛选器迁出的**独立中子星／按配船航线规划工具**，不是新增筛选器功能。

- 保留 Coriolis JSON / EDSY SLEF 导入、本地命名收藏、船型与普通／中子满油跳距预览。
- 保留有序途经点、货物、储备燃油、注入、算法、中子及补油相关选项。
- 默认启用中子增压；后端是 Spansh exact plotting，而非固定跳距的简化中子路由。
- 不引入任务来源、RES、工程师采购、站点筛选、稀有商品等功能。
- 中英文、跟随系统／亮／暗主题、字体与 Windows DPI 修复已随必要共享组件迁入。
- 用户不喜欢来回晃的进度条：已知工作量显示计数／百分比，未知总量只显示数量与状态。
- 结果支持表头排序；**有序途经点编辑表不能排序**。
- Beta 需说明拆分／UI 重构存在潜在 Bug，不能声称绝无问题。

原项目已在 `a4d2ce5f5049bcc240241c0c6ee921b4fce55b98` 移除规划器实现与测试，
双语 README 说明迁移，界面按钮仅打开新仓库。旧 v0.1.3 / v0.1.4-beta.1 EXE 未被替换。
原项目的稀有商品中子**几何顺路筛选**仍在那里，不属于本项目；其停止检查已解除对规划器的依赖。

## 3. 代码地图

| 文件 | 作用 |
| --- | --- |
| `planner.py` | 源码入口，设置本项目 `src` 路径 |
| `src/planner_app.py` | 独立宿主 App、主窗口、主题／语言、设置保存恢复、旧收藏导入入口、CLI |
| `src/route_gui.py` | 完整规划界面；可直接使用根窗口，也可供测试创建 Toplevel；后台计算、主线程队列回填 |
| `src/route_tool.py` | HTTP、收藏、Options、星系解析、异步任务提交／轮询、分段验证、合并、CSV |
| `src/route_ship.py` | 配船解析、工程参数、船型身份、满油跳距、固定版本 FSD 事实目录 |
| `src/suggestion_ui.py` | 从上游抽出的输入联想与主线程调度；不导入 `filter_gui` |
| `src/system_names.py` | 有界响应、超时与内存缓存的 Spansh 星系名候选查询 |
| `src/runtime_paths.py` | 本项目独立数据路径 |
| `src/session_store.py` | 原子 JSON 写入，避免半文件 |
| `src/migration.py` | 旧收藏显式复制导入；验证、限大小、冲突不覆盖 |
| `src/appearance.py`, `src/ui_display.py` | 主题、系统 DPI、可用中文 UI 字体选择 |
| `src/i18n.py`, `src/localized_tk.py` | 翻译及原始模型值与显示值分离；包括通用表格行为 |
| `src/result_sort.py`, `src/result_format.py`, `src/result_copy.py` | 排序、数字格式、复制 |
| `src/search_progress.py` | 真实阶段进度，不臆造端到端耗时百分比 |
| `src/export_metadata.py` | 独立项目作者／名称／版本／URL及 CSV 来源信息 |
| `src/smoke_test.py` | 源码／frozen 通用的离线启动与设置重启测试 |
| `EliteDangerousNeutronPlanner.spec` | PyInstaller one-file GUI 构建，捆绑 LICENSE 与 DPI manifest |
| `.github/workflows/ci.yml` | Windows 测试、离线冒烟、EXE 构建与 artifact |

`route_gui` 仅通过宿主的 `root` / `localizer` 工作，不需要完整筛选器 App。
`App.route_window()` 保留为测试适配接口；正常启动使用 `as_root=True`，没有隐藏的常驻宿主窗口。

## 4. 不能改变的规划语义

1. **各段独立满主油箱出发**。不继承上一段到达油量，也不保证途经点能补油。
2. 第一段“已增压”不自动沿用到后续段。
3. 共享端点合并时，前段到达燃油与后段假定出发燃油／操作分别保留。
4. 全部航点先解析；核查返回路线的端点、跳跃数据、状态。未知物理参数报错，不猜测。
5. 停止只取消本地轮询及后续提交，不能保证服务器已有任务被取消。
6. 错误／停止仅保留已验证完整分段；部分导出必须确认，并保留未完成与满油假设标记。
7. 预览是理论满油跳距，不保证当前位置有中子星、当前已增压或路线能实际补油。
8. CSV 使用独立项目元数据；公式风险文本须保留转义逻辑。

具体物理公式与支持范围见 `route_ship.py` 及清楚标为历史的上游说明。

## 5. 数据、隐私与旧收藏

- Windows：`%LOCALAPPDATA%/EliteDangerousNeutronPlanner`。
- 仅认 `ELITE_NEUTRON_DATA_DIR` 覆盖；不使用旧工具的 `ELITE_FILTER_DATA_DIR`。
- `settings.json`：语言、主题、编辑参数、途经点；无完整路线收藏库／账号体系。
- `destination_favorites.json`：本地命名的目的地星系收藏，不含配船或完整路线。
- `route_ship_favorites.json`：命名的配船 JSON；`route_module_cache.json`：按固定 revision 缓存 FSD 事实。
- 旧收藏必须用户手动选择文件导入，原文件不改不删；同名冲突整体拒绝，不静默覆盖。
- 旧缓存不迁移，按需重新获取。不得自动扫描个人 Journal 目录。
- 规划会发送所选配船与航点到 Spansh。预览仅取事实目录，不提交路线任务。
- 不在仓库／issue／测试日志中上传真实私人配船、Journal、收藏、settings 或缓存。

## 6. 维护命令与环境

当前本机环境：Windows x64、Python 3.13.9、PyInstaller 6.20.0。
README 要求 Python 3.11+（含 tkinter）；本次独立 CI 仅覆盖 Windows/Python 3.13，
不能把其他系统／Python 版本支持当作已经验证。运行时没有第三方包。

在**独立仓库目录**运行：

```powershell
git status --short --branch
python scripts/run_tests.py
python planner.py --smoke-test C:/Users/yulep/AppData/Local/Temp/opencode/neutron-source-smoke.json
python -m compileall -q src tests scripts planner.py
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean EliteDangerousNeutronPlanner.spec
```

测试脚本会将数据目录隔离到临时目录；烟测也自行隔离，不能因此删除真实数据来“清状态”。
实际 EXE 是 GUI 程序，PowerShell 用等待进程的方式验收：

```powershell
$report = 'C:/Users/yulep/AppData/Local/Temp/opencode/neutron-exe-smoke.json'
$process = Start-Process './dist/EliteDangerousNeutronPlanner.exe' -ArgumentList '--smoke-test', $report -Wait -PassThru
Get-Content $report
if ($process.ExitCode -ne 0) { throw 'EXE smoke failed' }
```

烟测通过不等于线上 Spansh 协议仍有效。如需要在线回归，用明确批准的合成配船与少量航点，
不拿用户收藏做无提示上传，不循环重提失败任务。UI 测试可能短暂显示窗口。

## 7. 许可与发布

- GPL-3.0-only，完整许可在 `LICENSE`；来源与上游提交在 `NOTICE.md`。
- 不将旧 MIT 授权历史说成可撤销。新仓库迁入的是 GPL 版本及后续修复。
- `route_ship.DATA_REVISION` 固定为 `0db9234b5b9ce8c939ea84133d7ce336eea88e27`。
- EDCD/coriolis-data 的 JSON 版权属于 Frontier，不能把它误认为 MIT；目录运行时下载，未捆绑。
- Windows 字体只选择系统可用字体，未分发字体文件；未完成对所有第三方服务条款的完整许可审计。
- 发布前同时核对版本、README、LICENSE、NOTICE、source zip及校验和；新项目独立版本线。
- 此次仅推送源码与 CI artifact。发布 Beta／标签／Release 附件需用户明确授权。

## 8. 待完善项（不是已确认故障）

1. 对损坏／手改的 `settings.json` 增加更细的字段、枚举、Boolean 类型校验；当前恢复主要做结构与基础类型检查。
2. 视需要补充独立版在线协议回归、系统联想测试、主题测试及当前独立界面截图。
3. 泛用翻译表／进度组件保留了部分上游无关词条；可以逐步精简，但不要因“看起来没用”破坏共享翻译行为。
4. 可以增加收藏冲突的交互式重命名。当前设计是安全拒绝，不应改成静默覆盖。
5. 根窗口正常关闭会保存设置；测试的 Toplevel 适配不是另一套完整的多窗口管理系统。
6. 配船预览、精确路由和实际星系补油能力是不同层次，不把理论跳距当作真实可行路线。

## 9. 新 session 的第一步

1. 将工作目录切到本仓库，读 `AGENTS.md`、本文件、双语 README 与 `NOTICE.md`。
2. `git status` 确认有没有用户新改动，运行隔离测试和离线烟测建立基线。
3. 只在本仓库处理规划器，不为修独立版回头改筛选器。
4. 原项目目录仍有大量其他功能的未提交改动，属于前一 session 工作，不能 reset/clean/一并提交。
5. 若用户要求恢复内置版或同步公共组件，先讨论两个项目的边界，而不是重新引入跨仓库 import。

# 中子星规划器维护交接

本文件面向接手此项目的新 session；首先阅读根目录 `AGENTS.md`。

## 1. 项目与当前状态

- 本地：`E:/opencode/bridge/Elite_dangerous_Neutron_Planner`
- GitHub：https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner
- 分支：`main`，远端 `origin`；使用 `git status` / `git log -3` 查看实时状态。
- 拆分基线提交：`1d3413462f0d31554e0ce35772a90fd44485311a`。
- 独立版本：`0.1.0`，位于 `src/export_metadata.py`。
- 用户已明确授权发布 `v0.1.0` Release；发布包包含 Windows EXE、源码及 SHA-256 校验文件。
- CI 基线：https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/actions/runs/39213832840
- Windows 构建附件：该运行的 `EliteDangerousNeutronPlanner-Windows` artifact。
- 本地 EXE：`dist/EliteDangerousNeutronPlanner.exe`，不纳入 Git。

v0.1.0 发布验证：95 项隔离测试通过；源码与重新构建 EXE 的离线冒烟通过，
EXE 报告版本 `0.1.0`、`frozen=true`、DPI awareness=1。发布不包含悬浮窗，
未使用私人配船做在线测试。发布说明保留满油分段／日志隐私／剪贴板警告，
并披露跳距预览辅助油箱质量处理与 EDSY 存在小幅差异（本次未修正物理公式）。

2026-10-23 用户授权将当前代码打包并上传：本轮重新运行 95 项隔离测试全部通过，
源码与新构建 EXE 离线冒烟均 `ok=true`（EXE `frozen=true`、DPI awareness=1），
compileall 和 diff 检查通过。已重新构建本地 EXE；本次上传采用 main 源码推送及
Windows CI artifact，不创建 Release／版本标签。下方“未提交／未打包”等为历史记录。
悬浮窗尚未实现；用户明确其未来形态应为纯信息显示、鼠标穿透、无交互且不抢焦点。

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
该次源码隔离测试 51 项通过，源码离线冒烟通过（DPI awareness=1）。
前述本地 EXE／CI 验证仍是拆分基线，不包含这次新功能。

后续本地未提交改动：放大选择框及联想列表、调整表单布局；用蓝色标识
Spansh `has_neutron=true/1` 的行（不是按跳距猜测，明暗主题均有配色）；
新增 `src/route_history.py`，原子保存最近 5 次已返回的规划参数和结果，含失败／停止状态。
历史不保存原始配船，仅保存配船内容摘要与收藏名；回看时按摘要匹配现有配船，
配船删除或修改后仍可查看／导出结果，但需重新选择配船才能再规划。
当前显示完整结果且请求摘要未变化时，规划按钮不提交、不清空结果；失败／停止可重试。
摘要包含实际配船内容、按序航点和全部规划选项，不含语言／主题。

本轮验证：58 项测试中 57 项通过；原有小窗口可见性测试失败于 `winfo_ismapped()==0`。
同环境独立空白 Tk/Toplevel 也始终报告未映射，未放宽或跳过原断言，需在正常桌面补验布局。
源码离线冒烟通过（DPI awareness=2），compileall 与 diff 检查通过；未做在线查询，
未重新打包 EXE、未推送或发布。源码冒烟不检查实际窗口可见性，不能替代上述布局验收。

另修复配船编辑器：原先 Text 先 pack 且请求空间较大，后 pack 的导入／保存按钮
在较小窗口或高 DPI 下会被挤出。改用 grid，仅 JSON 区域参与伸缩，底部操作行
固定高度，并补充双向滚动条、随宽度换行的提示和初始窗口尺寸约束。
新增布局结构／手动粘贴后确认覆盖的回归测试，与原编辑器流程测试共 2 项通过，
源码离线冒烟通过；真实桌面可见性仍待补验。未修改用户的收藏或配船数值。

新增用户明确要求的 Journal 起点按钮：`src/journal_location.py` 在点击时只读本地
Journal，默认 Saved Games 标准路径，可手动选择并保存其他目录。后台线程读取，
主线程填回起点，显示日志时间；不自动规划、不持续追踪、不上传日志。
只接受 `Location`、`FSDJump`、`CarrierJump` 的 `StarSystem`，忽略 `StartJump` 目的地。
选择最近活动的日志会话，可回查同一会话的编号分卷，不跨会话回退；倒序读取限 16 MiB，
单行限 1 MiB。读取期间用户若编辑起点，回填不覆盖。回填绕过输入联想，避免触发联网候选查询。
本次仅用合成日志测试，未读取真实个人 Journal；目前全套 69 项中 68 项通过，
仍是上述窗口映射断言失败；源码离线冒烟（含日志目录设置重启恢复）、编译及 diff 检查通过。

航线速度优化（同为本地未提交改动）：
- `route_tool.SystemCache`：当前进程内最多 512 条成功精确解析，TTL 24 小时；失败不缓存，返回副本，线程锁保护；注入的模拟 HTTP 默认不共享生产缓存。
- `resolve_points`：去重航点后最多两个并发 GET，结果恢复原航点顺序。全部解析成功才提交路线；取消／失败不再安排后续 GET，也不提交任何路线任务。已发出的 GET 不能强行中断。
- 分段路线仍串行，保留端点核对、已验证完整前缀及满油假设。排队轮询仍 2 秒逐步退避至 10 秒；进入 started/running 后检查间隔上限 4 秒，不重新提交任务。
- 自动复用最近 5 次中 24 小时内同摘要的完整结果，界面明确标识原记录时间和未重新查询。当前不完整结果的同参数重试不被较早成功记录拦截。
- 请求摘要新增固定事实 revision 和物理模型版本号（目前 1）；修改物理解析规则须同步提升模型号，防止旧结果自动复用。旧历史仍可手动查看。
- 进度区分配船／解析／Spansh 排队与计算；结果 `timings` 保存配船处理、解析、路线请求与等待、总耗时。缓存结果显示的是原次查询耗时，不是本次读取耗时。
- 最终全套 78 项测试中 77 项通过，唯一失败仍是上述映射断言；源码离线冒烟、compileall、diff 检查通过。合成 8 航点、每 GET 模拟 40 ms：单线程 0.328 s、双线程 0.164 s、缓存命中 0.001 s；这是模拟准备阶段，不是独立版线上路线提速实测。未上传真实配船、未在线查询、未打包／推送／发布。

最新 UI 调整：用户不喜欢上下分区，已移除 Panedwindow，改为单 Canvas 整页滚动，
设置、规划操作及结果位于同一内容 Frame；应用顶部语言／主题工具栏保留。
页面专用 bindtag 在控件类绑定前处理滚轮，滚过关闭的下拉框不会误改参数，
滚过结果表也滚整页；Shift+滚轮可横滚表格。配船编辑器／下拉弹窗不套用页面绑定。
结果表按行数增高（8–25 行），长路线保留表内纵向滚动条及横向滚动条，避免无限增大 Tk 子窗口。
新增布局与滚轮回归测试，并将原分区可见性测试更新为滚动到底部检查结果可见。
服务重启后桌面窗口映射恢复，本轮 **80 项测试全部通过**（包括 1400×850／1100×700
窗口下滚动至结果、结果实际映射与高度断言）；源码离线冒烟、compileall 和 diff 检查通过。
同时修正历史下拉列表重绘时索引变量被循环覆盖的问题。仍未打包、推送或发布。

最新新增：主窗口结果区“跟随游戏位置”和“自动复制计划下一跳”两个开关，均每次启动
默认关闭，不保存为路线参数／设置，不做悬浮窗。明确开启跟随后，后台约每 2 秒检查
JournalFollower，正常仅读新增内容；目录有变或每 10 秒复查新会话／分卷，初始与截断时
建立有界快照。只接受已确认位置事件，不使用 StartJump。后台只入队，Tk 标记及剪贴板
仅主线程操作；关闭／换目录的旧结果以 generation 忽略，退出设置 stop Event。
`src/route_position.py` 使用原始 rows 顺序和名称索引，结果排序不影响下一跳；同名多次
出现有歧义不猜测，可选中对应行后“确认所选位置”。新记录仍指向同名重复星系且无法
判断是否错过往返时，保守回到待确认状态。不在路线中仅清旧绿色标记／文字，不复制、
不弹偏航提示、不改起点、不重规划；不自动滚动，可点“定位当前行”。
自动复制仅写纯下一星系名，同一当前路线位置成功复制一次后不重复覆盖剪贴板；
失败不标成功，用户可切换开关重试。终点／已验证部分路线末尾不复制，后者明确标记
路线未完成。绿色当前位置覆盖中子蓝色，离开该行后中子标记仍保留。
新增合成日志增量／分卷会话／截断测试、纯位置模型和 GUI／剪贴板模拟测试。
本轮 **95 项测试全部通过**；源码离线冒烟（包含两个开关重启默认关闭且不启动读取器）、
compileall、diff 检查通过。未读真实个人 Journal、未联网测试路线，未打包、提交、推送或发布。

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
- `route_history.json`：最近 5 次规划的参数和路线结果（可能含未完成结果），属于本地私人数据，不能直接上传日志或 issue。
- `route_ship_favorites.json`：命名的配船 JSON；`route_module_cache.json`：按固定 revision 缓存 FSD 事实。
- 旧收藏必须用户手动选择文件导入，原文件不改不删；同名冲突整体拒绝，不静默覆盖。
- 旧缓存不迁移，按需重新获取。不得在启动时擅自扫描个人 Journal；仅用户点击位置按钮或明确开启“跟随游戏位置”后允许只读指定／默认日志目录。两个跟随／复制开关每次启动必须默认关闭。
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

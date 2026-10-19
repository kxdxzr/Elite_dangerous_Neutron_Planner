# Elite Dangerous 中子星规划器

[English](README.md) · [简体中文](README_zh-CN.md)

从 [Elite Dangerous 筛选器](https://github.com/kxdxzr/Elite_dangerous_Filter) 拆分的独立桌面工具。

**初始拆分 Beta：0.1.0-beta.1。涉及 UI 重构与拆分，不保证没有潜在 Bug。**
非 Frontier／Spansh 官方工具。暂未发布 GitHub Release；CI 通过后可从 Actions 下载 Windows 构建附件。

## 功能

- 导入单个 Coriolis JSON／EDSY SLEF 配船，本地命名收藏。
- 使用 Spansh exact 接口按配船规划，默认启用中子增压。
- 有序途经点编辑、货物、储备燃油、注入与算法设置。
- 普通／中子增压满油跳距预览，结果排序、复制与 CSV 导出。
- 英文／中文，跟随系统／浅色／深色主题，Windows 系统 DPI 感知。
- 独立保存设置，支持手动导入筛选器旧收藏。

每段均假设主油箱满油出发，**不保证跨段燃油连续，也不保证途经点能补油**。
停止不能保证撤销服务器已提交任务，部分结果导出需确认。详见[规划说明](docs/route-planner.md)。

## 运行与构建

Python 3.11+（含 tkinter），运行时无第三方包：

```powershell
python planner.py
python scripts/run_tests.py
python planner.py --smoke-test smoke.json
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean EliteDangerousNeutronPlanner.spec
```

EXE 位于 `dist/EliteDangerousNeutronPlanner.exe`。

## 数据与旧收藏

Windows 使用 `%LOCALAPPDATA%\EliteDangerousNeutronPlanner`，与原工具的
`%LOCALAPPDATA%\EliteDangerousFilter` 分开。仅用 `ELITE_NEUTRON_DATA_DIR` 覆盖路径。

点击“导入旧版舰船收藏”，选择旧工具数据目录里的 `route_ship_favorites.json`
（源码运行通常在旧项目 `data/` 下）。不会修改或删除旧文件，名称冲突时不覆盖。
旧缓存不移动，模组目录按需重新下载。

规划会将所选配船及航点发送给 Spansh，请移除不希望传输的私人字段；属性预览不提交路线任务。

## 许可

GPL-3.0-only；[来源、署名与第三方数据边界](NOTICE.md)。

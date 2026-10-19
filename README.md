# Elite Dangerous Neutron Planner

[English](README.md) · [简体中文](README_zh-CN.md)

Maintainers / next sessions: start with [AGENTS.md](AGENTS.md) and [HANDOFF.md](HANDOFF.md).

A standalone Windows desktop neutron-assisted route planner, extracted from
[Elite Dangerous Filter](https://github.com/kxdxzr/Elite_dangerous_Filter).

**Initial split Beta: 0.1.0-beta.1. UI refactoring/extraction may have potential bugs.**
This is not an official Frontier or Spansh application. No GitHub Release has been
published yet; Windows CI builds are available in Actions artifacts after CI passes.

## Features

- Import one Coriolis JSON / EDSY SLEF build and keep named local ship favourites.
- Ship-specific Spansh exact routing, neutron boost enabled by default.
- Ordered editable waypoints, cargo, fuel reserve, injection and routing options.
- Normal/neutron full-tank range preview; sortable results, copying and CSV export.
- English / 中文, system/light/dark theme, Windows system-DPI awareness.
- Independent saved settings and explicit import of old favourites.

Each leg assumes a full main tank. **Fuel continuity and refuelling at waypoints
are not guaranteed.** Cancelling does not necessarily cancel an already submitted
server job. Incomplete exports require confirmation. See [routing details](docs/route-planner.md).

## Run / build

Python 3.11+ with tkinter; no third-party runtime packages:

```powershell
python planner.py
python scripts/run_tests.py
python planner.py --smoke-test smoke.json
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean EliteDangerousNeutronPlanner.spec
```

The EXE is `dist/EliteDangerousNeutronPlanner.exe`.

## Settings and old favourites

Settings/favourites/cache use `%LOCALAPPDATA%\EliteDangerousNeutronPlanner` on Windows,
separate from `%LOCALAPPDATA%\EliteDangerousFilter`. Override only with
`ELITE_NEUTRON_DATA_DIR` (use an isolated directory for testing).

Click **Import legacy ship favourites**, then select `route_ship_favorites.json`
from the old filter's data directory (source runs: its `data/` folder). The old
file is not changed or deleted. Conflicting names abort without overwriting.
Old module caches are not moved; they are fetched again when needed.

Planning sends the selected build and waypoints to Spansh. Avoid private fields
you do not want to transmit. Previewing a ship does not submit a route job.

## License

GPL-3.0-only. [Origin, attribution and third-party data boundaries](NOTICE.md).

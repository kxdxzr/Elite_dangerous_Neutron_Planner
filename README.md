# Elite Dangerous Neutron Planner

[English](README.md) · [简体中文](README_zh-CN.md)

A small Windows desktop tool for Elite Dangerous players: keep favourite ship builds and destinations, arrange waypoints, and use Spansh to plan a neutron-assisted route for your ship.

**This is only a small desktop extension of [Spansh's existing ship-specific route planner](https://spansh.co.uk/exact-plotter). At its core, it still uses Spansh's planning service, not a separately developed planning algorithm.** Spansh performs the actual route calculations and deserves credit for the core planning capability. If you do not need local favourites or a desktop interface, you can simply use the Spansh website.

This is not an official Frontier or Spansh product. The current version is **0.1.0-beta.1 (Beta)** and may contain bugs. Check your route and fuel situation in-game.

## What you can do

- **Keep favourite builds:** import Coriolis JSON or EDSY SLEF and give each build a name.
- **Save destinations:** keep frequently visited systems and reuse them as your destination; rename or delete favourites.
- **Plan through waypoints:** visit specified systems in order and rearrange stops.
- **Adjust planning options:** neutron boost is enabled by default; configure cargo, fuel reserve, injection, algorithm and other options.
- **Use the results:** preview normal/neutron full-tank jump ranges, copy result system names or export a CSV.
- **Make it comfortable:** switch between English and Chinese, choose system/light/dark themes, and restore settings and favourites after restarting.

## Download and launch

There is no published Release package yet. Windows test builds are available on the [Actions build page](https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/actions/workflows/ci.yml):

1. Sign in to GitHub and open the latest successful build.
2. Under **Artifacts** at the bottom of the page, download `EliteDangerousNeutronPlanner-Windows`.
3. Extract the archive and run `EliteDangerousNeutronPlanner.exe`. Python is not required.

The first ship-attribute calculation needs an internet connection to fetch module data. Route planning requires a connection to Spansh.

## Plan your first route

1. Click **Add ship build**, enter a favourite name, then paste your build JSON or click **Import JSON file**. **You need the build data, not a Coriolis/EDSY webpage link.**
2. Save and select the build. Check its displayed ship model and full-tank jump ranges.
3. Enter your source and destination systems. Add and reorder waypoints if needed.
4. Set cargo, fuel reserve and other options to match your trip, then click **Plan route**.
5. Review the results, copy system names or export a CSV as needed.

### Save a frequently visited destination

Enter a destination system, click **Save current destination**, and give it a name. Next time, select it under **Destination favourites** and click **Use as destination**.

Favourites persist across restarts, and duplicate names never overwrite existing entries. Saving does not validate a system online or start planning; systems are resolved when you plan a route.

## Before you depart

- **Every leg assumes a full main fuel tank at departure.** With waypoints, the next leg does not inherit the previous leg's arrival fuel. **Refuelling at waypoints is not guaranteed.** Check refuelling opportunities yourself.
- Range previews are theoretical full-tank values. They do not mean neutron boosting is available at your location or guarantee a feasible route.
- **Stop** ends local waiting and further leg submissions, but does not necessarily cancel jobs already received by Spansh.
- If planning fails or stops, only verified complete legs are retained. Exporting partial results requires confirmation; do not treat them as a complete route.

See [routing details](docs/route-planner.md) for more information.

## Data and privacy

Settings and favourites are saved locally in `%LOCALAPPDATA%\EliteDangerousNeutronPlanner`. Saving a destination or ship build does not submit a route job.

**Planning sends the selected build and waypoints to Spansh.** Remove private fields you do not want to transmit. Ship previews fetch module data but do not submit a route job.

### Import ship favourites from the old filter

If you used the planner in [Elite Dangerous Filter](https://github.com/kxdxzr/Elite_dangerous_Filter), click **Import legacy ship favourites** and manually select `route_ship_favorites.json` from its old data directory. This is usually `%LOCALAPPDATA%\EliteDangerousFilter`; older source versions may use a `data` folder inside that project.

Importing does not change or delete the old file. Conflicting names abort the import without overwriting. This tool stores its data separately from the old filter.

## Feedback

Report bugs or suggestions through [Issues](https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/issues). Include your version, steps to reproduce and any error message. Redact private builds and other information you do not want to publish from screenshots or attachments.

## Source and license

Extracted from Elite Dangerous Filter and licensed under GPL-3.0-only. See [LICENSE](LICENSE) and [origin and third-party data notices](NOTICE.md).

To run from source, install Python 3.11+ with tkinter and run `python planner.py` in the project directory. No third-party Python packages are needed at runtime. Maintenance, test and build instructions are in [HANDOFF.md](HANDOFF.md); read [AGENTS.md](AGENTS.md) before contributing.

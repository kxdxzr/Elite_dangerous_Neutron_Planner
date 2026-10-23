# Elite Dangerous Neutron Planner

[English](README.md) · [简体中文](README_zh-CN.md)

A small Windows desktop tool for Elite Dangerous players: keep favourite ship builds and destinations, arrange waypoints, and use Spansh to plan a neutron-assisted route for your ship.

**This is only a small desktop extension of [Spansh's existing ship-specific route planner](https://spansh.co.uk/exact-plotter). At its core, it still uses Spansh's planning service, not a separately developed planning algorithm.** Spansh performs the actual route calculations and deserves credit for the core planning capability. If you do not need local favourites or a desktop interface, you can simply use the Spansh website.

This is not an official Frontier or Spansh product. The current version is **0.1.0-beta.1 (Beta)** and may contain bugs. Check your route and fuel situation in-game.

## What you can do

- **Keep favourite builds:** import Coriolis JSON or EDSY SLEF and give each build a name.
- **Save destinations:** keep frequently visited systems and reuse them as your destination; rename or delete favourites.
- **Plan through waypoints:** visit specified systems in order and rearrange stops.
- **Fill the source from game logs:** click **Use current system** to read the last recorded position from local Journals instead of copying a system name manually.
- **Adjust planning options:** neutron boost is enabled by default; configure cargo, fuel reserve, injection, algorithm and other options.
- **Use the results:** preview normal/neutron full-tank jump ranges, copy result system names or export a CSV.
- **Revisit recent routes:** keep the last 5 planning attempts and their parameters locally across restarts. Blue rows highlight systems Spansh marks as containing a neutron star.
- **Make it comfortable:** switch between English and Chinese, choose system/light/dark themes, and restore settings and favourites after restarting.
- **Scroll one page:** settings, planning controls and results share a single page, without split panes. The mouse wheel scrolls the page; drag the table's right-hand scrollbar for long routes and its bottom scrollbar for additional columns.

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

### Use your in-game position as the source

After entering the game, click **Use current system** to read the position from the most recently active Journal session. The record timestamp is shown alongside it.
The default folder is `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`. Use **Choose Journal folder** if yours is elsewhere; the selection is remembered after a normal exit.

This button reads once and only updates the source; it does not start planning. **There is no startup scanning or log upload. Continuous following must be enabled separately.**
Positions come from `Location`, `FSDJump` or `CarrierJump` records, never an uncompleted jump's destination.
Records may be stale after exiting the game. If accounts share a folder, the most recently active session is used; check the system and timestamp. If the latest session has no position yet, the tool reports that instead of falling back to another session.

### Follow route progress and auto-copy the next system

After planning or loading a result, enable **Follow game position** in the results area. The tool checks local Journals about every 2 seconds and normally reads only newly appended data.
When your position matches the route, its row turns green and shows the canonical route position, Journal time and planned next system. **It does not automatically scroll or change sorting**; use **Locate current row** when needed.

Enable **Auto-copy planned next system** to put the next system's plain name in the system clipboard, ready to paste in-game. It does not simulate keystrokes or switch focus.
**This replaces existing clipboard contents. Each position in the current route is auto-copied only once**, not on every Journal check.

- Outside the route, only the old position marker and following text are cleared. No copying, deviation popup, replanning or source-field changes occur.
- Nothing is copied at the destination. Incomplete routes follow only the verified portion and explicitly label its end as incomplete.
- The next system always comes from the original route order, regardless of table sorting.
- If a system occurs multiple times and its position is ambiguous, nothing is guessed or copied. Select the matching row and click **Confirm selected position**.
- Both switches default to off on every launch. Disabling following or closing the app stops reading. Reading, matching and auto-copying require no additional network requests.

This follows the last confirmed Journal position, not live in-game navigation. Check the timestamp, next system and refuelling conditions yourself. No floating overlay is provided.

### Revisit results and avoid duplicate searches

Select an entry under **Last 5 routes** and click **View saved result** to restore its parameters and results for viewing, copying or exporting without submitting another route job.
If the original build was deleted or changed, the saved result is still available, but you must select a build before planning again.

If the displayed result is complete and the build, endpoints, waypoints and planning options are unchanged, clicking **Plan route** again does nothing. Failed or stopped attempts can still be retried with the same parameters.
Incomplete history entries stay marked as incomplete and still require confirmation before export.

When searching again after changing parameters, a **complete result from the last 5 attempts, less than 24 hours old, with the exact same build and all planning parameters**, can also be reused. The status explicitly says **Saved result, not queried again** and shows its original timestamp. Incomplete results never substitute for a new plan.

To reduce preparation time, confirmed system identities are cached for the current application session, and waypoints are resolved with limited concurrency. Route legs are still calculated sequentially.
Progress distinguishes ship processing, system resolution, the Spansh queue and calculation, with stage timings shown afterward. **These optimizations cannot eliminate Spansh's own queueing or calculation time.**

## Before you depart

- **Every leg assumes a full main fuel tank at departure.** With waypoints, the next leg does not inherit the previous leg's arrival fuel. **Refuelling at waypoints is not guaranteed.** Check refuelling opportunities yourself.
- Range previews are theoretical full-tank values. They do not mean neutron boosting is available at your location or guarantee a feasible route.
- **Stop** ends local waiting and further leg submissions, but does not necessarily cancel jobs already received by Spansh.
- If planning fails or stops, only verified complete legs are retained. Exporting partial results requires confirmation; do not treat them as a complete route.

See [routing details](docs/route-planner.md) for more information.

## Data and privacy

Settings, favourites and the last 5 planning attempts are saved locally in `%LOCALAPPDATA%\EliteDangerousNeutronPlanner`. The `route_history.json` file contains waypoints, planning parameters and route results; review it before sharing it in a bug report. Saving a destination or ship build does not submit a route job.

**Planning sends the selected build and waypoints to Spansh.** Remove private fields you do not want to transmit. Ship previews fetch module data but do not submit a route job.
Journal reading itself stays local. A source filled from a Journal is sent to Spansh along with the waypoints only when you start planning.

### Import ship favourites from the old filter

If you used the planner in [Elite Dangerous Filter](https://github.com/kxdxzr/Elite_dangerous_Filter), click **Import legacy ship favourites** and manually select `route_ship_favorites.json` from its old data directory. This is usually `%LOCALAPPDATA%\EliteDangerousFilter`; older source versions may use a `data` folder inside that project.

Importing does not change or delete the old file. Conflicting names abort the import without overwriting. This tool stores its data separately from the old filter.

## Feedback

Report bugs or suggestions through [Issues](https://github.com/kxdxzr/Elite_dangerous_Neutron_Planner/issues). Include your version, steps to reproduce and any error message. Redact private builds and other information you do not want to publish from screenshots or attachments.

## Source and license

Extracted from Elite Dangerous Filter and licensed under GPL-3.0-only. See [LICENSE](LICENSE) and [origin and third-party data notices](NOTICE.md).

To run from source, install Python 3.11+ with tkinter and run `python planner.py` in the project directory. No third-party Python packages are needed at runtime. Maintenance, test and build instructions are in [HANDOFF.md](HANDOFF.md); read [AGENTS.md](AGENTS.md) before contributing.

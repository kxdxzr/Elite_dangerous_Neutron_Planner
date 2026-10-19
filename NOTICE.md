# Origin and licensing / 来源与许可

Copyright (C) 2026 kxdxzr and contributors. GPL-3.0-only; see LICENSE.

Extracted from https://github.com/kxdxzr/Elite_dangerous_Filter, base commit
`347ab87997e6eee58a33acb4460db27530214b35`, including subsequent local UI/DPI/progress fixes.
Original history and authorship remain available in that repository. This initial
snapshot is not a claim that upstream history was authored anew.

Transferred components: route_gui / route_tool / route_ship, generic theme,
localization, sorting, result formatting, progress, DPI, atomic JSON storage,
CSV provenance and related tests. suggestion_ui extracts reusable autocomplete
definitions from upstream filter_gui; it does not depend on the filter application.
No personal data, build exports, favourites or caches are included.

Spansh is an external service, not part of this code's license. Builds and waypoints
are sent to Spansh when planning. EDCD/coriolis-data facts are downloaded from a
pinned revision at runtime; its JSON data belongs to Frontier and is not MIT or
covered by this application's GPL. No module catalogue is bundled. Do not infer
third-party data reuse rights from this code license.

本项目从原筛选器拆分，保留作者与 GPL-3.0-only 许可，并注明上游提交与后续本地修复。
不包含私人配船、收藏、缓存。Spansh 服务及 Frontier 模组数据不因本项目 GPL 许可而获得额外授权。

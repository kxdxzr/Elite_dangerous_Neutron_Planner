# Routing boundaries / 规划边界

The standalone planner retains ship-specific exact routing, local favourites,
normal/neutron range previews and ordered multi-leg planning from the filter.
It has independent settings, version and CSV provenance. Rare-goods filtering
and system/station searching are not part of this application.

- Each leg starts with a full main tank, independently of the previous leg.
- Shared endpoints keep arrival and next-leg departure fuel/actions separate.
- Refuelling at waypoints, transfer time and actual flight safety are not verified.
- Only completed validated legs survive errors/stops; partial export requires confirmation.
- Build/waypoint data are submitted to Spansh; ship-preview facts are fetched separately.
- Third-party protocols can change. Unsupported builds fail rather than guess physics.
- Optional legacy-favourites import copies validated entries without deleting originals.

For the original engineering formulas, parsing limits and historical validation,
see the clearly labelled [upstream archive](upstream-route-planner.md).

本项目仅迁出中子规划器，不包含稀有商品或站点／星系筛选。每段独立满油，不保证补油、
跨段燃油连续或实际安全。停止／错误仅保留已验证完整分段，部分导出需确认；航点及配船
会提交给 Spansh，预览不提交路线。旧收藏手动复制导入，不修改原文件。

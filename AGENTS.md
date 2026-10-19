# Maintenance instructions

- Start with `HANDOFF.md`, then check `git status --short --branch` before editing.
- This is the standalone neutron planner. Do not import from or edit the sibling
  `Elite_dangerous_Filter` repository to make this application work. That repository
  has unrelated, unpublished local work; never reset, clean or commit it here.
- Preserve GPL-3.0-only, upstream attribution and third-party-data notices.
- Use `python scripts/run_tests.py` for isolated tests. Run the offline smoke test
  with `python planner.py --smoke-test <report.json>` after GUI/bootstrap changes.
- Never use a private ship build for a live network test without explicit approval.
  Planning transmits builds and waypoints to Spansh. Offline smoke must stay offline.
- Keep UI work on the Tk main thread. Preserve English/Chinese switching, themes,
  system DPI awareness, sortable result headers and unsortable ordered waypoints.
- Do not weaken full-tank-per-leg warnings, partial-export confirmation, strict
  ship parsing or cancellation/endpoint validation to make tests pass.
- Do not automatically move/delete old filter favourites or overwrite name conflicts.
- Keep both READMEs in sync. Do not publish a Release or replace an asset merely
  because tests/builds passed; obtain release authorization first.

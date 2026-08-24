# Plan: Finish the toggle-list → setting-row migration across System Hub leaves

## Goal
Cursor's Pulse rewrite (`ef026cd1`…`3ea9597b`) already replaced the flat page list
with a 5-destination rail (`PULSE_RAIL`) and sectioned hub chrome
(`SectionedHubPage`). A follow-up pass (`e63fa83c "hub updates"`) built the
Windows-Settings-style row primitive — `ToggleSwitch` (animated pill switch)
+ `widgets/cards.py::_make_setting_row` (label/subtitle + trailing control) —
and used it in exactly one place (`page_performance_cards_clean.py`'s
read-only badge rows). Everywhere else still hand-rolls a bare `QCheckBox` in
a `QHBoxLayout`. This plan finishes propagating the row idiom into every
remaining page so "list of toggles" stops being true anywhere in the Hub.

## Success Criteria
- No page module under `src/kyth-welcome/kyth_welcome/` constructs a raw
  `QCheckBox()` for a user-facing on/off setting outside `widgets/toggle.py`
  itself (`ToggleSwitch` subclasses `QCheckBox`, so the base class stays).
- Every on/off setting row uses `_make_setting_row(title, subtitle, ToggleSwitch(...))`
  inside a `_make_card(...)`, matching the shape already validated in
  `page_performance_cards_clean.py` and `theme_base/_inputs.py` styling
  (`QFrame#setting-row`, `QLabel#setting-row-title/subtitle`).
- `page_performance.py`'s two pre-existing `ToggleSwitch` rows (auto-switch,
  AI tuning) are re-homed onto `_make_setting_row` too, so the one page that
  started this pattern is internally consistent, not just the newest page.
- `just test`, `just validate`, and the `.githooks/pre-push` headless
  `MainWindow` smoke test all still pass after the change.

## Context And Current Facts
- Local `testing` was 93 commits behind `origin/testing` at task start
  (branched before `ef026cd1`); rebased clean (single commit, `bab4cc69` merge
  base) — done as of this plan.
- Diagnostic (`git grep QCheckBox` minus `widgets/toggle.py`) found raw
  checkboxes in: `page_feedback.py`, `page_gaming_tools_perf.py`,
  `page_guardian.py`, `page_network_shares.py`, `page_software_starter.py`,
  `page_update_auto.py`, `page_windows_migration/files_copy.py`,
  `page_windows_migration/shortcuts_phone.py`, `page_work/_focus.py`,
  `wizard/steps_apps.py`. (`page_repair.py` and
  `page_windows_migration/__init__.py` only reference `QCheckBox` as a type
  hint / import, no instances — leave alone.)
- `ToggleSwitch` (`widgets/toggle.py`) is a drop-in `QCheckBox` subclass — same
  `setChecked/isChecked/toggled` API — so swapping the widget class doesn't
  change any signal wiring, only construction + layout.
- `optimization-budgets.json: system_hub_python_modules = 235`. This pass adds
  no new modules (edits existing page files only), so no budget risk.

## Constraints And Non-goals
- Don't touch `PULSE_RAIL`, `SectionedHubPage`, `theme_base/_pulse.py`, or
  `windows.py` chrome — that layer is done and accepted; this pass is leaves
  only.
- Don't eagerly construct child pages — `lazy_page.compose_on_first_init`
  stays untouched; row-level edits happen inside each page's existing
  `compose`/`__init__`, not at Hub construction time.
- Non-goal: wizard flow redesign. `wizard/steps_apps.py` gets its one
  checkbox converted for visual consistency but the wizard's own flow/step
  structure is out of scope.
- Some checkboxes are inside a list of *many* dynamically generated rows
  (`page_work/_focus.py` has 5, `page_windows_migration` file-pick lists) —
  keep those as loops emitting `_make_setting_row`, don't hand-expand.

## Key Decisions
| Decision | Recommendation | Why |
|---|---|---|
| Convert in place vs. new widget | Convert in place: swap `QCheckBox(...)` → `ToggleSwitch(...)`, wrap existing label text in `_make_setting_row` | Same API, existing `.toggled.connect(...)` wiring keeps working — no logic changes, review stays small |
| Card wrapper | Keep each page's existing `_make_card` sections; only touch the row construction inside | Matches "extend don't restart" — page-level layout is fine, only the row primitive is stale |
| page_performance.py toggles | Re-home onto `_make_setting_row` in this pass, not deferred | It's the file that *proves* the idiom; leaving it inconsistent undercuts the "true modern control center" pitch |

## Work Plan
### Phase 1 — Convert the 10 files
- **Files:** the 10 listed above.
- **Steps (per file):** find each `QCheckBox(...)` construction, replace with
  `ToggleSwitch(...)`, move its adjacent label text into
  `_make_setting_row(title, subtitle_or_"", toggle)`, drop the now-redundant
  hand-built `QHBoxLayout`/`QLabel` if `_make_setting_row` fully replaces it.
  Re-run `git grep QCheckBox` after each file to confirm no leftover direct
  instantiation.
- **Deps:** none.

### Phase 2 — page_performance.py consistency pass
- Re-home `_perf_auto_toggle` and `_ai_toggle` rows onto `_make_setting_row`.

### Phase 3 — Validation
- `just test` (or targeted `PYTHONPATH=... python3 -m unittest tests.test_kyth_ui_construction tests.test_kyth_welcome_hub_smoke tests.test_kyth_lazy_page tests.test_kyth_page_registry -v`)
- `.githooks/pre-push` headless smoke (`QT_QPA_PLATFORM=offscreen`) run directly.
- `just validate` before commit.

## Validation Plan
- Unit: full `just test` green.
- Manual: not required for this pass (no behavior change, pure widget swap) —
  rely on the offscreen smoke test + existing page construction tests.

## Risks / Rollback
- **Risk:** a page's checkbox sits in a layout `_make_setting_row` doesn't
  fit (e.g. inline with other controls, not a simple label+control pair).
  **Mitigation:** where the row shape doesn't fit cleanly, leave the
  `QCheckBox` → `ToggleSwitch` swap (still gets the modern visual) without
  forcing `_make_setting_row`; note it in the commit body.
- **Rollback:** single-file revert per page; no cross-file coupling.

## Open Questions
- Whether `page_welcome_grid.py` / `page_welcome_hero.py` / `page_welcome_hud.py`
  (pre-Pulse home page remnants, still present after the rebase) should be
  deleted now that `page_welcome.py` owns the Home destination, or kept as
  dead code intentionally for reference. Not touched in this pass — flagging
  for the user.

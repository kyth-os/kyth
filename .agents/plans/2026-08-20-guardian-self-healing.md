# Plan: Kyth Guardian — Own Menu Item & Self-Healing Differentiator

## Goal
Promote Kyth Guardian from a small card inside Repair (`src/kyth-welcome/kyth_welcome/page_repair.py:265`) to its own top-level System Hub menu item and build it into an extremely useful, always-on self-healing surface — the Kyth differentiator. It should be the first place a user looks when "something feels off," and the place Kyth fixes itself quietly in the background.

## Success Criteria
- System Hub sidebar has a dedicated **Guardian** entry (visible without scrolling, own icon/section), deep-linkable via `--page Guardian` and search (`Ctrl+K` / `Ctrl+F`).
- Guardian page renders a live dashboard: current health, suppression reason, last check timestamp, auto-fix toggle, model status/install, history timeline (last 100 / 30d already persisted in `kyth_shared/guardian.py:30-31,526-541`), and one-click `Investigate`, `History`, `Repair` actions — all driven by the existing bounded CLI (`kyth-guardian` / `kyth_shared.guardian`).
- Existing Repair page no longer owns Guardian controls (de-duped; Repair keeps rollback/reset/recovery).
- Expanded self-healing actually fixes more real desktop pain with the same safety boundary (`docs/guardian.md` allowlisted recipes, redact, cooldown, 2-consecutive-failure + low-confidence gates).
- No new daemon: still timer (`kyth-guardian.timer` 15m) + path trigger on probe cache (`kyth-guardian.path`) + `Nice=10`/`IOSchedulingClass=idle` (`build_files/kyth-guardian.service:10-11`), oneshot model inference (30s, 256 tokens, locked).
- Existing tests still green: `tests/test_kyth_guardian.py` (policy, history, suppression, model install) and `tests/test_kyth_system_service_hardening.py:56`.

## Context And Current Facts
- **Current Guardian code** — `build_files/kyth_shared/kyth_shared/guardian.py` (604 LOC):
  - 7 recipes in `RECIPES` (`audio.restart`, `network.restart-user`, `flatpak.refresh-metadata`, `flatpak.repair-user`, `bluetooth.restart`, `disk.review`, `update.review-health`) with `risk`/`requires_auth`/`automatic`/`cooldown`/`verification` fields. Only 3 are `safe+automatic` (`audio.restart`, `network.restart-user`, `flatpak.refresh-metadata`); `disk.review`/`update.review-health` are advisory (empty command); `bluetooth.restart` needs auth.
  - `collect_symptoms()` probes: pipewire/wireplumber `systemctl --user is-active`, `nmcli` state, `bluetooth.service`, `flatpak list`, disk usage (`/`, `~`), boot health (`kyth_shared.boot_health.read_state()`). Deterministic decisions only when `len(recipes)==1`; otherwise defers to local LLM.
  - Local LLM is fully bounded: optional `llama-cli`, manifest-pinned (`/usr/share/kyth/guardian-model.json`), CPU-only, JSON-schema constrained, 2h cache (`infer()` 3600s suppression), `parse_model_decision()` rejects any non-allowlisted `recipe_id`, extra keys, non-https model URL, unknown probe, `confidence < 0.65`.
  - `can_execute()` gate: `automatic_safe_fixes` must be on, `risk==safe`, no auth, `automatic==True`, `occurrences[component] >= 2`, cooldown elapsed. `suppression_reason()` skips gaming/capture, foreground updates, critical battery, memory/thermal pressure. `_notify()` via `notify-send` throttled 6h.
  - Persistence under `XDG_STATE_HOME/kyth/guardian.json` + `XDG_CONFIG_HOME/kyth/guardian.json`, history bounded `MAX_HISTORY=100`, `MAX_HISTORY_AGE=30d`, atomic writes.

- **Current UI** — `src/kyth-welcome/kyth_welcome/page_repair.py:265 _build_guardian_card()`:
  - Single `card-accent-ok` with two checkboxes (enabled, auto-fix), three buttons (Investigate, Download/Remove model, Show history), and a one-line model summary. All buttons shell out to `/usr/bin/kyth-guardian`. Card is last among ~10 cards on Repair (after rollback timeline, quick fixes) — easy to miss.

- **Navigation** — `src/kyth-welcome/kyth_welcome/page_registry.py:169 get_nav_groups()` builds the sidebar in `src/kyth-welcome/kyth_welcome/windows.py:387`. Current groups: `None:{Home}`, `Gaming:{Gaming,Performance,Compatibility,Controllers}`, `Apps:{Discover Apps, Work Setup, Move Files}`, `System:{Updates, Hardware, Plasma & Wayland, Health Report, Repair}`, `Network & Internet:{VPN, Network Shares, Cloud Storage}`, `Advanced:{NVIDIA Drivers, Channels, Just, Feedback}`. Repair's `SEARCH_ITEMS` is "Rollback, restore, collect logs…" (`page_registry.py:134`). Guardian has no search entry, no `PROBLEM_ROUTES`.

- **Related control planes** — not yet unified:
  - `build_files/kyth_shared/kyth_shared/system/probe.py` caches 13+ sections (`bootc-*`, `flatpak-*`, `nvidia-detect`, `hardware-summary`, `network-summary`, etc.) on disk + in-process memo; `kyth-probe` warms them for Hub cold start.
  - `build_files/kyth_shared/kyth_shared/ai_assist.py` `generate_plan()` / `build_repair_plan()` is a separate deterministic repair plan (boot rollback, flatpak updates, nvidia, controller checks, latency/quirks) surfaced today only as a small AI hint in `windows.py:249 mission_bar` and `DiagnosticsPage._ai_card:69` — overlaps Guardian conceptually but isn't wired to Guardian recipes.
  - `build_files/kyth_shared/kyth_shared/boot_health.py` owns quarantine/rollback (digest-aware, `DEFAULT_FAILURE_THRESHOLD=3`) and already feeds Guardian via `update.review-health`.

- **Systemd** — `build_files/kyth-guardian.service|timer|path`, `build_files/scripts/branding/27-performance-daemons.sh:34-38` installs them as user units + enables globally in `31-ujust-recipes.sh:36-37`. Probe cache change triggers Guardian (`PathChanged=%t/kyth/probe-cache.json`).

- **Docs/tests** — `docs/guardian.md` (safety boundary, resource behavior, privacy, CLI), `tests/test_kyth_guardian.py` (policy/suppression/storage/model), `tests/test_kyth_system_service_hardening.py` (daemon limits).

## Constraints And Non-goals
- **Do not weaken the safety boundary.** Model stays outside execution, allowlist-only, no new privileged recipe without explicit product decision. Advisory recipes (`disk.review`, `update.review-health`) stay advisory unless design approves a bounded safe command.
- **Do not add a long-running daemon.** Keep timer+path oneshot, `Nice=10`, `IOSchedulingClass=idle`, `MemoryMax`/`CPUQuota` style limits already on `kyth-guardian.service`/`kyth-ai-perfd.service`.
- **Do not duplicate probe.** Reuse `kyth_shared/system/probe.py` + `ai_assist.py` evaluation rather than re-spawning `flatpak`/`bootc`/`lspci` directly in the UI thread (Hub must stay off `DataWorker`/cache for expensive calls, as Repair already does).
- **Non-goals (this plan):** cloud LLM, auto-installing packages (`dnf`/`rpm-ostree`), deleting files, drive encryption, unsupervised reboots, or changing update channel (those stay in `page_update`, `page_branches`, `boot_health`).
- **compat:** CLI `kyth-guardian --json status|check|investigate|history|enable|disable|auto-fix|model` must stay stable (tests + `ujust` recipes invoke it). Page move must keep `kyth-guardian` as the policy/execution boundary; UI only calls it.

## Key Decisions
| Decision | Recommendation | Why | Alternative rejected |
|---|---|---|---|
| Nav placement | New **Guardian** entry under `System` section, first item — section becomes `System` = `[Guardian, Updates, Hardware, Plasma & Wayland, Health Report, Repair]`. Optional follow: promote to its own top-level `Guardian` group (single-item) if signal strong. | Highest visibility without breaking user's mental model ("System" is where health lives). One code path in `get_nav_groups()`. | New top-level "Guardian" section immediately — more prominent but unfamiliar grouping for a first promotion; can graduate later without migration. Leaving inside Repair — current discoverability failure. |
| Page module | New `src/kyth-welcome/kyth_welcome/page_guardian.py` (`GuardianPage: Page`) + registry wiring (`page_registry.py:SEARCH_ITEMS`, `get_nav_groups`). Keep `page_repair.py` but delete `_build_guardian_card`+toggles (leave rollback/reset). | Isolates self-heal UI; lazy factory (`_page_factory`) keeps cold import cheap (matches every other page). | Reuse `page_repair.py` with split — keeps coupling, harder to own the surface. |
| Icon | `("shield", "security-high")` with glyph `⬢` or `🛡` — shield reads "protect/self-heal." | Ties to safety story, not overlapping existing `tools-wizard` (Repair) / `view-statistics` (Diagnostics). Falls back to glyph when icon missing (`windows.py:28`). | Reuse wrench/tools — collides with Repair. |
| Page architecture | Dashboard owns 5 sub-cards: (1) Status & controls (enabled/auto-fix, suppression banner), (2) Live Health strip (symptoms from `probe`+`boot_health` via `DataWorker`), (3) History timeline (read `guardian.load_state()`/CLI `history`), (4) Recipes catalogue (from `RECIPES` + `status().recipes`), (5) Model manager (manifest, size, `model install/remove`, inference lock). Background ops via existing `kyth-guardian --json` commands in `DataWorker`s; no direct `guardian.*` import on UI thread that shells. | Mirrors `DiagnosticsPage` pattern (`_make_card`, `DataWorker`, `guard_disposed`) users already know; keeps policy in `kyth_shared`. | Direct Python import for every check — risks blocking UI if probe or model I/O stalls; loses CLI single-source property. |
| Recipe expansion | Phase it: **P0** no new recipes (ship the page). **P1** propose 8-10 safe bounded additions (e.g., `portal.restart`, `plasma.restart`, `kwin.restart`, `sddm.review`, `flatpak.perms-review` advisory, `storage.purge-cache` safe, `network.resync-time`, `audio.resync`). Each needs allowlist review + `collect_symptoms` probe + `verify_recipe` check. | Proves the differentiator without blowing the safety review budget in one PR. | Ship 20 recipes at once — review risk, test blow-up, harder to justify each `requires_auth` vs `safe`. |
| Unification | `GuardianPage` aggregates `guardian.collect_symptoms()` + `ai_assist.build_repair_plan()` snapshot + `boot_health.read_state()` into one "self-healing plan" view, but execution stays per-`guardian.RECIPES` (no `ai_assist` command execution outside Guardian). | Users see one plan, not two hubs; keeps proven repair boundary. | Merge execution — would bypass `can_execute()` gates. |
| History UX | Timeline table (time, recipe, source, confidence, action, verified, detail) backed by `guardian.json` history (already redacted/rotated). Actions: `Re-run check`, `Investigate with Local AI` (forced infer), `Copy report`/`Save`. | Reuses existing schema, redaction, rotation (100/30d). | New store — migration pain. |

## Recommended Approach
1. **Extract & elevate.** Create `page_guardian.py` seeded from current `_build_guardian_card()` + `DiagnosticsPage` card/DataWorker patterns. Wire it in `page_registry.py` as `System` first entry. Update `SEARCH_ITEMS["Guardian"]` and `PROBLEM_ROUTES` (e.g., "guardian", "self heal", "auto repair", "fix audio", "flatpak broken").

2. **Thin Repair.** Remove Guardian card + `_toggle_*` from `page_repair.py`; leave rollback/timeline/quick fixes/assist. Add a tip card on Repair linking to Guardian ("Looking for automatic fixes? Open Guardian").

3. **Dashboard v1 (no new recipes).** Five cards as above, all data via `guardian.status()`, `guardian.check()`, `--json history`, `probe.read_section()`, `boot_health.read_state()`. Respect suppression (`guardian.suppression_reason()`), cooldown, `HUB_STATE` if available. Keep `llama-cli` path fully optional (card explains deterministic mode when not installed).

4. **Polish & differentiate.** Mission bar pill when Guardian has unresolved `recommended` items (like existing boot-health `self_heal_warn` in `page_repair.py:95`). Sidebar badge/dot when `history` has fresh `recommended` (6h throttle already exists). Link Diagnostics "AI Control Plane" card to Guardian deep-link.

5. **Phase P1 recipe expansion** (separate spec/PR after v1): propose specific new recipes with probe, risk, cooldown, verification — each gated on `trusted`/`confirm` review — and corresponding tests in `tests/test_kyth_guardian.py`.

## Work Plan

### Phase 0 — Scaffolding & Navigation (single PR, no behavior change beyond new route)
- **Files:** `src/kyth-welcome/kyth_welcome/page_registry.py`, `src/kyth-welcome/kyth_welcome/page_guardian.py` (new), `src/kyth-welcome/kyth_welcome/windows.py` (no change expected beyond registry, but verify `_refresh_nvidia_nav_visibility` pattern if needed for future badge).
- **Steps:**
  1. Add `SEARCH_ITEMS["Guardian"] = SearchItem("Guardian", "Self-healing: automatic health checks, safe fixes, history, and optional local AI diagnosis.", ("Guardian","Self heal","Auto repair","Fix automatically","Health check","Supervisor","AI repair"))` and `PROBLEM_ROUTES` entries.
  2. Insert Guardian nav item as first entry of `System` group: `(("shield","security-high"), "⬢", "Guardian", "Guardian", _page_factory("page_guardian","GuardianPage"))`. Update `descriptors_from_nav_groups` coverage.
  3. Create `page_guardian.py` stub `GuardianPage(Page)` rendering a placeholder card + lazy probe of `guardian.status()` so navigation smoke works.
- **Deps:** none. **Owner surface:** Hub navigation.

### Phase 1 — Dashboard v1 (main PR)
- **Files:** `page_guardian.py`, `page_repair.py` (trim), `page_diagnostics/__init__.py` (optional deep-link hint), `docs/guardian.md` (update menu path), `tests/test_kyth_guardian.py` (navigation smoke if needed, no policy change).
- **Steps:**
  1. **Status & Controls card:** checkboxes `Monitoring enabled` / `Automatically apply safe fixes` wired to `kyth-guardian enable/disable` + `auto-fix on/off` via `DataWorker`/`_run_quick_fix` pattern (copied from `page_repair.py:349-358`). Show `suppression_reason()` banner ("Paused: gaming / battery / update …") and `last_check` timestamp.
  2. **Live Health strip:** async gather `guardian.collect_symptoms()` + `probe` summaries + `boot_health.read_state()` in `DataWorker`; render symptom chips + deterministic decision badges. "Run Check" (`--json check`) and "Investigate with Local AI" (`--json investigate`, `force=True`) buttons. All output redacted.
  3. **History timeline:** load via `kyth-guardian --json history` (or `load_state()`), render sorted table, rotate notice (100 / 30d), copy/save (reuse `DiagnosticsPage` copy pattern). Throttle notify assessed but not mutated.
  4. **Recipes catalogue:** render `status().recipes` (id, title, risk, requires_auth) with per-recipe tooltip explaining risk level and `recovery` text from `RECIPES[recipe].recovery`.
  5. **Model manager:** show `model_status()` (id, license, size, installed path), buttons `Download`/`Remove` (`model install/remove`), note `llama-cpp` CPU-only, manifest pinning, and inference-only-when-ambiguous contract.
  6. **Repair slimming:** delete `_build_guardian_card`/`_guardian_*` fields from `RepairPage`; add `_build_guardian_link_card()` tip linking to Guardian.
  7. **Search/palette wiring:** ensure `windows.py:_rank_search_results` finds "guardian" + problem phrases; `kyth-welcome --page Guardian` deep-link works (`app.py:88`).
- **Deps:** Phase 0.

### Phase 2 — Self-Healing Polish (follow-up, no new recipes)
- **Files:** `page_guardian.py`, `windows.py` (mission bar), `widgets` theme if needed, `tests/test_kyth_guardian.py`.
- **Steps:**
  1. Mission bar pill / sidebar dot when `status.history` contains fresh `recommended` (reuse 6h throttle semantics from `_notify`).
  2. Diagnostics AI card deep-link button → Guardian.
  3. Redaction preview (debug) / privacy copy alignment with `docs/guardian.md:37-44`.
- **Deps:** Phase 1.

### Phase 3 — Recipe Expansion (separate spec per batch, gated)
- **Files:** `build_files/kyth_shared/kyth_shared/guardian.py`, `tests/test_kyth_guardian.py`, `docs/guardian.md`, possibly `build_files/kyth_shared/kyth_shared/system/probe.py` for new probe sections.
- **Steps:**
  1. Propose batch (e.g., `portal.restart`, `plasma.restart --user`, `audio.resync`, `storage.purge-cache`) with allowlist review, `collect_symptoms` probe, `verify_recipe` check, risk/cooldown assignment.
  2. Add coverage: `can_execute` transitions, `redact` edge cases, `suppression_reason` for new trigger.
  3. Docs + CLI help updated.
- **Deps:** Phase 1 complete; requires product approval per recipe (auth vs safe).

## Validation Plan
- **Unit:** `python -m pytest tests/test_kyth_guardian.py -v` (policy: allowlist, confidence, malformed, auth gate, 2-failure+cooldown, redact, history rotation, model install HTTPS/digest, suppression).
- **Full suite:** `python -m pytest tests/ -k "guardian or system_service_hardening or diagnostics"` — ensures hardening still sees `kyth-guardian.service` limits.
- **Static:** `rg "get_nav_groups"`, `rg "SEARCH_ITEMS"` — confirm no duplicate key, factory import resolves (`import_module` happy).
- **Manual Hub (primary):** `python -m kyth_welcome.app --page Guardian` or `python -m kyth_welcome` → sidebar shows Guardian under System as first entry, icon renders, `Ctrl+K` "guardian"/"self heal"/"fix audio" ranks Guardian top, clicking navigates and deep-link survives restart. Cards populate without blocking UI (verify via `DataWorker` — no hang on cold probe). Check toggles persist to `~/.config/kyth/guardian.json` + reflect after re-open. Investigate/history buttons stream `kyth-guardian --json` output.
- **Service sanity:** `systemctl --user status kyth-guardian.{service,timer,path}` shows enabled/oneshot, no continuous CPU; `journalctl --user -u kyth-guardian.service --since -1h` shows only timer/path invocations. Verify `nice`/`IOSchedulingClass` still idle.
- **Redaction:** Trigger a notional history with secrets/IP/MAC/home in evidence; confirm `history` JSON shows `<redacted>`, `<address>`, `<mac>`, `<home>`, `<path>`.
- **Phase 3 extras:** For each new recipe, manual repro of symptom (e.g., stop `pipewire`/`wireplumber`, disconnect NM) → Guardian `check` yields correct deterministic `Decision`, `can_execute` gate holds until 2 occurrences + cooldown, `execute_recipe` + `verify_recipe` succeed, notification throttled.

## Risks / Rollback
- **Sidebar collision:** Adding to `System` first position shifts indices — `windows.py:_page_index_by_key` and `_switch_page(0)` assume spec order. Mitigate: never rely on hard indices after Phase 0; test palette ordering. Rollback: revert `page_registry.py` one-line, Hub reverts to 5-item System.
- **Startup cost:** Guardian page import pulling heavy deps (like `page_hardware` eager `lspci`) would regress cold start. Mitigate: lazy `_page_factory` + `DataWorker` for every probe/LLM call, matching existing pattern; keep `import kyth_welcome.app` cheap (as `app.py` comments warn).
- **Policy drift:** Expanding recipes risks widening `safe+automatic` without review. Mitigate: Phase 1 ships zero new recipes; Phase 3 gated per-recipe with explicit `risk` review.
- **Model UX confusion:** Users may think model is required. Mitigate: card copy "Deterministic monitoring remains available" (existing `page_repair.py:340` language), download is opt-in.
- **Rollback:** Revert commits on `testing`; Repair still functions standalone because Guardian CLI/state files are untouched. No data migration needed.

## Open Questions
- **Placement final:** System-first vs own `Guardian` top-level group with single entry — recommend System-first for v1, graduate if telemetry shows heavy use. Choice needed before Phase 0.
- **Naming:** "Guardian" vs "Guardian — Self-Heal" vs "Self-Healing" label in sidebar/search — affects discoverability for newcomers.
- **Recipe appetite:** Which P1 recipes are actually wanted first? Candidate safe candidates vs advisory-only for disk/storage.
- **Mission bar vs notifications:** Should unresolved Guardian `recommended` surface as a persistent mission pill or only as a `notify-send`? Current `_notify()` throttles 6h; pill would be more visible.
- **History sharing:** Should Guardian expose "Copy Report" that bundles redact-safe history + `probe` snapshot for issue filing (like Diagnostics copy)?

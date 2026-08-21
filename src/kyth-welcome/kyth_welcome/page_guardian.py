"""Kyth Guardian — self-healing dashboard.

Owns the System Hub "Guardian" route (System → Guardian). All policy and
execution stays in ``kyth_shared.guardian`` / ``/usr/bin/kyth-guardian``;
this page is a dashboard that calls that boundary on background threads and
renders redacted results. Mirrors the patterns in DiagnosticsPage and
RepairPage (cards, DataWorker + guard_disposed, never blocking the GUI).
"""
from __future__ import annotations

import json
import time

from .core_base import restyle
from .services.runtime import DataWorker, guard_disposed
from .qt import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    single_shot,
)
from .widgets import Page, _make_card, _make_tip_card

# ---------------------------------------------------------------------------
# helpers — run on background threads (DataWorker) so Hub never blocks
# ---------------------------------------------------------------------------

def _guardian_status() -> dict:
    try:
        from kyth_shared.guardian import status as _status  # lazy: keep import cheap
        return _status()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "enabled": True, "automatic_safe_fixes": False, "model": {"installed": False}}


def _guardian_history() -> dict:
    try:
        from kyth_shared.guardian import load_state
        state = load_state()
        return {"history": state.get("history", []), "occurrences": state.get("occurrences", {}), "last_check": state.get("last_check")}
    except Exception as exc:  # noqa: BLE001
        return {"history": [], "error": str(exc)}


def _guardian_check(*, investigate: bool = False) -> dict:
    try:
        from kyth_shared.guardian import check as _check
        return _check(investigate=investigate, automatic=False)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "symptoms": [], "decisions": []}


def _guardian_fix_my_system() -> dict:
    """One-click Fix My System — runs healing chain with user consent, gaming-aware."""
    try:
        from kyth_shared.guardian import check as _check
        # User clicked explicit fix — run as if automatic but with user present; respects suppression + cooldown
        return _check(investigate=False, automatic=True)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "symptoms": [], "decisions": []}


def _guardian_set_enabled(enabled: bool) -> dict:
    from kyth_shared.guardian import load_config, save_config, status as _status
    cfg = load_config()
    cfg["enabled"] = bool(enabled)
    save_config(cfg)
    return _status()


def _guardian_set_autofix(enabled: bool) -> dict:
    from kyth_shared.guardian import load_config, save_config, status as _status
    cfg = load_config()
    cfg["automatic_safe_fixes"] = bool(enabled)
    save_config(cfg)
    return _status()


def _guardian_model_op(op: str) -> dict:
    try:
        if op == "remove":
            from kyth_shared.guardian import model_path, model_status
            path = model_path()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return model_status()
        if op == "install":
            from kyth_shared.guardian import install_model, model_status
            install_model()
            return model_status()
        from kyth_shared.guardian import model_status
        return model_status()
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "error": str(exc)}


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "never"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except (OSError, ValueError, TypeError):
        return str(ts)


class GuardianPage(Page):
    """Self-healing dashboard — owns the Guardian sidebar route."""

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _k: None)
        self._status_worker = None
        self._health_worker = None
        self._history_worker = None
        self._model_worker = None
        self._check_worker = None
        self._toggle_worker = None

        self._page_header(
            "System",
            "Guardian — Self-Healing",
            "Automatic health checks, bounded safe fixes, and optional on-demand local AI. "
            "Fixes run only when Kyth can verify them — nothing is installed, deleted, or rebooted without your say-so.",
        )

        self._build_status_card()
        self._build_health_card()
        self._build_dashboard_card()
        self._build_history_card()
        self._build_recipes_card()
        self._build_model_card()
        self._build_private_card()

        self._stretch()
        single_shot(self, 0, self._refresh_all)

    # -- status & controls -------------------------------------------------

    def _build_status_card(self) -> None:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Guardian status")
        title.setObjectName("card-title")
        layout.addWidget(title)

        intro = QLabel(
            "Guardian watches audio, portals, Plasma shell, network, Bluetooth, Flatpak, storage, and update health. "
            "Cheap checks run every 15 minutes and again when the system probe cache changes. "
            "The optional local model starts only when a case is ambiguous, picks one Kyth recipe, then exits."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._enabled_chk = QCheckBox("Monitoring enabled")
        self._enabled_chk.setToolTip("When off, periodic checks are skipped. Manual checks still work.")
        self._enabled_chk.toggled.connect(self._on_toggle_enabled)
        controls.addWidget(self._enabled_chk)

        self._autofix_chk = QCheckBox("Automatically apply safe fixes")
        self._autofix_chk.setToolTip(
            "Only fixed, reversible, unprivileged recipes can run automatically. "
            "Administrator and data-affecting actions always need confirmation."
        )
        self._autofix_chk.toggled.connect(self._on_toggle_autofix)
        controls.addWidget(self._autofix_chk)
        controls.addStretch()
        layout.addLayout(controls)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._check_btn = QPushButton("Run Check")
        self._check_btn.setToolTip("Run a fresh health scan and show what Guardian would do.")
        self._check_btn.clicked.connect(lambda _=False: self._run_check(investigate=False))
        btns.addWidget(self._check_btn)

        self._investigate_btn = QPushButton("Investigate with Local AI")
        self._investigate_btn.setObjectName("primary")
        self._investigate_btn.setToolTip("Forces the local model to choose a recipe when one is installed.")
        self._investigate_btn.clicked.connect(lambda _=False: self._run_check(investigate=True))
        btns.addWidget(self._investigate_btn)

        self._history_btn = QPushButton("Refresh History")
        self._history_btn.clicked.connect(lambda _=False: self._refresh_history())
        btns.addWidget(self._history_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._status_lbl = QLabel("Loading Guardian status…")
        self._status_lbl.setObjectName("card-copy")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        self._suppression_lbl = QLabel("")
        self._suppression_lbl.setObjectName("status-warn")
        self._suppression_lbl.setWordWrap(True)
        self._suppression_lbl.hide()
        layout.addWidget(self._suppression_lbl)

        self._add(card)

    # -- live health --------------------------------------------------------

    def _build_health_card(self) -> None:
        card, layout = _make_card()
        title = QLabel("Live health")
        title.setObjectName("card-title")
        layout.addWidget(title)

        hint = QLabel("Symptoms are gathered from the same checks that feed the background timer. Nothing here blocks the desktop.")
        hint.setObjectName("card-copy")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._health_lbl = QLabel("Waiting for status…")
        self._health_lbl.setObjectName("card-copy")
        self._health_lbl.setWordWrap(True)
        layout.addWidget(self._health_lbl)

        self._decisions_lbl = QLabel("")
        self._decisions_lbl.setObjectName("card-copy")
        self._decisions_lbl.setWordWrap(True)
        self._decisions_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._decisions_lbl)

        # One-click healing with same gated runner as Starter Packs
        fix_row = QHBoxLayout()
        fix_row.setSpacing(8)
        self._fix_btn = QPushButton("Fix My System — run safe repairs now")
        self._fix_btn.setObjectName("primary")
        self._fix_btn.setToolTip("Runs Guardian healing chain (storage.maint→firmware, display/controller, audio/network) with cooldown + gaming suppression. Same 30s bounded runner as Starter Packs.")
        self._fix_btn.clicked.connect(self._run_fix_my_system)
        fix_row.addWidget(self._fix_btn)
        self._fix_status = QLabel("")
        self._fix_status.setObjectName("card-copy")
        self._fix_status.setWordWrap(True)
        fix_row.addWidget(self._fix_status, 1)
        layout.addLayout(fix_row)

        self._add(card)

    # -- health dashboard --------------------------------------------------

    def _build_dashboard_card(self) -> None:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Health dashboard — super-app at a glance")
        title.setObjectName("card-title")
        layout.addWidget(title)
        intro = QLabel(
            "All Guardian healing plus StarTER packs, Installed, and updates live in this one System Hub — no store hop. "
            "This dashboard surfaces what auto-healed, what needs you, and when gaming/battery paused it."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._dash_health = QLabel("Loading dashboard…")
        self._dash_health.setObjectName("card-copy")
        self._dash_health.setWordWrap(True)
        self._dash_health.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._dash_health)
        self._dash_chain = QLabel("")
        self._dash_chain.setObjectName("card-copy")
        self._dash_chain.setWordWrap(True)
        self._dash_chain.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._dash_chain)
        row = QHBoxLayout()
        row.setSpacing(8)
        hub_btn = QPushButton("Open Software → Starter Packs")
        hub_btn.setToolTip("Opt-in apps and starter packs — all in this same Hub")
        hub_btn.clicked.connect(lambda _=False: self._navigate("App Store"))
        row.addWidget(hub_btn)
        upd_btn = QPushButton("Open System → Updates")
        upd_btn.clicked.connect(lambda _=False: self._navigate("Update"))
        row.addWidget(upd_btn)
        row.addStretch()
        layout.addLayout(row)
        self._add(card)

    # -- history -----------------------------------------------------------

    def _build_history_card(self) -> None:
        card, layout = _make_card()
        title = QLabel("History — last 100 checks (30 days)")
        title.setObjectName("card-title")
        layout.addWidget(title)

        desc = QLabel("Every action is recorded redacted — no passwords, tokens, SSIDs, addresses, or filenames — then rotated automatically.")
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._history_summary = QLabel("No history yet.")
        self._history_summary.setObjectName("card-copy")
        self._history_summary.setWordWrap(True)
        layout.addWidget(self._history_summary)

        self._history_view = QTextEdit()
        self._history_view.setReadOnly(True)
        self._history_view.setMinimumHeight(180)
        self._history_view.setPlaceholderText("History will appear here as JSON — copy, save, or clear from the buttons below.")
        layout.addWidget(self._history_view)

        row = QHBoxLayout()
        row.setSpacing(8)
        copy_btn = QPushButton("Copy History")
        copy_btn.clicked.connect(self._copy_history)
        row.addWidget(copy_btn)
        clear_btn = QPushButton("Clear display")
        clear_btn.clicked.connect(lambda _=False: self._history_view.clear())
        row.addWidget(clear_btn)
        row.addStretch()
        layout.addLayout(row)

        self._add(card)

    # -- recipes -----------------------------------------------------------

    def _build_recipes_card(self) -> None:
        card, layout = _make_card()
        title = QLabel("Repair recipes — what Guardian is allowed to do")
        title.setObjectName("card-title")
        layout.addWidget(title)

        body = QLabel(
            "Every fix is an allowlisted recipe. The model can only pick an ID — it cannot add a command, change arguments, "
            "install software, delete files, or reboot. Advisory recipes only point to the right System Hub page."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        self._recipes_lbl = QLabel("Loading recipes…")
        self._recipes_lbl.setObjectName("card-copy")
        self._recipes_lbl.setWordWrap(True)
        self._recipes_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._recipes_lbl)

        self._add(card)

    # -- model -------------------------------------------------------------

    def _build_model_card(self) -> None:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Local AI — optional, on-demand")
        title.setObjectName("card-title")
        layout.addWidget(title)

        body = QLabel(
            "The small Q4 model (~1.04 GiB, Apache-2.0) is verified by size + SHA-256 before use, runs CPU-only with a 256-token limit, "
            "and times out after 30 seconds. Deterministic checks work without it; it only helps when a diagnosis is ambiguous."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._model_install_btn = QPushButton("Download Local AI Model")
        self._model_install_btn.setToolTip("Downloads the pinned model to ~/.local/share/kyth/guardian — about 1 GiB.")
        self._model_install_btn.clicked.connect(lambda _=False: self._run_model_op("install"))
        row.addWidget(self._model_install_btn)

        self._model_remove_btn = QPushButton("Remove Model")
        self._model_remove_btn.clicked.connect(lambda _=False: self._run_model_op("remove"))
        row.addWidget(self._model_remove_btn)
        row.addStretch()
        layout.addLayout(row)

        self._model_lbl = QLabel("Checking model status…")
        self._model_lbl.setObjectName("card-copy")
        self._model_lbl.setWordWrap(True)
        layout.addWidget(self._model_lbl)

        self._add(card)

    # -- privacy tip + redaction demo (phase 2.3) ---------------------------

    def _build_private_card(self) -> None:
        card, layout = _make_card()
        title = QLabel("Privacy & safety boundary")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Evidence is capped at 4,096 characters and redacted before it reaches the model or history: "
            "credentials, tokens, SSIDs, IP/MAC addresses, usernames, home paths, and filenames are stripped. "
            "Prompts are not retained and nothing is uploaded. Automatic repair is limited to safe, "
            "reversible, unprivileged recipes after two consecutive failures and a cooldown."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        # Interactive redaction preview — mirrors docs/guardian.md privacy contract
        from .qt import QLineEdit  # local to keep module import light

        demo_row = QHBoxLayout()
        demo_row.setSpacing(8)
        self._redact_input = QLineEdit()
        self._redact_input.setPlaceholderText("Type a sample line (e.g. token=abc /home/alice/file.txt 10.0.0.1) to preview redaction")
        self._redact_input.setToolTip("Local preview only — demonstrates guardian.redact() without storing anything.")
        demo_row.addWidget(self._redact_input, 1)
        demo_btn = QPushButton("Preview Redaction")
        demo_btn.setToolTip("Shows how Guardian strips sensitive evidence before any model or history write.")
        demo_row.addWidget(demo_btn)
        layout.addLayout(demo_row)

        self._redact_out = QLabel("Redacted output will appear here — try pasting a log snippet above.")
        self._redact_out.setObjectName("card-copy")
        self._redact_out.setWordWrap(True)
        self._redact_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._redact_out.setStyleSheet("padding: 6px 8px; border: 1px solid palette(mid); border-radius: 6px;")
        layout.addWidget(self._redact_out)

        def _do_redact():
            raw = self._redact_input.text()
            if not raw.strip():
                self._redact_out.setText("Enter text above to see the redacted form.")
                return
            try:
                from kyth_shared.guardian import redact as _redact
                out = _redact(raw)
            except Exception as exc:  # noqa: BLE001
                out = f"redact failed: {exc}"
            # Show truncated if very long
            if len(out) > 600:
                out = out[:600] + "…"
            self._redact_out.setText(f"Raw: {raw[:400]}\nRedacted: {out}")

        demo_btn.clicked.connect(_do_redact)
        self._redact_input.returnPressed.connect(_do_redact)

        # Help link row
        help_row = QHBoxLayout()
        help_row.setSpacing(8)
        help_btn = QPushButton("Learn more")
        help_btn.clicked.connect(lambda _=False: self._navigate("Diagnostics"))
        help_row.addWidget(help_btn)
        help_row.addStretch()
        layout.addLayout(help_row)

        self._add(card)

    # -- data wiring -------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_status()
        self._refresh_history()

    def _refresh_status(self) -> None:
        if self._status_worker is not None:
            return
        self._status_worker = DataWorker("guardian-status", _guardian_status)
        self._status_worker.result.connect(guard_disposed(self._on_status_ready))
        self._status_worker.failed.connect(guard_disposed(lambda _k, m: self._on_status_ready(_k, {"error": m})))
        self._status_worker.finished.connect(lambda: setattr(self, "_status_worker", None))
        self._status_worker.finished.connect(self._status_worker.deleteLater)
        self._status_worker.start()

    def _on_status_ready(self, _key: str, data: object) -> None:
        if not isinstance(data, dict):
            return
        err = data.get("error")
        if err:
            self._status_lbl.setText(f"Status unavailable: {err}")
            self._status_lbl.setObjectName("status-err")
            restyle(self._status_lbl)
            return

        enabled = bool(data.get("enabled", True))
        autofix = bool(data.get("automatic_safe_fixes", False))
        last = _fmt_ts(data.get("last_check"))
        hist_n = data.get("history_count", "?")
        model = data.get("model", {})
        recipes = data.get("recipes", [])

        # block signals while syncing so toggles don't re-trigger save
        try:
            self._enabled_chk.blockSignals(True)
            self._enabled_chk.setChecked(enabled)
        finally:
            self._enabled_chk.blockSignals(False)
        try:
            self._autofix_chk.blockSignals(True)
            self._autofix_chk.setChecked(autofix)
        finally:
            self._autofix_chk.blockSignals(False)

        self._status_lbl.setText(
            f"Monitoring: {'on' if enabled else 'off'}  ·  Auto-fix: {'on' if autofix else 'off'}  ·  "
            f"Last check: {last}  ·  History: {hist_n} records"
        )
        self._status_lbl.setObjectName("status-ok" if enabled else "card-copy")
        restyle(self._status_lbl)

        # suppression banner (from check's suppression_reason — also expose here via quick probe)
        try:
            from kyth_shared.guardian import suppression_reason
            reason = suppression_reason()
        except Exception:
            reason = ""
        if reason:
            self._suppression_lbl.setText(f"Paused — {reason} (checks resume automatically)")
            self._suppression_lbl.show()
        else:
            self._suppression_lbl.hide()
        restyle(self._suppression_lbl)

        # recipes
        if recipes:
            lines = []
            for r in recipes:
                badge = "safe/auto" if r.get("risk") == "safe" and not r.get("requires_auth") else r.get("risk", "")
                lines.append(f"• {r.get('id')} — {r.get('title')}  [{badge}]")
            self._recipes_lbl.setText("\n".join(lines))
        else:
            self._recipes_lbl.setText("No recipes reported.")

        # model
        self._apply_model_status(model)
        # also refresh live health snippet lazily after status
        self._refresh_health_preview()

    def _apply_model_status(self, model: dict) -> None:
        installed = bool(model.get("installed"))
        mid = model.get("id", "model")
        lic = model.get("license", "license unknown")
        size = model.get("size", "")
        err = model.get("error")
        if err and not installed:
            self._model_lbl.setText(f"Model unavailable — {err}")
            self._model_lbl.setObjectName("status-warn")
        elif installed:
            extra = f" · {int(size)//(1024*1024)} MiB on disk" if isinstance(size, int) else ""
            self._model_lbl.setText(f"Installed · {mid} · {lic}{extra} — loaded only when a case is ambiguous.")
            self._model_lbl.setObjectName("status-ok")
            self._model_install_btn.setText("Re-download Model")
            self._model_remove_btn.setEnabled(True)
        else:
            self._model_lbl.setText("Not installed — deterministic checks remain available. Download when you want on-device diagnosis.")
            self._model_lbl.setObjectName("card-copy")
            self._model_install_btn.setText("Download Local AI Model")
            self._model_remove_btn.setEnabled(False)
        restyle(self._model_lbl)

    def _refresh_health_preview(self) -> None:
        if self._health_worker is not None:
            return
        self._health_worker = DataWorker("guardian-preview", lambda: _guardian_check(investigate=False))
        self._health_worker.result.connect(guard_disposed(self._on_health_ready))
        self._health_worker.failed.connect(guard_disposed(lambda _k, m: self._health_lbl.setText(f"Preview failed: {m}")))
        self._health_worker.finished.connect(lambda: setattr(self, "_health_worker", None))
        self._health_worker.finished.connect(self._health_worker.deleteLater)
        self._health_worker.start()

    def _on_health_ready(self, _key: str, data: object) -> None:
        if not isinstance(data, dict):
            return
        if data.get("error"):
            self._health_lbl.setText(f"Live check failed: {data['error']}")
            return
        symptoms = data.get("symptoms", [])
        decisions = data.get("decisions", [])
        suppressed = data.get("suppression_reason", "")
        if suppressed:
            self._health_lbl.setText(f"Paused — {suppressed}")
            self._health_lbl.setObjectName("status-warn")
        elif not symptoms:
            self._health_lbl.setText("Healthy — no issues detected. Guardian stays quiet until something drifts.")
            self._health_lbl.setObjectName("status-ok")
        else:
            parts = []
            for s in symptoms if isinstance(symptoms, list) else []:
                if isinstance(s, dict):
                    parts.append(f"• {s.get('component')}: {s.get('evidence','')[:160]}  → {', '.join(s.get('recipes',()))}")
            self._health_lbl.setText("\n".join(parts) if parts else f"{len(symptoms)} symptom(s) detected.")
            self._health_lbl.setObjectName("status-warn")
        restyle(self._health_lbl)

        if isinstance(decisions, list) and decisions:
            lines = []
            for d in decisions[:5]:
                if isinstance(d, dict):
                    lines.append(f"→ {d.get('recipe_id')} [{d.get('source')}, {d.get('confidence')}] — {d.get('action')} — {d.get('detail','')[:120]}")
            self._decisions_lbl.setText("\n".join(lines))
        else:
            self._decisions_lbl.setText("No repair queued — checks will re-run on the next timer tick or when system probes change.")
        restyle(self._decisions_lbl)
        # update dashboard mirror
        try:
            self._update_dashboard_preview(data, symptoms)
        except Exception:
            pass

    def _refresh_history(self) -> None:
        if self._history_worker is not None:
            return
        self._history_worker = DataWorker("guardian-history", _guardian_history)
        self._history_worker.result.connect(guard_disposed(self._on_history_ready))
        self._history_worker.failed.connect(guard_disposed(lambda _k, m: self._history_summary.setText(f"History load failed: {m}")))
        self._history_worker.finished.connect(lambda: setattr(self, "_history_worker", None))
        self._history_worker.finished.connect(self._history_worker.deleteLater)
        self._history_worker.start()

    def _update_dashboard_preview(self, check_data: dict, symptoms: list) -> None:
        if not hasattr(self, "_dash_health"):
            return
        suppressed = check_data.get("suppression_reason", "")
        if suppressed:
            self._dash_health.setText(f"Guardian paused — {suppressed} (gaming/battery/thermal) · checks resume automatically")
            self._dash_health.setObjectName("status-warn")
        elif not symptoms:
            self._dash_health.setText("Healthy — all probes ok · Storage ok · Firmware ok · Audio/Network ok")
            self._dash_health.setObjectName("status-ok")
        else:
            comps = ", ".join(sorted({s.get("component","?") for s in symptoms if isinstance(s, dict)}))
            self._dash_health.setText(f"Needs attention: {comps} — see Live health below. Heap: Starter Packs + Opt-in apps stay in System Hub.")
            self._dash_health.setObjectName("status-warn")
        restyle(self._dash_health)
        # chain timeline from history if available
        try:
            from kyth_shared.guardian import load_state
            hist = load_state().get("history", [])
            chains = [h for h in hist if isinstance(h, dict) and "chain" in h]
            if chains:
                last = chains[-1]
                ts = _fmt_ts(last.get("timestamp"))
                chain_ids = last.get("chain", [])
                results = last.get("results", [])
                ok_n = sum(1 for r in results if r.get("verified"))
                self._dash_chain.setText(f"Last healing chain {ts}: {' → '.join(chain_ids)} · verified {ok_n}/{len(results)} · see History")
            else:
                # show last 2 single actions
                hist2 = [h for h in hist if isinstance(h, dict) and h.get("recipe_id")][-2:]
                if hist2:
                    self._dash_chain.setText("Recent: " + " · ".join(f"{h.get('recipe_id')} @ {_fmt_ts(h.get('timestamp'))}" for h in hist2))
                else:
                    self._dash_chain.setText("No healing chains yet — Guardian stays quiet until two consecutive failures + cooldown.")
            restyle(self._dash_chain)
        except Exception:
            pass

    def _on_history_ready(self, _key: str, data: object) -> None:
        if not isinstance(data, dict):
            return
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []
        last = _fmt_ts(data.get("last_check"))
        self._history_summary.setText(f"{len(history)} record(s) · last check {last} — newest last, rotated after 100 / 30 days.")
        try:
            pretty = json.dumps(history[-25:], indent=2, sort_keys=True, ensure_ascii=False) if history else "[]"
        except (OSError, ValueError, TypeError):
            pretty = str(history[-25:])
        # avoid flooding the widget on huge history
        if len(pretty) > 20000:
            pretty = pretty[-20000:]
        self._history_view.setPlainText(pretty)

    def _run_check(self, *, investigate: bool) -> None:
        if self._check_worker is not None:
            return
        label = "investigate" if investigate else "check"
        self._health_lbl.setText(f"Running {label}…")
        self._check_worker = DataWorker(f"guardian-{label}", lambda: _guardian_check(investigate=investigate))
        self._check_worker.result.connect(guard_disposed(self._on_health_ready))
        # also refresh history after a check writes it
        self._check_worker.result.connect(guard_disposed(lambda _k, _d: self._refresh_history()))
        self._check_worker.result.connect(guard_disposed(lambda _k, _d: self._refresh_status()))
        self._check_worker.failed.connect(guard_disposed(lambda _k, m: self._health_lbl.setText(f"{label} failed: {m}")))
        self._check_worker.finished.connect(lambda: setattr(self, "_check_worker", None))
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _run_model_op(self, op: str) -> None:
        if self._model_worker is not None:
            return
        self._model_lbl.setText(f"Model {op}… — this may take a minute on first download.")
        self._model_install_btn.setEnabled(False)
        self._model_remove_btn.setEnabled(False)
        self._model_worker = DataWorker(f"guardian-model-{op}", lambda: _guardian_model_op(op))
        self._model_worker.result.connect(guard_disposed(self._on_model_done))
        self._model_worker.failed.connect(guard_disposed(lambda _k, m: self._model_lbl.setText(f"Model {op} failed: {m}")))
        self._model_worker.finished.connect(lambda: setattr(self, "_model_worker", None))
        self._model_worker.finished.connect(self._model_worker.deleteLater)
        self._model_worker.start()

    def _on_model_done(self, _key: str, data: object) -> None:
        if isinstance(data, dict):
            self._apply_model_status(data)
        self._model_install_btn.setEnabled(True)
        self._model_remove_btn.setEnabled(bool(isinstance(data, dict) and data.get("installed")))
        restyle(self._model_lbl)

    def _on_toggle_enabled(self, checked: bool) -> None:
        if self._toggle_worker is not None:
            return
        self._status_lbl.setText(f"Updating monitoring → {'on' if checked else 'off'}…")
        self._toggle_worker = DataWorker("guardian-toggle-enabled", lambda: _guardian_set_enabled(checked))
        self._toggle_worker.result.connect(guard_disposed(self._on_status_ready))
        self._toggle_worker.failed.connect(guard_disposed(lambda _k, m: self._status_lbl.setText(f"Toggle failed: {m}")))
        self._toggle_worker.finished.connect(lambda: setattr(self, "_toggle_worker", None))
        self._toggle_worker.finished.connect(self._toggle_worker.deleteLater)
        self._toggle_worker.start()

    def _on_toggle_autofix(self, checked: bool) -> None:
        if self._toggle_worker is not None:
            return
        self._status_lbl.setText(f"Updating auto-fix → {'on' if checked else 'off'}…")
        self._toggle_worker = DataWorker("guardian-toggle-autofix", lambda: _guardian_set_autofix(checked))
        self._toggle_worker.result.connect(guard_disposed(self._on_status_ready))
        self._toggle_worker.failed.connect(guard_disposed(lambda _k, m: self._status_lbl.setText(f"Toggle failed: {m}")))
        self._toggle_worker.finished.connect(lambda: setattr(self, "_toggle_worker", None))
        self._toggle_worker.finished.connect(self._toggle_worker.deleteLater)
        self._toggle_worker.start()

    def _run_fix_my_system(self) -> None:
        if getattr(self, "_fix_worker", None) and self._fix_worker and self._fix_worker.isRunning():
            return
        self._fix_status.setText("Running safe repairs (30s bound per step, gaming-aware)…")
        self._fix_btn.setEnabled(False)
        from .services.runtime import DataWorker
        self._fix_worker = DataWorker("guardian-fix-my-system", _guardian_fix_my_system)
        self._fix_worker.result.connect(guard_disposed(self._on_fix_done))
        self._fix_worker.failed.connect(guard_disposed(lambda _k, m: self._on_fix_done(_k, {"error": m})))
        self._fix_worker.finished.connect(lambda: setattr(self, "_fix_worker", None))
        self._fix_worker.finished.connect(self._fix_worker.deleteLater)
        self._fix_worker.start()

    def _on_fix_done(self, _key: str, data: object) -> None:
        self._fix_btn.setEnabled(True)
        if not isinstance(data, dict):
            self._fix_status.setText("Fix finished.")
            return
        if data.get("error"):
            self._fix_status.setText(f"Fix failed: {data['error']}")
            self._fix_status.setObjectName("status-err")
        elif data.get("suppression_reason"):
            self._fix_status.setText(f"Paused — {data['suppression_reason']}; try again after gaming/battery/thermal clears.")
            self._fix_status.setObjectName("status-warn")
        else:
            decs = data.get("decisions", [])
            execd = [d for d in decs if isinstance(d, dict) and d.get("action") == "executed"]
            recmd = [d for d in decs if isinstance(d, dict) and d.get("action") == "recommended"]
            if execd:
                self._fix_status.setText(f"Fixed {len(execd)} issue(s) — {', '.join(d.get('recipe_id','') for d in execd[:3])} · History updated.")
                self._fix_status.setObjectName("status-ok")
            elif recmd:
                self._fix_status.setText(f"No auto-fix — {len(recmd)} need confirmation in Repairs: {', '.join(d.get('recipe_id','') for d in recmd[:2])}")
                self._fix_status.setObjectName("status-warn")
            else:
                self._fix_status.setText("Healthy — no repairs needed.")
                self._fix_status.setObjectName("status-ok")
        restyle(self._fix_status)
        # mirror to health + refresh history/dashboard
        try:
            self._on_health_ready(_key, data)
        except Exception:
            pass
        single_shot(self, 200, self._refresh_history)
        single_shot(self, 200, self._refresh_status)

    def _copy_history(self) -> None:
        text = self._history_view.toPlainText()
        if not text.strip():
            return
        try:
            from .qt import QApplication
            QApplication.clipboard().setText(text)
            self._history_summary.setText("History copied to clipboard.")
            restyle(self._history_summary)
        except Exception:
            pass

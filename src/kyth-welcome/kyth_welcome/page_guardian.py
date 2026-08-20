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
            "Guardian watches audio, network, Bluetooth, Flatpak, storage, and update health. "
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

    # -- privacy tip -------------------------------------------------------

    def _build_private_card(self) -> None:
        card, _ = _make_tip_card(
            "Privacy & safety boundary",
            "Evidence is capped at 4,096 characters and redacted before it reaches the model or history: "
            "credentials, tokens, SSIDs, IP/MAC addresses, usernames, home paths, and filenames are stripped. "
            "Prompts are not retained and nothing is uploaded. Automatic repair is limited to safe, "
            "reversible, unprivileged recipes after two consecutive failures and a cooldown.",
            buttons=[("Learn more", lambda _=False: self._navigate("Diagnostics"))],
        )
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

    def _refresh_history(self) -> None:
        if self._history_worker is not None:
            return
        self._history_worker = DataWorker("guardian-history", _guardian_history)
        self._history_worker.result.connect(guard_disposed(self._on_history_ready))
        self._history_worker.failed.connect(guard_disposed(lambda _k, m: self._history_summary.setText(f"History load failed: {m}")))
        self._history_worker.finished.connect(lambda: setattr(self, "_history_worker", None))
        self._history_worker.finished.connect(self._history_worker.deleteLater)
        self._history_worker.start()

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

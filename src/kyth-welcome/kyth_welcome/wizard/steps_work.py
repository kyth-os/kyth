"""Wizard mixin for the Work Ready step."""
from __future__ import annotations

from ..services.work import orchestrate_work_setup, work_ready_checks


class _WorkStepMixin:
    """Wizard mixin for N25 Work step."""

    def _make_work_step(self):
        from ..qt import QLabel, QPushButton, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(52, 40, 52, 28)
        layout.setSpacing(14)
        title = QLabel("Make ready to work — one click")
        title.setObjectName("wiz-heading")
        layout.addWidget(title)
        body = QLabel(
            "Installs Brave and LibreOffice if missing, writes Microsoft 365 "
            "shortcuts, and reports fonts / cloud / printer. Idempotent; offline "
            "leaves a note instead of pretending it applied."
        )
        body.setObjectName("wiz-subheading")
        body.setWordWrap(True)
        layout.addWidget(body)
        status = QLabel("")
        status.setObjectName("card-copy")
        status.setWordWrap(True)
        layout.addWidget(status)

        def _check():
            checks = work_ready_checks()
            msgs = []
            for label, fn in checks:
                try:
                    _ok, msg = fn()
                    msgs.append(f"{label}: {msg}")
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001
                    msgs.append(f"{label}: {exc}")
            status.setText("\n".join(msgs))

        def _apply():
            from ..services.runtime import DataWorker, guard_disposed

            apply_btn.setEnabled(False)
            status.setText("Applying work setup…")
            worker = DataWorker("wizard-work-apply", orchestrate_work_setup)
            self._work_apply_worker = worker

            def _done(_key, result):
                ok, msg = result if isinstance(result, tuple) and len(result) == 2 else (False, str(result))
                status.setText(("Ready. " if ok else "Partial. ") + str(msg))
                apply_btn.setEnabled(True)

            worker.result.connect(guard_disposed(_done))
            worker.failed.connect(guard_disposed(lambda _k, message: (
                status.setText(f"Work setup failed: {message}"),
                apply_btn.setEnabled(True),
            )))
            worker.finished.connect(lambda: setattr(self, "_work_apply_worker", None))
            worker.finished.connect(worker.deleteLater)
            worker.start()

        check_btn = QPushButton("Check readiness")
        check_btn.clicked.connect(lambda _=False: _check())
        layout.addWidget(check_btn)
        apply_btn = QPushButton("Make ready to work")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(lambda _=False: _apply())
        layout.addWidget(apply_btn)
        _check()
        return page

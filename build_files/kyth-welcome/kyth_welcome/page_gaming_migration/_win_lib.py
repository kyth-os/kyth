# __KYTH_GENERATED_IMPORTS__
from ..core_base import restyle
from ..qt import QLabel
from ..widgets import _make_flow_step


class _WinLibMixin:
    def _on_win_lib_result(self, partitions: list) -> None:
        if not partitions:
            return

        while self._win_lib_layout.count():
            item = self._win_lib_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        any_dirty = any(p["is_dirty"] or p["is_hibernated"] for p in partitions)
        any_clean = any(not p["is_dirty"] and not p["is_hibernated"] for p in partitions)

        title_lbl = QLabel("Windows Drive Detected")
        title_lbl.setObjectName("card-title")
        self._win_lib_layout.addWidget(title_lbl)

        if any_dirty:
            self._win_lib_card.setObjectName("card-accent-err")
            restyle(self._win_lib_card)
            warn = QLabel(
                "\u26a0  Your Windows partition is in a hibernated or dirty state \u2014 "
                "this means Windows used Fast Startup or wasn't shut down cleanly."
            )
            warn.setObjectName("card-copy")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #d4a843;")
            self._win_lib_layout.addWidget(warn)

            steps_label = QLabel("To safely import your games:")
            steps_label.setObjectName("card-copy")
            self._win_lib_layout.addWidget(steps_label)
            for index, (step_title, copy) in enumerate((
                ("Boot into Windows", "Then follow the steps below before returning to KythOS."),
                ("Open power settings", "Start \u2192 Settings \u2192 System \u2192 Power & Sleep \u2192 Additional power settings."),
                ("Disable Fast Startup", "\"Choose what the power buttons do\" \u2192 turn off \"Turn on fast startup\"."),
                ("Do a full Shut Down", "Not Restart."),
                ("Come back to KythOS", "Use the Steam Library tool below."),
            ), 1):
                self._win_lib_layout.addWidget(_make_flow_step(index, step_title, copy))

        if any_clean:
            self._win_lib_card.setObjectName("card-accent-ok")
            restyle(self._win_lib_card)
            found_any_steam = any(p["steam_paths"] for p in partitions if not p["is_dirty"])
            if found_any_steam:
                msg = QLabel(
                    "\u2713  Your Steam library was found on this drive.\n"
                    "Use the Steam Library tool below to copy your games to KythOS \u2014 "
                    "the drive is accessed read-only, your original install is never touched."
                )
            else:
                msg = QLabel(
                    "\u2713  A clean PC drive is available.\n"
                    "Use the Steam Library tool below to scan it and copy games to KythOS."
                )
            msg.setObjectName("card-copy")
            msg.setWordWrap(True)
            self._win_lib_layout.addWidget(msg)

        self._win_lib_card.show()

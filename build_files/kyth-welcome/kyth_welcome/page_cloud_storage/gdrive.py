from ._rclone_sync_card import _RcloneSyncCard


class _GoogleDriveMixin:
    # ── Google Drive card ─────────────────────────────────────────────────

    def _build_gd_card(self):
        self._gd_card = _RcloneSyncCard(
            self,
            prefix="gd",
            service="drive",
            title="Google Drive",
            desc=(
                "Sync or mount your Google Drive via rclone. "
                "The setup wizard handles browser OAuth — no terminal required."
            ),
            wizard_key="drive",
            # No "gd" prefix: this key predates OneDrive support.
            interval_key="_sync_interval_min",
            default_folder="~/GoogleDrive",
        )
        self._gd_card.build()

    def _update_gd_sync_label(self):
        self._gd_card.update_label()

    def _start_gd_sync(self, remote: str | None = None, folder: str | None = None):
        self._gd_card.start_sync(remote, folder)

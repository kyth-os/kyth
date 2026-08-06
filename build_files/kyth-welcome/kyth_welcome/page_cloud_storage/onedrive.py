from ._rclone_sync_card import _RcloneSyncCard


class _OneDriveMixin:
    # ── OneDrive card ────────────────────────────────────────────────────

    def _build_od_card(self):
        self._od_card = _RcloneSyncCard(
            self,
            prefix="od",
            service="onedrive",
            title="OneDrive",
            desc=(
                "Sync your Microsoft OneDrive via rclone. "
                "The setup wizard handles Microsoft OAuth in your browser — no terminal required. "
                "Works with personal accounts; business / SharePoint accounts can be configured "
                "manually with rclone config after the initial setup."
            ),
            wizard_key="onedrive",
            interval_key="_od_sync_interval_min",
            default_folder="~/OneDrive",
        )
        self._od_card.build()

    def _update_od_sync_label(self):
        self._od_card.update_label()

    def _start_od_sync(self, remote: str | None = None, folder: str | None = None):
        self._od_card.start_sync(remote, folder)

# __KYTH_GENERATED_IMPORTS__
from .services.security import DEFAULT_KALI_BOX, DEFAULT_KALI_IMAGE, SEC_HOST_TOOLS
from .qt import QVBoxLayout, QWidget
from .page_software_security_hosttools import _HostSecurityToolsMixin
from .page_software_security_kali import _KaliContainerMixin


class _SecurityTabMixin(_KaliContainerMixin, _HostSecurityToolsMixin):
    """The Security tab: Kali Linux distrobox toolbox + host-side (Flatpak) security tools.

    Split across sibling modules: the Kali container lifecycle
    (page_software_security_kali) and the native host-tools grid
    (page_software_security_hosttools). This file only orchestrates the
    tab build and status refresh.
    """

    # Class-level defaults (also on SoftwarePage shell for early access).
    _SEC_BOX_NAME = DEFAULT_KALI_BOX
    _SEC_BOX_IMAGE = DEFAULT_KALI_IMAGE
    _SEC_HOST_TOOLS = SEC_HOST_TOOLS
    # ── Tab 6: Security ───────────────────────────────────────────────────────

    def _build_security_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self._build_kali_card(layout)
        self._build_host_tools_grid(layout)

        layout.addStretch()
        return tab

    def _refresh_sec_status(self):
        self._refresh_sec_kali_status()
        self._refresh_sec_host_tools_status()

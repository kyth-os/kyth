"""Hardware page helpers — extracted from god-page for R5 split.

Keeps page_hardware.py focused on Qt layout; probe/card logic lives here
or in services/hardware/. Re-export for backwards compat.
"""
from .services.hardware.collect import hardware_summary_view  # noqa: F401
from .services.hardware import HardwareProbe  # noqa: F401

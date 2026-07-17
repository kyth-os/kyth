"""Hardware probes package (GPU, display, controllers, platform, …)."""
from .types import HardwareProbe, _status_palette
from .nvidia import (
    _akmod_nvidia_built,
    _akmod_nvidia_installed,
    _detect_nvidia,
    _gpu_probe,
    _hw_setup_done,
    _hw_setup_service_state,
    _nvidia_module_loaded,
)
from .io import (
    _audio_probe,
    _connectivity_probe,
    _controller_probe,
    _displaylink_probe,
    _firmware_probe,
    _peripheral_probe,
)
from .display import (
    _display_probe,
    _format_display_mode,
    _parse_kscreen_output,
    _strip_ansi,
)
from .system import (
    _cpu_probe,
    _memory_probe,
    _platform_probe,
    _storage_probe,
    _thermal_probe,
)
from .codec import (
    _codec_probe,
    _compact_vaapi_failure_details,
    _mesa_vaapi_failure_context,
    _successful_vaapi_probe,
    _vaapi_failure_summary,
    _vaapi_profiles,
)
from .collect import HardwareProbeWorker, _collect_hardware_probes
from .drives import _detect_controllers, _find_ntfs_drives

__all__ = [
    "HardwareProbe",
    "HardwareProbeWorker",
    "DataWorker",
    "TrackedThread",
    "Worker",
    "_akmod_nvidia_built",
    "_akmod_nvidia_installed",
    "_audio_probe",
    "_codec_probe",
    "_collect_hardware_probes",
    "_connectivity_probe",
    "_controller_probe",
    "_cpu_probe",
    "_detect_controllers",
    "_detect_nvidia",
    "_display_probe",
    "_displaylink_probe",
    "_find_ntfs_drives",
    "_firmware_probe",
    "_format_display_mode",
    "_gpu_probe",
    "_hw_setup_done",
    "_hw_setup_service_state",
    "_memory_probe",
    "_nvidia_module_loaded",
    "_parse_kscreen_output",
    "_peripheral_probe",
    "_platform_probe",
    "_status_palette",
    "_storage_probe",
    "_strip_ansi",
    "_thermal_probe",
]


def __getattr__(name: str):
    """Lazy re-export of Qt worker types so pure probe imports stay Qt-free."""
    if name in {"DataWorker", "TrackedThread", "Worker"}:
        from ..runtime import DataWorker, TrackedThread, Worker
        mapping = {
            "DataWorker": DataWorker,
            "TrackedThread": TrackedThread,
            "Worker": Worker,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

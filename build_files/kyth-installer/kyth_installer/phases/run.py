"""Install worker orchestration — Phase 2 verbatim."""
from __future__ import annotations

import os
import traceback
from pathlib import Path

from ..config import LOG_FILE, STAGING_INSTALL_ROOT
from ..context import InstallerContext, InstallLifecycle, InstallPhase
from ..cleanup import clear_secrets_and_orphan_mount, unmount_configuration
from ..recovery import cleanup_registered_mounts
from ..runner import run_command
from ..system import _as_root, _require_no_symlink, _safe_umount, _try_stage_mok_enrollment, require_root
from .common import _push, _record_transaction
from .finalize import _configure_installed_system, _handle_install_failure
from .storage import _prepare_storage_for_plan

def _run_install_worker(
    log, progress, alongside_mount, context: InstallerContext,
):
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, require_root, _try_stage_mok_enrollment, format_install_error
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import require_root  # fallback
        from ..system import _try_stage_mok_enrollment  # fallback
        from ..system import format_install_error  # fallback
    # The execution service owns these transitions in production. Keeping the
    # worker independently invokable also supports the partition CLI and
    # focused phase tests without weakening transition validation.
    if context.lifecycle is InstallLifecycle.IDLE:
        context.transition(InstallLifecycle.VALIDATED)
        context.transition(InstallLifecycle.INSTALLING)
    try:
        require_root()
        from ..install import _prepare_install_context
        resolved = _prepare_install_context(log, context)

        target_part, root_part, alongside_mount = _prepare_storage_for_plan(
            resolved, log, progress, alongside_mount, context
        )
        _record_transaction(context, "image_installed", log=log)

        log("── Phase 2: Configuring installed system ─────────────────────────")
        progress(91)

        if alongside_mount:
            config_root = alongside_mount
        else:
            from ..config import STAGING_INSTALL_ROOT
            config_root = STAGING_INSTALL_ROOT  # noqa: S108 — _require_no_symlink guards this below
            _require_no_symlink(config_root)
            run_command(_as_root(["mkdir", "-p", config_root]), check=True)
            # Detach any stale mount left by a previously crashed install attempt.
            _safe_umount(run_command, config_root)
            context.register_mount(config_root)
            run_command(_as_root(["mount", root_part, config_root]), check=True)

        progress(93)

        _configure_installed_system(
            root_part, target_part, resolved.disk, resolved.kernel, resolved.mode,
            config_root, alongside_mount, log, progress, context, resolved.request,
        )

        log("── Phase 3: Staging Secure Boot enrollment ───────────────────────")
        context.enter_phase(InstallPhase.SECURE_BOOT)
        mok_state = _try_stage_mok_enrollment(log, resolved.kernel, resolved.request.mok_password)

        progress(100)
        context.enter_phase(InstallPhase.COMPLETE)
        context.transition(InstallLifecycle.DONE)
        _record_transaction(context, "complete", log=log)
        _push({"type": "done", "mok_state": mok_state}, context)

    except Exception as exc:
        _handle_install_failure(exc, log, context)
    finally:
        # Guard against orphaned mounts when Phase 1 fails before the inner
        # try/finally (which holds the normal umount) is ever entered.
        clear_secrets_and_orphan_mount(context.state, alongside_mount, run=run_command)
        context.clear_secrets()
        cleanup_registered_mounts(context, run=run_command)

def _run_install(context: InstallerContext) -> None:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, require_root, _try_stage_mok_enrollment, format_install_error
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import require_root  # fallback
        from ..system import _try_stage_mok_enrollment  # fallback
        from ..system import format_install_error  # fallback
    context.events.clear()

    def log(msg: str) -> None:
        _push({"type": "log", "text": msg}, context)
        try:
            with LOG_FILE.open("a") as f:
                f.write(msg + "\n")
        except OSError as exc:
            # Still surface progress over SSE even if the log file is unusable.
            _push({
                "type": "log",
                "text": (
                    f"(installer log write failed for {LOG_FILE}: "
                    f"{format_os_error(exc, path=LOG_FILE)})"
                ),
            }, context)

    def progress(pct: int) -> None:
        _push({"type": "progress", "value": pct}, context)

    try:
        require_root()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # LOG_FILE sits under the world-writable /tmp by default — remove
        # whatever's there first (unlink doesn't follow a symlink, it just
        # drops the link itself), then create fresh with O_EXCL | O_NOFOLLOW
        # so a symlink raced back in between the two calls makes this fail
        # loudly instead of writing through it as root. /tmp's sticky bit
        # protects the file for the rest of the run once this succeeds.
        LOG_FILE.unlink(missing_ok=True)
        fd = os.open(str(LOG_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        _record_transaction(context, "started")
    except Exception as exc:
        message = format_install_error(exc)
        context.transition(InstallLifecycle.FAILED)
        _push({"type": "error", "message": message}, context)
        return

    alongside_mount = ""

    _run_install_worker(log, progress, alongside_mount, context)
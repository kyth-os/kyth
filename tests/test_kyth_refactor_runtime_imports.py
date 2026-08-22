"""Regression checks for names used only by deferred UI callbacks."""
from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome"


class RefactorRuntimeImportTests(unittest.TestCase):
    def test_hub_services_do_not_launch_subprocesses_directly(self):
        allowed = {"privileged.py"}
        violations = []
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                    and path.name not in allowed
                ):
                    violations.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
        self.assertEqual(violations, [])

    # Functions backed by a subprocess call (bootc status, lspci, ...) that
    # WelcomePage and MainWindow's sidebar used to call directly during
    # construction — freezing the whole app before any window appeared,
    # since these are the very first widgets built at startup. Each is
    # wrapped in probe_cached() so it's cheap *after* the first real call,
    # but that first call still blocks the GUI thread if made synchronously
    # from a constructor. Fixed for those two; this guards against a new
    # instance being introduced in any page's __init__ (or in
    # get_nav_groups(), which is MainWindow's sidebar builder) elsewhere.
    _BLOCKING_PROBE_NAMES = frozenset({
        "_detect_nvidia",
        "current_branch",
        "current_kernel_flavor",
        "has_staged_update",
        "has_rollback_deployment",
        "bootc_image_timestamp",
        "bootc_image_digest",
        "bootc_status_text",
        "bootc_status_data",
        "active_bootc_operation",
        "bootc_proxy_running",
        # Added alongside the wizard/NVIDIA-page/Plasma-Wayland-page/
        # Performance-page fixes (page_nvidia.py's own polling loop,
        # page_plasma_wayland's readiness card, page_performance.py's 5s
        # heartbeat, and the wizard's machine/gaming steps) — same
        # subprocess-blocks-the-GUI-thread anti-pattern, different probes.
        "_nvidia_module_loaded",
        "_akmod_nvidia_built",
        "_akmod_nvidia_installed",
        "_hw_setup_service_state",
        "_find_ntfs_drives",
        "is_sched_daemon_active",
        "list_schedulers",
        "kscreen_doctor_output",
        "load_appstream_catalog",
        "build_repair_plan",
        "gather_first_week_checklist",
        "is_installed",
        "_kdeconnect_configured",
        "_printer_configured",
        "_browser_integration_native_ready",
    })

    class _DirectCallFinder(ast.NodeVisitor):
        """Collects calls to banned names, but does not descend into a
        lambda or nested def — those run later (as a worker/timer
        callback), not synchronously at construction time."""

        def __init__(self, banned: frozenset[str]):
            self.banned = banned
            self.found: list[tuple[str, int]] = []

        def visit_Lambda(self, node):  # noqa: N802
            pass

        def visit_FunctionDef(self, node):  # noqa: N802
            pass

        def visit_AsyncFunctionDef(self, node):  # noqa: N802
            pass

        def visit_Call(self, node):  # noqa: N802
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in self.banned:
                self.found.append((name, node.lineno))
            self.generic_visit(node)

    # path (relative to PACKAGE) -> extra function names to scan, beyond the
    # default __init__/get_nav_groups. Covers pages that build eagerly from
    # a helper method rather than __init__ itself directly. Wizard steps
    # are built lazily on first visit; constructors still must not block.
    _EXTRA_SCAN_TARGETS: dict = {
        "wizard/steps_machine.py": ("_make_machine_step",),
        "wizard/steps_gaming.py": ("_make_gaming_step",),
        "page_welcome.py": ("_make_first_week_card",),
        "page_update_ops.py": ("_refresh_summary",),
        "page_software_flatpak/_catalog.py": ("_fp_appstream_catalog",),
        "windows.py": ("_on_mission_bar_ready",),
    }

    def test_page_constructors_do_not_call_blocking_probes_directly(self):
        violations = []
        scan_paths = (
            sorted(PACKAGE.glob("page_*.py"))
            + [
                PACKAGE / "windows.py",
                PACKAGE / "page_registry.py",
                PACKAGE / "page_plasma_wayland" / "__init__.py",
            ]
            + [PACKAGE / pathlib.PurePosixPath(rel) for rel in self._EXTRA_SCAN_TARGETS]
        )
        scan_paths = list(dict.fromkeys(scan_paths))
        for path in scan_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            relative = path.relative_to(PACKAGE).as_posix()
            target_names = {"__init__", "get_nav_groups", *self._EXTRA_SCAN_TARGETS.get(relative, ())}
            targets = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name in target_names
            ]
            for target in targets:
                finder = self._DirectCallFinder(self._BLOCKING_PROBE_NAMES)
                for stmt in target.body:
                    finder.visit(stmt)
                for name, lineno in finder.found:
                    violations.append(f"{relative}:{lineno} calls {name}() directly")
        self.assertEqual(violations, [], (
            "Found blocking probe calls directly inside a constructor/sidebar-builder/"
            "eager-step-builder. Defer these to a background probe (see "
            "WelcomePage._refresh_system_status, MainWindow._refresh_nvidia_nav_visibility, "
            "page_nvidia.py's _refresh_status, or wizard/steps_machine.py's "
            "_refresh_machine_facts for the pattern):\n"
            + "\n".join(violations)
        ))

    def test_deferred_callback_dependencies_are_imported(self):
        required = {
            "page_hardware.py": {"command_stdout"},
            "page_repair_quick.py": {"shlex"},
            "page_welcome.py": {"time"},
        }
        for relative_path, expected in required.items():
            with self.subTest(path=relative_path):
                tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
                imported = {
                    alias.asname or alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names
                }
                self.assertTrue(expected.issubset(imported))


if __name__ == "__main__":
    unittest.main()

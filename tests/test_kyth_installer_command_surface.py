import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "build_files" / "kyth-installer" / "kyth_installer"


class InstallerCommandSurfaceTests(unittest.TestCase):
    def test_execution_modules_use_runner_for_subprocess_run(self):
        execution_modules = {
            "imagesrc.py",
            "install.py",
            "plan.py",
            "system.py",
        }

        for filename in execution_modules:
            with self.subTest(filename=filename):
                tree = ast.parse((INSTALLER / filename).read_text())
                calls = []
                imports_runner = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module == "runner":
                        imports_runner = True
                    if isinstance(node, ast.ImportFrom) and node.module == ".runner":
                        imports_runner = True
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                        and node.func.attr == "run"
                    ):
                        calls.append(node.lineno)

                self.assertFalse(calls, f"direct subprocess.run calls at {calls}")
                self.assertIn(
                    "from .runner import run_command",
                    (INSTALLER / filename).read_text(),
                )

    def test_discovery_modules_keep_subprocess_boundary_explicit(self):
        discovery_modules = {"disk.py"}
        for filename in discovery_modules:
            with self.subTest(filename=filename):
                text = (INSTALLER / filename).read_text()
                self.assertIn("subprocess", text)

    def test_install_progress_runner_is_module_level(self):
        tree = ast.parse((INSTALLER / "install.py").read_text())
        module_functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue(
            {
                "_run_cmd",
                "_prepare_install_context",
                "_prepare_install_storage",
                "_configure_installed_system",
                "_run_install_worker",
            }.issubset(module_functions)
        )

        run_install = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_install"
        )
        nested_functions = {
            node.name for node in run_install.body if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("run_cmd", nested_functions)

        worker = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_install_worker"
        )
        self.assertLessEqual(worker.end_lineno - worker.lineno + 1, 60)


if __name__ == "__main__":
    unittest.main()

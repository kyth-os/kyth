import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
sys.path.insert(0, str(INSTALLER_ROOT))


class InstallerEntrypointTests(unittest.TestCase):
    def test_python_entrypoint_compiles_and_imports_package_main(self):
        entrypoint = INSTALLER_ROOT / "kyth-installer"
        tree = ast.parse(entrypoint.read_text())
        imports_main = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "kyth_installer.app"
            and any(alias.name == "main" for alias in node.names)
            for node in ast.walk(tree)
        )

        self.assertTrue(imports_main)

    def test_installer_package_imports_without_starting_browser(self):
        from kyth_installer import app, server  # noqa: PLC0415

        self.assertEqual(app.PORT, 7777)
        self.assertTrue(hasattr(server, "Handler"))

    def test_desktop_launcher_shell_syntax(self):
        import subprocess  # noqa: PLC0415

        subprocess.run(
            ["bash", "-n", str(ROOT / "build_files" / "kyth-launch-installer")],
            check=True,
        )

    def test_live_image_installs_shared_python_package(self):
        containerfile = (ROOT / "installer" / "Containerfile").read_text()
        build_script = (ROOT / "installer" / "build.sh").read_text()

        self.assertIn("source=build_files/kyth_shared", containerfile)
        self.assertIn("python3 -m pip install", build_script)
        self.assertIn("/src/build_files/kyth_shared", build_script)
        self.assertNotIn("/usr/kyth_shared", build_script)


if __name__ == "__main__":
    unittest.main()

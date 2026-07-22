import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PythonPackagingTests(unittest.TestCase):
    def _metadata(self, relative: str) -> dict:
        with (ROOT / relative / "pyproject.toml").open("rb") as stream:
            return tomllib.load(stream)

    def test_runtime_projects_have_standard_metadata(self):
        expected = {
            "build_files/kyth_shared": "kyth-shared",
            "build_files/kyth-installer": "kyth-installer",
            "build_files/kyth-welcome": "kyth-welcome",
        }

        for relative, project_name in expected.items():
            with self.subTest(project=project_name):
                metadata = self._metadata(relative)
                self.assertEqual(metadata["build-system"]["build-backend"], "setuptools.build_meta")
                self.assertEqual(metadata["project"]["name"], project_name)

    def test_app_packages_publish_console_entry_points(self):
        installer = self._metadata("build_files/kyth-installer")
        welcome = self._metadata("build_files/kyth-welcome")

        self.assertEqual(
            installer["project"]["scripts"]["kyth-installer"],
            "kyth_installer.app:main",
        )
        self.assertEqual(
            welcome["project"]["scripts"]["kyth-welcome"],
            "kyth_welcome.app:main",
        )

    def test_image_builds_install_python_projects_via_pip(self):
        installer_build = (ROOT / "installer/build.sh").read_text()
        helper_build = (
            ROOT / "build_files/scripts/branding/23-kyth-helper-ctx-installs.sh"
        ).read_text()

        self.assertIn("python3 -m pip install", installer_build)
        self.assertIn("/src/build_files/kyth-installer", installer_build)
        self.assertIn("python3 -m pip install", helper_build)
        self.assertIn("/ctx/kyth-welcome", helper_build)
        self.assertNotIn("/usr/lib/kyth-installer", installer_build)
        self.assertNotIn("/usr/lib/kyth-welcome", helper_build)


if __name__ == "__main__":
    unittest.main()

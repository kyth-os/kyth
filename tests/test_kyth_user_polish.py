import unittest
from unittest.mock import patch, mock_open
import sys
from pathlib import Path

# Add project root to sys.path to resolve imports if needed
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build_files"))

import importlib.util
from importlib.machinery import SourceFileLoader

loader = SourceFileLoader("kyth_user_polish", str(ROOT / "build_files" / "kyth-user-polish"))
spec = importlib.util.spec_from_loader("kyth_user_polish", loader)
kyth_user_polish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kyth_user_polish)


class TestKythUserPolish(unittest.TestCase):
    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("os.path.isdir")
    @patch("os.path.isfile")
    @patch("os.makedirs")
    @patch("glob.glob")
    @patch("builtins.open", new_callable=mock_open)
    def test_main_flow(self, mock_file_open, mock_glob, mock_makedirs, mock_isfile, mock_isdir, mock_run, mock_which):
        # Setup mocks
        mock_which.side_effect = lambda cmd: "/usr/bin/" + cmd
        mock_isdir.return_value = False
        mock_isfile.return_value = False
        mock_glob.return_value = []
        
        # Mock sys.argv
        with patch("sys.argv", ["kyth-user-polish"]):
            kyth_user_polish.main()
            
        # Verify kwriteconfig6 was called for some key configurations
        calls = [c[0][0] for c in mock_run.call_args_list]
        
        # We expect kwriteconfig6 to be called for ksplashrc, kwalletrc, kdeglobals, etc.
        has_ksplash = any("ksplashrc" in cmd for cmd in calls)
        has_kwallet = any("kwalletrc" in cmd for cmd in calls)
        
        self.assertTrue(has_ksplash, "Should configure ksplash")
        self.assertTrue(has_kwallet, "Should configure kwallet")


if __name__ == "__main__":
    unittest.main()

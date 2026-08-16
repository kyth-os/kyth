import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

try:
    from kyth_welcome.core_base import replace_clicked_handler  # noqa: E402
except ImportError:
    raise unittest.SkipTest("Qt bindings required for UI signal tests") from None


class ReplaceClickedHandlerTests(unittest.TestCase):
    def test_connects_initial_handler_without_blind_disconnect(self):
        button = mock.Mock(spec=[])
        button.clicked = mock.Mock()
        handler = mock.Mock()

        replace_clicked_handler(button, handler)

        button.clicked.disconnect.assert_not_called()
        button.clicked.connect.assert_called_once_with(handler)

    def test_disconnects_only_the_handler_it_previously_installed(self):
        button = mock.Mock(spec=[])
        button.clicked = mock.Mock()
        first = mock.Mock()
        second = mock.Mock()

        replace_clicked_handler(button, first)
        replace_clicked_handler(button, second)

        button.clicked.disconnect.assert_called_once_with(first)
        self.assertEqual(button.clicked.connect.call_args_list, [mock.call(first), mock.call(second)])


if __name__ == "__main__":
    unittest.main()

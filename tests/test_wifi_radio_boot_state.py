import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NETWORK_SETUP = ROOT / "build_files/scripts/sysconfig/network/16-wifi-disable-power-management.sh"


class WifiRadioBootStateTests(unittest.TestCase):
    def test_wired_dispatcher_does_not_persist_wifi_radio_off(self):
        """A wired link must not persistently disable Wi-Fi across reboots."""
        source = NETWORK_SETUP.read_text(encoding="utf-8")
        match = re.search(
            r"write_config /etc/NetworkManager/dispatcher\.d/80-kyth-wired-or-wireless 0755 <<'NMWIREDEOF'\n(.*?)\nNMWIREDEOF",
            source,
            re.DOTALL,
        )
        if match is None:
            self.fail("expected installed wired-network dispatcher")
        dispatcher = match.group(1)
        self.assertNotIn("nmcli radio wifi off", dispatcher)
        self.assertNotIn("wifi-off-for-wired", dispatcher)


if __name__ == "__main__":
    unittest.main()

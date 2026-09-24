import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_POLICY = ROOT / "build_files/scripts/sysconfig/audio/20-wireplumber-audio-policy.sh"


class WirePlumberPolicyTests(unittest.TestCase):
    def test_bluetooth_rules_are_combined_in_one_monitor_assignment(self):
        source = AUDIO_POLICY.read_text(encoding="utf-8")
        config_match = re.search(r"<<'WPEOF'\n(.*?)\nWPEOF", source, re.DOTALL)
        if config_match is None:
            self.fail("expected WirePlumber config heredoc")
        config = config_match.group(1)
        self.assertEqual(
            len(re.findall(r"^monitor\.bluez\.rules\s*=", config, re.MULTILINE)),
            1,
            "SPA-JSON repeated keys overwrite earlier Bluetooth policy rules",
        )
        self.assertIn("device.name = \"~bluez_card.*\"", config)
        self.assertIn("node.name = \"~bluez_output.*\"", config)


if __name__ == "__main__":
    unittest.main()

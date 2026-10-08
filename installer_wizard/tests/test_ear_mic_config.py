import asyncio
import unittest
from unittest import mock

from features.ear import api


class MicConfigTest(unittest.TestCase):
    def config(self, agc: str | None) -> dict:
        values = {} if agc is None else {"ATENA_MIC_AGC": agc}
        with mock.patch("features.ear.api.require_display"), \
                mock.patch("features.ear.api.env_get", side_effect=lambda key, default: values.get(key, default)):
            return asyncio.run(api.ear_config(mock.Mock()))

    def test_automatic_level_is_the_default(self):
        cfg = self.config(None)
        self.assertTrue(cfg["autoLevel"])
        self.assertFalse(cfg["autoGainControl"])

    def test_forced_on_and_off(self):
        self.assertEqual((self.config("1")["autoGainControl"], self.config("1")["autoLevel"]), (True, False))
        self.assertEqual((self.config("0")["autoGainControl"], self.config("0")["autoLevel"]), (False, False))


if __name__ == "__main__":
    unittest.main()

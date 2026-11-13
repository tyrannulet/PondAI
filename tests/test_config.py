import unittest
from unittest.mock import patch

from scripts import config


class CredentialTests(unittest.TestCase):
    def test_dummy_credentials_do_not_enable_api_calls(self):
        for value in (None, "", "  ", "AAAA", "aaaa", "PASTE_API_KEY"):
            with self.subTest(value=value):
                self.assertTrue(config.is_placeholder(value))
                with patch.object(config, "get_featherless_config", return_value={"FEATHERLESS_API_KEY": value}):
                    self.assertFalse(config.has_real_featherless())
                with patch.object(config, "get_copernicus_config", return_value={
                    "CDSE_CLIENT_ID": value, "CDSE_CLIENT_SECRET": "real-secret",
                    "CDSE_TOKEN_URL": "https://example.com/token",
                }):
                    self.assertFalse(config.has_real_copernicus())


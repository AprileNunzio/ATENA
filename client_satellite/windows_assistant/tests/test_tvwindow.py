import unittest

from app import tvwindow


class TrustedUrlTest(unittest.TestCase):
    def test_only_atena_tv_pages_open(self):
        self.assertTrue(tvwindow.trusted("http://192.168.1.10:8080/tv/watch?c=ab&t=1", "atena.local:8443"))
        self.assertTrue(tvwindow.trusted("http://atena.local:8080/tv/watch?c=ab", "atena.local:8443"))
        for url in ("https://evil.example/tv/watch?c=1", "http://192.168.1.10:8080/admin", "file:///C:/x",
                    "http://192.168.1.10/tv/watch", "javascript:alert(1)"):
            self.assertFalse(tvwindow.trusted(url, "atena.local:8443"), url)


if __name__ == "__main__":
    unittest.main()

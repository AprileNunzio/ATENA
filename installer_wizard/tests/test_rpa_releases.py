import unittest

from features.rpa import releases


def release(tag, assets=("ATENA_Assistente_Setup.exe",), **extra):
    return {"tag_name": tag, "assets": [{"name": a, "browser_download_url": f"https://x/{tag}/{a}"} for a in assets], **extra}


class ReleasesTest(unittest.TestCase):
    def test_the_newest_published_installer_is_chosen(self):
        chosen = releases.pick([release("assistant-v1.2.0"), release("assistant-v1.10.0"), release("v9.0.0"),
                                release("assistant-v2.0.0", draft=True), release("assistant-v3.0.0", assets=("manifest.json",))])
        self.assertEqual(chosen, "https://x/assistant-v1.10.0/ATENA_Assistente_Setup.exe")

    def test_no_installer_means_no_redirect(self):
        self.assertEqual(releases.pick([release("v1.0.0")]), "")


if __name__ == "__main__":
    unittest.main()

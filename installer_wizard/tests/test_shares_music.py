import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.shares import archive

HEADERS = {"X-Atena-Request": "1"}
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "os" / "steps" / "63-shares.sh"


class SharesMusicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "condivisa"
        patcher = mock.patch.object(archive, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_install_script_creates_every_folder_the_code_uses(self):
        text = SCRIPT.read_text(encoding="utf-8")
        listed = set(re.findall(r'"(\d\d [^"]+)"', re.search(r"^FOLDERS=\((.*?)\)", text, re.M | re.S).group(1)))
        self.assertEqual(listed, set(archive.FOLDERS.values()))
        self.assertIn('06 Musica', text.split("step_check()")[1].split("write_conf()")[0])

    def test_opening_the_shares_page_creates_the_whole_structure(self):
        r = self.admin.get("/api/shares", headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        for name in archive.FOLDERS.values():
            self.assertTrue((self.root / name).is_dir(), name)
        self.assertTrue((self.root / "06 Musica").is_dir())
        self.assertIn("06 Musica", [f["name"] for f in r.json()["folders"]])

    def test_music_folder_has_its_subfolders_and_the_script_creates_them_too(self):
        self.admin.get("/api/shares", headers=HEADERS)
        for sub in ("Libreria", "Da smistare", "Playlist", "Copertine"):
            self.assertTrue((self.root / "06 Musica" / sub).is_dir(), sub)
        text = SCRIPT.read_text(encoding="utf-8")
        for sub in archive.SUBFOLDERS["musica"]:
            self.assertIn(f'"{sub}"', text)
        self.assertIn("06 Musica/Libreria", (self.root / "LEGGIMI.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

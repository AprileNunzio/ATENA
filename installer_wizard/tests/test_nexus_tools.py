import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.nexus import composition
from features.nexus.application.freshness_service import FreshnessService
from features.nexus.application.tool_service import ToolNotFound, ToolService
from features.nexus.domain import freshness, wizard
from features.nexus.infrastructure.fingerprint import FolderFingerprint
from features.nexus.infrastructure.json_store import JsonDocument

HEADERS = {"X-Atena-Request": "1"}
FEATURES = Path(__file__).resolve().parents[1] / "features"
CAMERA = {"id": "cam", "name": "Cam", "toggle": {"env": "ATENA_CAM"}, "settings": [
    {"key": "ATENA_CAM_FPS", "label": "Fluidità", "type": "select", "options": [{"value": "8", "label": "8 al secondo"}, "15"]},
    {"key": "ATENA_CAM_KEY", "label": "Chiave", "type": "secret"},
    {"key": "ATENA_CAM_ON", "label": "Registra", "type": "bool"},
    {"key": "ATENA_CAM_LINK", "label": "Pagina", "type": "link", "default": "/x"},
]}


class WizardTest(unittest.TestCase):
    def test_generated_wizard_covers_mode_and_settings(self):
        steps = wizard.build(CAMERA)
        self.assertEqual([s["kind"] for s in steps], ["mode", "choice", "field", "choice"])
        self.assertEqual(steps[1]["options"][1], {"value": "15", "label": "15", "hint": ""})
        self.assertEqual(steps[2]["input"], "password")
        self.assertEqual([o["value"] for o in steps[3]["options"]], ["1", "0"])

    def test_declared_wizard_is_validated(self):
        manifest = {**CAMERA, "wizard": [{"kind": "mode", "title": "Accendo la cam?"}, {"setting": "ATENA_CAM_ON", "title": "Registro?"},
                                         {"setting": "NOPE"}, {"setting": "../x"}, "garbage"]}
        steps = wizard.build(manifest)
        self.assertEqual([s["title"] for s in steps], ["Accendo la cam?", "Registro?"])
        self.assertEqual(wizard.build({"id": "fixed", "settings": []}), [])

    def test_every_shipped_manifest_produces_a_valid_wizard(self):
        for path in FEATURES.glob("*/feature.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for step in wizard.build(manifest):
                self.assertIn(step["kind"], ("mode", "choice", "field"), path)
                self.assertLessEqual(len(step.get("options", [])), wizard.MAX_OPTIONS)


class FreshnessDomainTest(unittest.TestCase):
    def test_first_run_is_a_silent_baseline(self):
        records = freshness.reconcile({}, {"a": "1", "b": "2"}, now=1000.0)
        self.assertEqual({freshness.badge(r, 1000.0)["badge"] for r in records.values()}, {""})

    def test_new_and_updated_badges_expire(self):
        base = freshness.reconcile({}, {"a": "1"}, now=0.0)
        later = freshness.reconcile(base, {"a": "2", "b": "9"}, now=100.0)
        self.assertEqual(freshness.badge(later["a"], 101.0), {"badge": "updated", "since": 100.0})
        self.assertEqual(freshness.badge(later["b"], 101.0), {"badge": "new", "since": 100.0})
        self.assertEqual(freshness.badge(later["b"], 100.0 + freshness.FRESH_SECONDS + 1)["badge"], "")
        self.assertEqual(freshness.reconcile(later, {"a": "2", "b": "9"}, now=500.0), later)

    def test_restore_ignores_garbage(self):
        self.assertEqual(freshness.restore({"a": {"fingerprint": "x"}, "b": 3, 4: {}, "c": {"no": 1}}).keys(), {"a"})
        self.assertEqual(freshness.restore([]), {})


class FreshnessInfrastructureTest(unittest.TestCase):
    def test_fingerprint_follows_content_not_cache_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "a.py").write_text("x = 1")
            fp = FolderFingerprint()
            first = fp(folder)
            (folder / "__pycache__").mkdir()
            (folder / "__pycache__" / "a.pyc").write_bytes(b"junk")
            self.assertEqual(fp(folder), first)
            (folder / "a.py").write_text("x = 2")
            self.assertNotEqual(fp(folder), first)

    def test_release_version_bump_is_not_an_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "mcp.py").write_text('INFO = {"version": "4.1.46"}')
            before = FolderFingerprint(ignore=("4.1.46",))(folder)
            (folder / "mcp.py").write_text('INFO = {"version": "4.1.47"}')
            self.assertEqual(FolderFingerprint(ignore=("4.1.47",))(folder), before)

    def test_service_persists_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "feat"
            folder.mkdir()
            (folder / "m.py").write_text("a")
            clock = [1000.0]
            doc = JsonDocument(Path(tmp) / "fresh.json")
            service = FreshnessService(FolderFingerprint(), doc, clock=lambda: clock[0])
            service.refresh({"feat": folder})
            self.assertEqual(service.badges()["feat"]["badge"], "")
            (folder / "m.py").write_text("b")
            clock[0] += 30
            service.refresh({"feat": folder})
            self.assertEqual(service.badges()["feat"]["badge"], "")
            clock[0] += 60
            service.refresh({"feat": folder})
            self.assertEqual(service.badges()["feat"]["badge"], "updated")
            reloaded = FreshnessService(FolderFingerprint(), doc, clock=lambda: clock[0])
            reloaded.refresh({"feat": folder})
            self.assertEqual(reloaded.badges()["feat"]["badge"], "updated")
            self.assertEqual((Path(tmp) / "fresh.json").stat().st_mode & 0o777, 0o600)
            upgraded = FreshnessService(lambda _: "other-method", doc, clock=lambda: clock[0], revision="2")
            upgraded.refresh({"feat": folder})
            self.assertEqual(upgraded.badges()["feat"]["badge"], "")


class ToolServiceTest(unittest.TestCase):
    def test_detail_shapes_the_tool_and_rejects_unknown_ids(self):
        listing = {"features": [{**CAMERA, "state": {"enabled": True, "mode": "auto"}, "values": {"ATENA_CAM_KEY": "••••1234"}}],
                   "hardware": {"ram_gb": 8}}
        service = ToolService(lambda: listing, badges=lambda: {"cam": {"badge": "new", "since": 5}})
        tool = service.detail("cam")
        self.assertEqual((tool["mode"], tool["badge"], tool["values"]["ATENA_CAM_KEY"]), ("auto", "new", "••••1234"))
        self.assertEqual(tool["settings"][0]["options"][0]["label"], "8 al secondo")
        for bad in ("missing", "../etc", "", "A" * 80):
            with self.assertRaises(ToolNotFound):
                service.detail(bad)


class ToolApiTest(unittest.TestCase):
    def test_tool_detail_endpoint(self):
        self.assertEqual(TestClient(atena_supervisor.admin).get("/api/nexus/tools/cameras").status_code, 401)
        admin = TestClient(atena_supervisor.admin)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        with mock.patch.object(composition.freshness, "document", JsonDocument(Path(tempfile.mkdtemp()) / "f.json")):
            composition.freshness._records = None
            r = admin.get("/api/nexus/tools/cameras")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["zone"], "tools")
        self.assertTrue(data["wizard"])
        self.assertIn("badge", data)
        self.assertEqual(admin.get("/api/nexus/tools/no_such_tool").status_code, 404)
        self.assertEqual(admin.get("/api/nexus/tools/..%2Fetc").status_code, 404)


if __name__ == "__main__":
    unittest.main()

import unittest

from fastapi.testclient import TestClient

import atena_supervisor
from features.desktop.desk import desk

HEADERS = {"X-Atena-Request": "1"}


class WidgetRecallTest(unittest.TestCase):
    def setUp(self):
        desk.scan()
        self.wid = next(w for w, m in desk.widgets.items() if not m.get("bind") and m.get("demo") and w != "alarm")
        desk.last.pop(self.wid, None)

    def tearDown(self):
        desk.hide(key=f"recall:{self.wid}")

    def test_preview_then_last_real_data(self):
        self.assertEqual(desk.recall(self.wid), "preview")
        desk.show(self.wid, {"content": "dati veri"}, key="vero")
        self.assertEqual(desk.recall(self.wid), "last")
        self.assertEqual(desk.instances[f"recall:{self.wid}"]["data"], {"content": "dati veri"})
        desk.show(self.wid, {"content": "prova"}, key=f"test:{self.wid}")
        self.assertEqual(desk.last[self.wid], {"content": "dati veri"})
        desk.hide(key="vero")

    def test_self_sufficient_widgets_open_live(self):
        clock = next((w for w, m in desk.widgets.items() if not m.get("bind") and not m.get("demo")), None)
        if clock is None:
            self.skipTest("nessun widget autonomo")
        desk.last.pop(clock, None)
        self.assertEqual(desk.recall(clock), "live")
        desk.hide(key=f"recall:{clock}")

    def test_bound_widgets_use_live_sources(self):
        bound = next((w for w, m in desk.widgets.items() if isinstance(m.get("bind"), str)), None)
        if bound is None:
            self.skipTest("nessun widget collegato")
        attr = desk.widgets[bound]["bind"]
        previous = desk.sources.get(attr)
        desk.register_source(attr, lambda: {"title": "dal vivo"})
        try:
            self.assertEqual(desk.recall(bound), "live")
        finally:
            desk.hide(key=f"recall:{bound}")
            if previous:
                desk.register_source(attr, previous)
            else:
                desk.sources.pop(attr, None)

    def test_api_requires_admin_and_rejects_unknown(self):
        self.assertEqual(TestClient(atena_supervisor.admin).post(f"/api/widgets/{self.wid}/recall", headers=HEADERS).status_code, 401)
        admin = TestClient(atena_supervisor.admin)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        self.assertEqual(admin.post(f"/api/widgets/{self.wid}/recall").status_code, 403)
        self.assertEqual(admin.post(f"/api/widgets/{self.wid}/recall", headers=HEADERS).json()["origin"], "preview")
        self.assertEqual(admin.post("/api/widgets/nope/recall", headers=HEADERS).status_code, 404)
        self.assertEqual(admin.post("/api/widgets/alarm/recall", headers=HEADERS).status_code, 400)


if __name__ == "__main__":
    unittest.main()

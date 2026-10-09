import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from access import require_admin
from features.locale import api as locale_api
from features.locale import service
from tests.test_locale import LocaleBase


def _apps(user: str = "nunzio") -> tuple[TestClient, TestClient]:
    public, admin = FastAPI(), FastAPI()
    public.include_router(locale_api.public_routes)
    admin.include_router(locale_api.admin_routes)
    admin.dependency_overrides[require_admin] = lambda: user
    return TestClient(public), TestClient(admin)


class LocaleApiTests(LocaleBase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(locale_api, "require_display", lambda request: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_admin_users_keep_separate_languages(self):
        _, nunzio = _apps("nunzio")
        _, maria = _apps("maria")
        self.assertEqual(nunzio.put("/api/locale/ui", json={"lang": "fr"}).json(), {"ui": "fr"})
        self.assertEqual(maria.get("/api/locale").json()["ui"], service.system_ui())
        self.restart()
        self.assertEqual(nunzio.get("/api/locale").json()["ui"], "fr")

    def test_display_language_is_stored_for_the_device(self):
        public, _ = _apps()
        self.assertEqual(public.put("/api/locale/ui", json={"lang": "en"}).status_code, 200)
        self.restart()
        body = public.get("/api/locale").json()
        self.assertEqual(body["ui"], "en")
        self.assertIn("ja", body["reply_languages"])

    def test_device_reply_language_can_be_set_and_cleared_from_the_panel(self):
        _, admin = _apps()
        body = admin.put("/api/locale/device/cucina", json={"reply": "de", "teach": True}).json()
        self.assertEqual((body["reply"], body["teach"]), ("de", True))
        body = admin.put("/api/locale/device/cucina", json={"reply": ""}).json()
        self.assertEqual((body["reply"], body["teach"]), (service.system_reply(), False))

    def test_invalid_input_is_rejected(self):
        public, admin = _apps()
        self.assertEqual(public.put("/api/locale/ui", json={"lang": "klingon"}).status_code, 400)
        self.assertEqual(public.put("/api/locale/ui", json=["it"]).status_code, 400)
        self.assertEqual(admin.put("/api/locale/device/a%20b", json={"ui": "it"}).status_code, 400)

    def test_pages_carry_the_resolved_language(self):
        import pages
        service.set_ui("fr", device="remote")
        with mock.patch.object(pages, "WEB_DIR") as web:
            web.__truediv__.return_value.read_text.return_value = "<html><head></head><body></body></html>"
            html = pages.page("x.html", "fr").body.decode()
        self.assertIn('window.ATENA_UI_LANG = "fr"', html)


if __name__ == "__main__":
    unittest.main()

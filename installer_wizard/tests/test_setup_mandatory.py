import unittest
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
import setup_api
from state import store


class MandatorySetupTest(unittest.TestCase):
    def setUp(self):
        self.public = TestClient(atena_supervisor.public)
        self.admin = TestClient(atena_supervisor.admin)
        self.phase = mock.patch.object(store, "phase", "READY")
        self.phase.start()
        self.private = mock.patch.object(setup_api, "_private_client", lambda request: True)
        self.private.start()

    def tearDown(self):
        self.phase.stop()
        self.private.stop()

    def test_display_and_admin_lead_to_setup_until_it_is_done(self):
        with mock.patch.object(setup_api, "done", return_value=False):
            display = self.public.get("/", follow_redirects=False)
            self.assertEqual((display.status_code, display.headers["location"]), (303, "/setup"))
            panel = self.admin.get("/", follow_redirects=False)
            self.assertEqual(panel.status_code, 303)
            self.assertTrue(panel.headers["location"].endswith("/setup"))

    def test_nothing_is_redirected_once_setup_is_done(self):
        with mock.patch.object(setup_api, "done", return_value=True):
            self.assertEqual(self.public.get("/", follow_redirects=False).status_code, 200)
            self.assertEqual(self.admin.get("/", follow_redirects=False).status_code, 200)

    def test_installation_monitor_stays_visible_while_installing(self):
        with mock.patch.object(setup_api, "done", return_value=False), mock.patch.object(store, "phase", "INSTALLING"):
            self.assertEqual(self.public.get("/", follow_redirects=False).status_code, 200)


if __name__ == "__main__":
    unittest.main()

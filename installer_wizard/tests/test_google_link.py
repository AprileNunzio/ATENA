import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from sealed import SealedFile

from features.google import app as google_app
from features.google.flows import FlowStore, LinkError, parse

CODE = "4/0AVG7fiQ" + "x" * 40


def store_in(root: str) -> FlowStore:
    return FlowStore(SealedFile(Path(root) / "flows.vault", Path(root) / "flows.key"))


class ParseTest(unittest.TestCase):
    def test_full_url(self):
        p = parse(f"http://127.0.0.1:8889/?state=abc&code={CODE.replace('/', '%2F')}&scope=email+openid")
        self.assertEqual((p.code, p.state, p.error), (CODE, "abc", ""))

    def test_url_without_scheme_and_with_line_breaks(self):
        p = parse(f"127.0.0.1:8889/?state=abc&\n code={CODE}")
        self.assertEqual((p.code, p.state), (CODE, "abc"))

    def test_bare_code(self):
        self.assertEqual(parse(f"  {CODE} ").code, CODE)

    def test_denied(self):
        self.assertEqual(parse("http://127.0.0.1:8889/?error=access_denied&state=abc").error, "access_denied")

    def test_garbage(self):
        self.assertEqual(parse("ciao").code, "")


class FlowStoreTest(unittest.TestCase):
    def test_flow_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store_in(root).create("s1", "mario", "v1")
            state, flow = store_in(root).resolve(parse(f"?state=s1&code={CODE}"))
            self.assertEqual((state, flow["slug"], flow["verifier"]), ("s1", "mario", "v1"))

    def test_missing_state_uses_the_person_being_linked(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            flows.create("s2", "anna", "v2")
            self.assertEqual(flows.resolve(parse(CODE), "anna")[0], "s2")
            with self.assertRaises(LinkError):
                flows.resolve(parse(CODE))

    def test_used_state_explains_itself(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            flows.consume("s1")
            with self.assertRaisesRegex(LinkError, "già stato usato"):
                flows.resolve(parse(f"?state=s1&code={CODE}"))

    def test_expired_flows_are_dropped(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            with mock.patch("features.google.flows.time.time", return_value=time.time() + 4000):
                self.assertEqual(flows.pending(), [])
                with self.assertRaisesRegex(LinkError, "Nessun collegamento"):
                    flows.resolve(parse(f"?state=s1&code={CODE}"))

    def test_cancel(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            flows.cancel("mario")
            self.assertEqual(flows.pending(), [])


class ExchangeTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_exchange_keeps_the_flow_for_a_retry(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            oauth = google_app.OAuthApp()
            with mock.patch.object(google_app, "flows", flows), \
                    mock.patch.object(oauth, "token", side_effect=ValueError("Google: errore 500")):
                with self.assertRaises(ValueError):
                    await oauth.exchange(f"?state=s1&code={CODE}")
            self.assertEqual([f["slug"] for f in flows.pending()], ["mario"])

    async def test_success_consumes_the_flow(self):
        with tempfile.TemporaryDirectory() as root:
            flows = store_in(root)
            flows.create("s1", "mario", "v1")
            oauth = google_app.OAuthApp()
            token = mock.AsyncMock(return_value={"refresh_token": "r", "access_token": "a"})
            with mock.patch.object(google_app, "flows", flows), mock.patch.object(oauth, "token", token):
                slug, body = await oauth.exchange(f"?state=s1&code={CODE}")
            self.assertEqual((slug, body["refresh_token"]), ("mario", "r"))
            self.assertEqual(token.call_args.args[0]["code_verifier"], "v1")
            self.assertEqual(flows.pending(), [])


if __name__ == "__main__":
    unittest.main()

import asyncio
import hashlib
import time
import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

import access
import atena_supervisor
from config import write_env
from features.music import catalog, dlna, sharing, tokens
from features.music.db import db
from features.music.outputs import DEVICE_RE, Outputs, outputs as shared_outputs
from state import store
from tests.test_music_library import Base

HEADERS = {"X-Atena-Request": "1"}
DESCRIPTION = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><friendlyName>Salotto</friendlyName><modelName>Box</modelName>
<serviceList><service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType><controlURL>/avt</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType><controlURL>/rc</controlURL></service></serviceList></device></root>"""


class DlnaTest(unittest.TestCase):
    def test_ssdp_reply_and_device_description_are_parsed(self):
        reply = b"HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.9:49152/d.xml\r\nUSN: uuid:abc::urn:x\r\n\r\n"
        self.assertEqual(dlna.parse_ssdp(reply)["location"], "http://192.168.1.9:49152/d.xml")
        found = dlna.find_services(DESCRIPTION, "http://192.168.1.9:49152/d.xml")
        self.assertEqual((found["name"], found["avt"], found["rc"]), ("Salotto", "http://192.168.1.9:49152/avt", "http://192.168.1.9:49152/rc"))
        with self.assertRaises(Exception):
            dlna.find_services("<x/>", "http://a/")

    def test_only_private_addresses_are_trusted(self):
        for host in ("192.168.1.5", "10.0.0.2", "172.16.4.4", "169.254.1.1"):
            self.assertTrue(dlna.private_host(host), host)
        for host in ("8.8.8.8", "example.com", ""):
            self.assertFalse(dlna.private_host(host), host)

    def test_times_and_metadata_are_escaped(self):
        self.assertEqual(dlna.clock(3725), "1:02:05")
        self.assertEqual(dlna.seconds("0:03:20.500"), 200)
        self.assertEqual(dlna.seconds("NOT_IMPLEMENTED"), 0)
        meta = dlna.didl("A & <B>", "x", "y", "http://h/a?b=1&c=2", "", "audio/mpeg")
        self.assertIn("A &amp; &lt;B&gt;", meta)
        self.assertNotIn("<B>", meta)

    def test_describe_rejects_locations_that_do_not_match_the_responder(self):
        async def run():
            return await dlna.describe("192.168.1.9", {"location": "http://10.9.9.9/d.xml", "usn": "uuid:a"}), \
                   await dlna.describe("8.8.8.8", {"location": "http://8.8.8.8/d.xml", "usn": "uuid:a"})
        self.assertEqual(asyncio.run(run()), (None, None))

    def test_soap_calls_carry_the_action_and_surface_errors(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.headers["soapaction"], request.content.decode()))
            if "Stop" in request.headers["soapaction"]:
                return httpx.Response(500)
            return httpx.Response(200, text='<s:Envelope xmlns:s="x"><s:Body><u:R xmlns:u="y"><CurrentTransportState>PLAYING</CurrentTransportState>'
                                            '<RelTime>0:00:10</RelTime><TrackDuration>0:03:00</TrackDuration></u:R></s:Body></s:Envelope>')

        real = httpx.AsyncClient
        device = {"avt": "http://192.168.1.9/avt", "rc": "http://192.168.1.9/rc"}
        with mock.patch.object(dlna.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            info = asyncio.run(dlna.status(device))
            self.assertEqual(info, {"state": "playing", "position": 10, "duration": 180})
            asyncio.run(dlna.control(device, "volume", 0.5))
            self.assertIn("<DesiredVolume>50</DesiredVolume>", seen[-1][1])
            with self.assertRaises(RuntimeError):
                asyncio.run(dlna.control(device, "stop"))
            with self.assertRaises(ValueError):
                asyncio.run(dlna.control(device, "explode"))


class OutputsTest(Base, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.filled()
        self.out = Outputs()
        self.out.remote_beat("display:sala", "Sala")
        self.ids = [t["id"] for t in catalog.tracks("title")]
        self.addCleanup(lambda: setattr(store, "now_playing", {}))

    async def test_device_ids_are_validated(self):
        self.assertTrue(DEVICE_RE.match("display:sala-1"))
        for bad in ("../x", "display:", "tv:1", "cast:a b", "display:" + "x" * 80):
            self.assertIsNone(DEVICE_RE.match(bad), bad)
        with self.assertRaises(KeyError):
            await self.out.start("display:ignoto", "ann", self.ids, 0, 0, "http://h")

    async def test_start_sends_a_signed_load_command_and_announces_the_track(self):
        view = await self.out.start("display:sala", "ann", self.ids, 1, 0, "http://192.168.1.2")
        command = self.out.remote_queue["display:sala"].get_nowait()
        self.assertEqual(command["type"], "load")
        self.assertIn(f"/api/music/media/{self.ids[1]}?t=", command["url"])
        token = command["url"].split("t=")[1].split("&")[0]
        self.assertTrue(tokens.verify("media", self.ids[1], token))
        self.assertEqual(view["state"], "playing")
        self.assertEqual(store.now_playing["source"], "library")
        self.assertEqual(store.now_playing["title"], view["track"]["title"])

    async def test_pause_seek_volume_stop_and_unknown_commands(self):
        await self.out.start("display:sala", "ann", self.ids, 0, 0, "http://h")
        self.assertEqual((await self.out.control("display:sala", "pause"))["state"], "paused")
        self.assertEqual((await self.out.control("display:sala", "seek", 30))["position"], 30)
        self.assertEqual((await self.out.control("display:sala", "volume", 5))["volume"], 1.0)
        self.assertEqual((await self.out.control("display:sala", "stop"))["state"], "stopped")
        self.assertEqual(store.now_playing, {})
        with self.assertRaises(ValueError):
            await self.out.control("display:sala", "explode")
        with self.assertRaises(KeyError):
            await self.out.control("cast:x", "pause")

    async def test_queue_advances_repeats_and_continues_with_similar_tracks(self):
        await self.out.start("display:sala", "ann", self.ids[:1], 0, 0, "http://h")
        session = self.out.sessions["display:sala"]
        view = await self.out.step(session, "http://h", 1, True)
        self.assertGreater(view["length"], 1)
        self.assertEqual(view["index"], 1)
        await self.out.control("display:sala", "repeat")
        self.assertEqual(session.repeat, "all")
        session.index = len(session.queue) - 1
        self.assertEqual((await self.out.step(session, "http://h", 1, True))["index"], 0)

    async def test_plays_are_counted_once_when_a_track_ends(self):
        await self.out.start("display:sala", "ann", self.ids, 0, 0, "http://h")
        first = self.ids[0]
        session = self.out.sessions["display:sala"]
        await self.out.step(session, "http://h", 1, True)
        self.assertEqual(catalog.track(first)["plays"], 1)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM history WHERE user='ann'"), 1)

    async def test_remote_report_ending_advances_the_queue(self):
        await self.out.start("display:sala", "ann", self.ids, 0, 0, "http://h")
        self.out.remote_report("display:sala", "playing", 0.6, False)
        self.assertAlmostEqual(self.out.sessions["display:sala"].position(), 0.6, delta=0.3)
        self.out.remote_report("display:sala", "playing", 0, True)
        await asyncio.sleep(0.05)
        self.assertEqual(self.out.sessions["display:sala"].index, 1)

    async def test_long_poll_returns_the_pending_command_or_nothing(self):
        self.out.remote_queue["display:sala"].put_nowait({"type": "pause"})
        self.assertEqual(await self.out.wait_command("display:sala", "Sala"), {"type": "pause"})
        with mock.patch("features.music.outputs.REMOTE_WAIT", 0.05):
            self.assertIsNone(await self.out.wait_command("display:sala", "Sala"))


class SharingTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        cls.public = TestClient(atena_supervisor.public)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def test_links_expose_only_what_was_shared_and_expire(self):
        self.filled()
        rosso = next(t for t in catalog.tracks() if t["title"] == "Rosso")
        luna = next(t for t in catalog.tracks() if t["title"] == "Luna")
        made = self.admin.post("/api/music/shares", json={"kind": "track", "ref": str(rosso["id"]), "hours": 2}, headers=HEADERS)
        self.assertEqual(made.status_code, 200, made.text)
        token = made.json()["token"]
        self.assertIn(f"/music/share/{token}", made.json()["url"])
        self.assertEqual(self.public.get(f"/music/share/{token}").status_code, 200)
        data = self.public.get(f"/api/music/share/{token}/data").json()
        self.assertEqual([t["title"] for t in data["tracks"]], ["Rosso"])
        self.assertEqual(self.public.get(f"/api/music/share/{token}/media/{rosso['id']}").status_code, 200)
        self.assertEqual(self.public.get(f"/api/music/share/{token}/media/{luna['id']}").status_code, 404)
        self.assertEqual(self.public.get("/api/music/share/inventato/data").status_code, 404)
        db.run("UPDATE shares SET expires=? WHERE token=?", (time.time() - 5, token))
        self.assertEqual(self.public.get(f"/api/music/share/{token}/data").status_code, 404)

    def test_revoking_and_brute_force_protection(self):
        self.filled()
        album = catalog.albums()[0]["album_key"]
        token = self.admin.post("/api/music/shares", json={"kind": "album", "ref": album}, headers=HEADERS).json()["token"]
        self.assertEqual(len(self.admin.get("/api/music/shares", headers=HEADERS).json()["shares"]), 1)
        self.assertEqual(self.admin.post(f"/api/music/shares/{token}/revoke", headers=HEADERS).status_code, 200)
        self.assertEqual(self.public.get(f"/api/music/share/{token}/data").status_code, 404)
        sharing._failures.clear()
        codes = [self.public.get(f"/api/music/share/guess{i}/data").status_code for i in range(sharing.FAIL_LIMIT + 3)]
        self.assertEqual(codes[-1], 429)
        sharing._failures.clear()

    def test_nothing_to_share_and_bad_kinds_are_refused(self):
        self.assertEqual(self.admin.post("/api/music/shares", json={"kind": "album", "ref": "nulla"}, headers=HEADERS).status_code, 400)
        self.assertEqual(self.admin.post("/api/music/shares", json={"kind": "etc", "ref": "1"}, headers=HEADERS).status_code, 400)

    def test_signed_media_links(self):
        self.filled()
        track = catalog.tracks()[0]
        url = f"/api/music/media/{track['id']}"
        self.assertEqual(self.public.get(url).status_code, 401)
        self.assertEqual(self.public.get(f"{url}?t={tokens.sign('media', track['id'])}").status_code, 200)
        self.assertEqual(self.public.get(f"{url}?t={tokens.sign('media', track['id'] + 1)}").status_code, 401)
        part = self.public.get(f"{url}?t={tokens.sign('media', track['id'])}", headers={"Range": "bytes=0-3"})
        self.assertEqual(part.status_code, 206)


class SubsonicTest(Base):
    PASSWORD = "segreta-lunga"

    @classmethod
    def setUpClass(cls):
        cls.public = TestClient(atena_supervisor.public)

    def setUp(self):
        super().setUp()
        write_env({"ATENA_MUSIC_SUBSONIC": "1", "ATENA_MUSIC_APP_PASSWORD": self.PASSWORD})
        self.addCleanup(lambda: write_env({"ATENA_MUSIC_SUBSONIC": "0", "ATENA_MUSIC_APP_PASSWORD": ""}))

    def call(self, method: str, **params):
        salt = "abc123"
        base = {"u": "Mario", "t": hashlib.md5((self.PASSWORD + salt).encode()).hexdigest(), "s": salt, "v": "1.16.1", "c": "test", "f": "json"}
        return self.public.get(f"/rest/{method}.view", params={**base, **params})

    def reply(self, method: str, **params) -> dict:
        return self.call(method, **params).json()["subsonic-response"]

    def test_authentication(self):
        self.assertEqual(self.reply("ping")["status"], "ok")
        bad = self.public.get("/rest/ping", params={"u": "x", "p": "sbagliata", "f": "json"}).json()["subsonic-response"]
        self.assertEqual((bad["status"], bad["error"]["code"]), ("failed", 40))
        plain = self.public.get("/rest/ping", params={"u": "x", "p": self.PASSWORD, "f": "json"}).json()["subsonic-response"]
        self.assertEqual(plain["status"], "ok")
        hexed = self.public.get("/rest/ping", params={"u": "x", "p": "enc:" + self.PASSWORD.encode().hex(), "f": "json"}).json()["subsonic-response"]
        self.assertEqual(hexed["status"], "ok")
        write_env({"ATENA_MUSIC_SUBSONIC": "0"})
        self.assertEqual(self.reply("ping")["error"]["code"], 50)

    def test_xml_is_the_default_format(self):
        text = self.public.get("/rest/ping", params={"u": "x", "p": self.PASSWORD}).text
        self.assertTrue(text.startswith("<?xml"))
        self.assertIn('status="ok"', text)

    def test_browsing_the_library(self):
        self.filled()
        artists = self.reply("getArtists")["artists"]["index"]
        names = [a["name"] for group in artists for a in (group["artist"] if isinstance(group["artist"], list) else [group["artist"]])]
        self.assertEqual(sorted(names), ["Mina", "Vasco"])
        album_id = next(a["id"] for g in artists for a in g["artist"] if a["name"] == "Vasco")
        artist = self.reply("getArtist", id=album_id)["artist"]
        self.assertEqual(artist["albumCount"], 1)
        album = self.reply("getAlbum", id=artist["album"][0]["id"])["album"]
        self.assertEqual([s["title"] for s in album["song"]], ["Rosso", "Blu"])
        self.assertEqual(album["song"][0]["suffix"], "wav")
        found = self.reply("search3", query="min")["searchResult3"]
        self.assertEqual(found["artist"][0]["name"], "Mina")
        self.assertEqual(self.reply("getAlbumList2", type="newest", size=5)["albumList2"]["album"][0]["songCount"] >= 1, True)
        self.assertEqual(self.reply("getAlbum", id="al-nulla")["error"]["code"], 70)

    def test_stream_star_scrobble_and_playlists(self):
        self.filled()
        song = catalog.tracks("title")[0]
        stream = self.call("stream", id=song["id"])
        self.assertEqual(stream.status_code, 200)
        self.assertEqual(self.call("stream", id=song["id"] + 999).json()["subsonic-response"]["error"]["code"], 70)
        self.assertEqual(self.reply("star", id=song["id"])["status"], "ok")
        liked = self.reply("getStarred2")["starred2"]["song"]
        self.assertEqual([s["id"] for s in liked], [str(song["id"])])
        self.assertEqual(self.reply("scrobble", id=song["id"])["status"], "ok")
        self.assertEqual(catalog.track(song["id"])["plays"], 1)
        made = self.reply("createPlaylist", name="Telefono", songId=song["id"])["playlist"]
        self.assertEqual(made["songCount"], 1)
        self.assertEqual(self.reply("getPlaylists")["playlists"]["playlist"][0]["name"], "Telefono")
        self.assertEqual(self.reply("deletePlaylist", id=made["id"])["status"], "ok")
        self.assertEqual(self.reply("getPlaylist", id=made["id"])["status"], "failed")

    def test_unknown_methods_fail_cleanly(self):
        self.assertEqual(self.reply("jukeboxControl")["status"], "failed")


class OutputApiTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        cls.display = TestClient(atena_supervisor.public)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def setUp(self):
        super().setUp()
        self.local = True
        patcher = mock.patch.object(access, "is_local", lambda request: self.local)
        patcher.start()
        self.addCleanup(patcher.stop)
        for target in (mock.patch.object(dlna, "discover", mock.AsyncMock(return_value=[])), mock.patch.object(Outputs, "safe_cast", mock.AsyncMock(return_value=[]))):
            target.start()
            self.addCleanup(target.stop)
        shared_outputs.devices.clear()
        shared_outputs.sessions.clear()
        shared_outputs.remote_queue.clear()
        self.addCleanup(lambda: setattr(store, "now_playing", {}))

    def test_display_registers_polls_and_reports(self):
        self.filled()
        with mock.patch("features.music.outputs.REMOTE_WAIT", 0.05):
            first = self.display.get("/api/music/out/poll?device=display:sala&name=Sala")
        self.assertEqual(first.status_code, 200)
        self.assertIsNone(first.json()["command"])
        listing = self.admin.get("/api/music/out", headers=HEADERS).json()
        self.assertEqual([d["id"] for d in listing["devices"]], ["display:sala"])
        ids = [t["id"] for t in catalog.tracks("title")]
        started = self.admin.post("/api/music/out/display:sala/play", json={"tracks": ids, "index": 0}, headers=HEADERS)
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["state"], "playing")
        command = self.display.get("/api/music/out/poll?device=display:sala&name=Sala").json()["command"]
        self.assertEqual(command["type"], "load")
        self.assertIn("/api/music/media/", command["url"])
        media = self.display.get(command["url"])
        self.assertEqual(media.status_code, 200)
        self.assertEqual(self.display.post("/api/music/out/report", json={"device": "display:sala", "state": "playing", "position": 0.3}).status_code, 200)
        state = self.admin.get("/api/music/out/display:sala", headers=HEADERS).json()
        self.assertEqual(state["state"], "playing")
        paused = self.admin.post("/api/music/out/display:sala/control", json={"action": "pause"}, headers=HEADERS)
        self.assertEqual(paused.json()["state"], "paused")

    def test_bad_requests_and_permissions(self):
        self.assertEqual(self.display.get("/api/music/out/poll?device=cast:x").status_code, 400)
        self.assertEqual(self.display.get("/api/music/out/poll?device=../x").status_code, 400)
        self.assertEqual(self.display.post("/api/music/out/report", json={"device": "bad"}).status_code, 400)
        self.assertEqual(self.admin.post("/api/music/out/display:nulla/play", json={"tracks": [1]}, headers=HEADERS).status_code, 404)
        shared_outputs.remote_beat("display:sala", "Sala")
        self.assertEqual(self.admin.post("/api/music/out/display:sala/play", json={"tracks": ["x"]}, headers=HEADERS).status_code, 400)
        self.assertEqual(self.admin.post("/api/music/out/display:sala/control", json={"action": "pause"}, headers=HEADERS).status_code, 400)
        self.local = False
        self.assertEqual(self.display.get("/api/music/out/poll?device=display:sala").status_code, 401)
        self.assertEqual(self.display.post("/api/music/out/report", json={"device": "display:sala"}).status_code, 401)
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.get("/api/music/out", headers=HEADERS).status_code, 401)

    def test_library_overview_carries_the_preferences_and_lookup_restores_a_queue(self):
        self.filled()
        prefs = self.admin.get("/api/music/library", headers=HEADERS).json()["prefs"]
        for key in ("crossfade", "radio", "lyrics", "cast", "share", "subsonic"):
            self.assertIn(key, prefs)
        ids = [t["id"] for t in catalog.tracks("title")]
        found = self.admin.get(f"/api/music/tracks/lookup?ids={ids[1]},{ids[0]},999,zz", headers=HEADERS).json()["tracks"]
        self.assertEqual([t["id"] for t in found], [ids[1], ids[0]])

    def test_app_password_flow(self):
        state = self.admin.post("/api/music/app", json={"enabled": True}, headers=HEADERS).json()
        self.assertTrue(state["enabled"])
        self.assertGreaterEqual(len(state["password"]), 8)
        again = self.admin.post("/api/music/app", json={"enabled": True}, headers=HEADERS).json()
        self.assertEqual(again["password"], state["password"])
        fresh = self.admin.post("/api/music/app", json={"enabled": True, "regenerate": True}, headers=HEADERS).json()
        self.assertNotEqual(fresh["password"], state["password"])
        off = self.admin.post("/api/music/app", json={"enabled": False}, headers=HEADERS).json()
        self.assertEqual((off["enabled"], off["password"]), (False, ""))
        write_env({"ATENA_MUSIC_APP_PASSWORD": ""})


if __name__ == "__main__":
    unittest.main()

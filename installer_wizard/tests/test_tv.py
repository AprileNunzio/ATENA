import asyncio
import tempfile
import unittest
from pathlib import Path

from sealed import SealedFile

from features.nodes.inbox import Inbox
from features.tv import m3u, relay, targets
from features.tv.store import TvStore

PLAYLIST = """#EXTM3U url-tvg="http://epg.example/x.xml"
#EXTINF:-1 tvg-id="rai1.it" tvg-logo="http://logo.example/rai1.png" group-title="Italia",Rai 1 HD
http://iptv.example/live/user/pass/1.m3u8
#EXTINF:-1 group-title="Italia",Rai 10
http://iptv.example/live/user/pass/10.ts
#EXTINF:-1,Bad <script>
javascript:alert(1)
#EXTINF:-1 tvg-logo="ftp://x",Canale 5 (backup)
https://cdn.example/c5/index.m3u8
"""


class M3uTest(unittest.TestCase):
    def test_parse_skips_unsafe_and_keeps_metadata(self):
        rows = m3u.parse(PLAYLIST)
        self.assertEqual([r["name"] for r in rows], ["Rai 1 HD", "Rai 10", "Canale 5 (backup)"])
        self.assertEqual((rows[0]["group"], rows[0]["tvg_id"], rows[0]["logo"]), ("Italia", "rai1.it", "http://logo.example/rai1.png"))
        self.assertEqual(rows[2]["logo"], "")

    def test_not_a_playlist(self):
        with self.assertRaises(m3u.PlaylistError):
            m3u.parse("<html>login</html>")

    def test_find_respects_numbers_and_quality_tags(self):
        rows = m3u.parse(PLAYLIST)
        self.assertEqual(m3u.find(rows, "metti rai 1 sul pc")["name"], "Rai 1 HD")
        self.assertEqual(m3u.find(rows, "guarda rai 10")["name"], "Rai 10")
        self.assertEqual(m3u.find(rows, "canale 5")["name"], "Canale 5 (backup)")
        self.assertIsNone(m3u.find(rows, "accendi la luce"))


class RelayTest(unittest.TestCase):
    def test_segment_urls_are_signed(self):
        path = relay.encode("abcd", "http://cdn.example/s1.ts", "tok")
        q = dict(p.split("=", 1) for p in path.split("?", 1)[1].split("&"))
        self.assertEqual(relay.decode("abcd", q["u"], q["s"]), "http://cdn.example/s1.ts")
        with self.assertRaises(relay.RelayError):
            relay.decode("other", q["u"], q["s"])

    def test_rewrite_keeps_tags_and_blocks_internal_hosts(self):
        text = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\nseg1.ts\nhttp://192.168.1.1/admin\n'
        out = relay.rewrite(text, "http://cdn.example/live/index.m3u8", "abcd", "tok", "http://cdn.example/live/index.m3u8")
        lines = out.splitlines()
        self.assertTrue(lines[1].startswith("#EXT-X-KEY:METHOD=AES-128,URI=\"/api/tv/seg/abcd?"))
        self.assertTrue(lines[2].startswith("/api/tv/seg/abcd?"))
        self.assertEqual(lines[3], "#rimosso")

    def test_private_origin_may_use_private_segments(self):
        self.assertTrue(relay.allowed("http://192.168.1.5/live.m3u8", "http://192.168.1.5/seg.ts"))
        self.assertFalse(relay.allowed("http://cdn.example/a.m3u8", "http://127.0.0.1/x"))
        self.assertFalse(relay.allowed("http://cdn.example/a.m3u8", "file:///etc/passwd"))


class StoreTest(unittest.TestCase):
    def test_add_find_favorite_remove(self):
        with tempfile.TemporaryDirectory() as root:
            store = TvStore(SealedFile(Path(root) / "tv.vault", Path(root) / "tv.key"))
            entry = store.add("Prova", text=PLAYLIST)
            self.assertEqual(entry["count"], 3)
            self.assertNotIn("url", store.playlists()[0])
            ch = store.find("rai 1")
            store.set_favorite(ch["id"], True)
            again = TvStore(SealedFile(Path(root) / "tv.vault", Path(root) / "tv.key"))
            self.assertEqual(again.favorites(), [ch["id"]])
            self.assertNotIn(b"iptv.example", (Path(root) / "tv.vault").read_bytes())
            again.remove(entry["id"])
            self.assertEqual(again.channels(), [])


class TargetTest(unittest.TestCase):
    ROWS = [{"id": "display", "kind": "display", "name": "Schermi di Atena", "online": True},
            {"id": "pc:studio-pc", "kind": "pc", "name": "Studio PC", "online": True},
            {"id": "cast:abc", "kind": "cast", "name": "Salotto TV", "online": True}]

    def test_resolve_phrases(self):
        self.assertEqual(targets.resolve("metti rai 1 sul pc", self.ROWS)["id"], "pc:studio-pc")
        self.assertEqual(targets.resolve("rai 1 sulla salotto tv", self.ROWS)["id"], "cast:abc")
        self.assertEqual(targets.resolve("rai 1 sul chromecast", self.ROWS)["id"], "cast:abc")
        self.assertIsNone(targets.resolve("metti rai 1", self.ROWS))

    def test_target_ids_are_validated(self):
        for bad in ("pc:../../x", "shell:rm", "display:999"):
            self.assertFalse(targets.TARGET.match(bad), bad)


class InboxTest(unittest.IsolatedAsyncioTestCase):
    async def test_long_poll_wakes_on_push(self):
        box = Inbox()
        waiter = asyncio.create_task(box.wait("pc1", 2))
        await asyncio.sleep(0.05)
        box.push("pc1", {"type": "tv", "url": "http://x/tv/watch?c=1"})
        self.assertEqual((await waiter)[0]["type"], "tv")
        self.assertEqual(await box.wait("pc1", 0.05), [])


if __name__ == "__main__":
    unittest.main()

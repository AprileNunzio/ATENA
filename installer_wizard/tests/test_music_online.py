import asyncio
import unittest
from unittest import mock

import httpx

from config import write_env
from features.music import catalog, covers, enrich, layout, lyrics, lyrics_store, organizer, renamer, scanner, sources
from features.music.db import db
from features.music.service import LibraryService
from tests.test_music_library import Base, age, make_wav

ITUNES = {"results": [
    {"trackName": "Back In Black", "artistName": "AC/DC", "collectionName": "Back In Black", "releaseDate": "1980-07-25T07:00:00Z",
     "primaryGenreName": "Rock", "artworkUrl100": "https://img.example/100x100bb.jpg"},
    {"trackName": "Altro", "artistName": "Qualcuno", "collectionName": "X", "releaseDate": "2001-01-01T00:00:00Z"}]}
IMAGE = b"\xff\xd8" + b"x" * 2000


REAL_CLIENT = httpx.AsyncClient


def transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "itunes.apple.com" in str(request.url):
            return httpx.Response(200, json=ITUNES)
        return httpx.Response(200, content=IMAGE)
    return httpx.MockTransport(handler)


class OnlineBase(Base):
    def setUp(self):
        super().setUp()
        real = httpx.AsyncClient
        patcher = mock.patch.object(sources.httpx, "AsyncClient", lambda **kw: real(transport=transport(), **kw))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: write_env({"ATENA_MUSIC_COVERS": "1", "ATENA_MUSIC_LYRICS": "1"}))

    def unknown_album_track(self) -> dict:
        path = make_wav(self.inbox / "AC DC - Back in Black.wav")
        age(path)
        organizer.sweep()
        scanner.scan()
        return catalog.tracks()[0]


class LyricsStoreTest(OnlineBase):
    def test_synced_and_plain_lyrics_are_written_next_to_the_song(self):
        self.filled()
        synced = {"synced": [{"t": 1.5, "text": "uno"}, {"t": 65.25, "text": "due"}]}
        text = lyrics_store.to_lrc(synced)
        self.assertEqual([(l["t"], l["text"]) for l in lyrics._parse(text)], [(1.5, "uno"), (65.25, "due")])
        self.assertEqual(lyrics_store.to_lrc({"plain": "ciao\nmondo"}), "ciao\nmondo\n")

        async def fake(title, artist, album="", duration=None):
            return synced if title == "Rosso" else {"plain": "solo testo"} if title == "Blu" else {}
        with mock.patch.object(lyrics, "fetch", fake):
            saved = asyncio.run(lyrics_store.fetch_missing(10))
            again = asyncio.run(lyrics_store.fetch_missing(10))
        self.assertEqual((saved, again), (2, 0))
        rosso = next(layout.library().rglob("*Rosso*.wav")).with_suffix(".lrc")
        self.assertTrue(rosso.is_file())
        self.assertEqual(len(list(layout.library().rglob("*.lrc"))), 2)

    def test_existing_lyrics_are_kept_and_the_limit_is_respected(self):
        self.filled()
        existing = next(layout.library().rglob("*Rosso*.wav")).with_suffix(".lrc")
        existing.write_text("[00:01.00]mio\n", encoding="utf-8")
        calls = []

        async def fake(title, artist, album="", duration=None):
            calls.append(title)
            return {"plain": "x"}
        with mock.patch.object(lyrics, "fetch", fake):
            asyncio.run(lyrics_store.fetch_missing(1))
        self.assertEqual(len(calls), 1)
        self.assertEqual(existing.read_text(encoding="utf-8"), "[00:01.00]mio\n")


class EnrichTest(OnlineBase):
    def test_unknown_album_is_filled_in_with_cover_year_and_genre(self):
        track = self.unknown_album_track()
        self.assertEqual((track["album"], track["artist"]), ("Singoli", "AC DC"))
        self.assertTrue((layout.library() / "AC DC" / "Singoli").is_dir())
        self.assertEqual(asyncio.run(enrich.run()), 1)
        found = catalog.track(track["id"])
        self.assertEqual((found["album"], found["year"], found["genre"]), ("Back In Black", 1980, "Rock"))
        self.assertTrue(found["cover"])
        self.assertTrue(covers.stored(found["album_key"]).is_file())
        self.assertEqual(catalog.search("black")["albums"][0]["album"], "Back In Black")
        renamer.run()
        self.assertTrue((layout.library() / "AC DC" / "Back In Black" / "AC DC - Back in Black (1980).wav").is_file())
        self.assertFalse((layout.library() / "AC DC" / "Singoli").exists())
        self.assertEqual(asyncio.run(enrich.run()), 0)

    def test_a_different_song_is_never_accepted(self):
        self.assertFalse(sources.match("Hells Bells", "AC DC", "Back In Black", "AC/DC"))
        self.assertFalse(sources.match("Back in Black", "Mina", "Back In Black", "AC/DC"))
        self.assertTrue(sources.match("Back in Black", "AC DC", "Back In Black", "AC/DC"))
        self.assertFalse(sources.match("", "AC DC", "Back In Black", "AC/DC"))

    def test_tracks_with_known_albums_are_left_alone(self):
        self.filled()
        self.assertEqual(asyncio.run(enrich.run()), 0)


class SourcesTest(OnlineBase):
    def run_search(self, artist: str, title: str, handler):
        async def go():
            async with REAL_CLIENT(transport=httpx.MockTransport(handler)) as client:
                return await sources.search(client, artist, title)
        return asyncio.run(go())

    def test_the_swapped_order_of_a_file_name_is_understood(self):
        found = self.run_search("Back In Black", "AC DC", lambda r: httpx.Response(200, json=ITUNES))
        self.assertEqual((found["artist"], found["title"], found["album"], found["year"]), ("AC/DC", "Back In Black", "Back In Black", 1980))

    def test_other_services_are_used_when_the_first_knows_nothing_and_data_is_merged(self):
        def handler(request):
            url = str(request.url)
            if "itunes" in url:
                return httpx.Response(200, json={"results": []})
            if "deezer" in url:
                return httpx.Response(200, json={"data": [{"title": "Back In Black", "duration": 255, "artist": {"name": "AC/DC"},
                                                           "album": {"title": "Back In Black", "cover_xl": "https://img.example/deezer.jpg"}}]})
            return httpx.Response(200, json={"recordings": [{"title": "Back in Black", "length": 255000, "artist-credit": [{"name": "AC/DC"}],
                                                             "releases": [{"title": "Back in Black", "date": "1980-07-25", "release-group": {"primary-type": "Album"}}]}]})
        found = self.run_search("AC DC", "Back in Black (Official Video) [HD]", handler)
        self.assertEqual((found["album"], found["year"], found["cover"]), ("Back In Black", 1980, "https://img.example/deezer.jpg"))
        self.assertEqual(found["source"], "Deezer")

    def test_nothing_found_and_broken_answers(self):
        self.assertIsNone(self.run_search("Qualcuno", "Brano mai esistito", lambda r: httpx.Response(200, json={})))
        self.assertIsNone(self.run_search("Qualcuno", "Brano", lambda r: httpx.Response(500, text="boom")))
        self.assertIsNone(self.run_search("", "Brano", lambda r: httpx.Response(200, json=ITUNES)))
        self.assertEqual(sources.clean_query("Back In Black (Official Video) [HD] - lyrics"), "Back In Black")


class ServiceOnlineTest(OnlineBase):
    def test_new_tracks_trigger_the_online_search_and_the_settings_switch_it_off(self):
        self.unknown_album_track()

        async def fake(title, artist, album="", duration=None):
            return {"plain": "testo"}
        service = LibraryService()
        with mock.patch.object(lyrics, "fetch", fake):
            asyncio.run(service.online())
        self.assertEqual(len(list(layout.library().rglob("*.lrc"))), 1)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tracks WHERE album='Back In Black'"), 1)
        write_env({"ATENA_MUSIC_COVERS": "0", "ATENA_MUSIC_LYRICS": "0"})
        for lrc in layout.library().rglob("*.lrc"):
            lrc.unlink()
        db.run("DELETE FROM lookups")
        with mock.patch.object(lyrics, "fetch", fake):
            asyncio.run(service.online())
        self.assertEqual(list(layout.library().rglob("*.lrc")), [])


if __name__ == "__main__":
    unittest.main()

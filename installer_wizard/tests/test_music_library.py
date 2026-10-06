import os
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

import atena_supervisor
from features.music import catalog, id3, layout, listening, mixes, organizer, playlists, scanner, stream, tags, tokens
from features.music.db import db
from features.shares import archive

HEADERS = {"X-Atena-Request": "1"}


def make_wav(path: Path, seconds: float = 1.0, title: str = "", artist: str = "", album: str = "", genre: str = "", year: str = "", track: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * int(8000 * seconds))
    if title or artist:
        id3.write_wav(path, {"title": title, "artist": artist, "album": album, "genre": genre, "year": year, "track_no": track})
    return path


def age(path: Path, seconds: float = 120) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "condivisa"
        patches = [mock.patch.object(archive, "ROOT", self.root), mock.patch.object(layout, "DB_FILE", self.tmp / "music.db"),
                   mock.patch.object(tokens, "SECRET_FILE", self.tmp / "secret")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        db.close()
        db.path = None
        self.addCleanup(db.close)
        archive.ensure()
        self.inbox = layout.inbox()

    def drop(self, name: str, **info) -> Path:
        path = make_wav(self.inbox / name, **info)
        age(path)
        return path

    def filled(self) -> None:
        self.drop("a.wav", title="Rosso", artist="Vasco", album="Blasco", genre="Rock", year="1990", track="1/9")
        self.drop("b.wav", title="Blu", artist="Vasco", album="Blasco", genre="Rock", year="1990", track="2/9")
        self.drop("c.wav", title="Luna", artist="Mina", album="Mille", genre="Pop", year="1975", track="1")
        organizer.sweep()
        scanner.scan()


class TagsTest(Base):
    def test_reads_embedded_tags_and_duration(self):
        path = make_wav(self.tmp / "x.wav", 2.0, "Titolo", "Artista", "Album", "Jazz", "2001-05-01", "4/12")
        info = tags.read(path)
        self.assertEqual((info["title"], info["artist"], info["album"], info["genre"]), ("Titolo", "Artista", "Album", "Jazz"))
        self.assertEqual((info["year"], info["track_no"]), (2001, 4))
        self.assertAlmostEqual(info["duration"], 2.0, places=1)

    def test_structural_folders_are_never_taken_for_artist_or_album(self):
        for place in ("06 Musica/Da smistare", "srv/atena/condivisa/06 Musica/Da smistare", "condivisa/06 Musica"):
            path = self.tmp / place / "Canzone.wav"
            info = tags.from_path(path)
            self.assertNotIn("album", info, place)
            self.assertEqual(info["artist"], "", place)
        kept = tags.from_path(self.tmp / "06 Musica" / "Libreria" / "Queen" / "Greatest Hits" / "01 - Bohemian.wav")
        self.assertEqual((kept["artist"], kept["album"], kept["track_no"]), ("Queen", "Greatest Hits", 1))
        inbox = tags.from_path(self.tmp / "06 Musica" / "Da smistare" / "Pink Floyd" / "The Wall" / "x.wav")
        self.assertEqual((inbox["artist"], inbox["album"]), ("Pink Floyd", "The Wall"))

    def test_untagged_files_fall_back_to_the_file_name(self):
        path = make_wav(self.tmp / "Lucio Dalla - Caruso.wav")
        info = tags.read(path)
        self.assertEqual((info["artist"], info["title"]), ("Lucio Dalla", "Caruso"))
        numbered = make_wav(self.tmp / "07 - Ciao.wav")
        self.assertEqual((tags.read(numbered)["track_no"], tags.read(numbered)["title"]), (7, "Ciao"))

    def test_broken_files_never_raise(self):
        bad = self.tmp / "rotto.mp3"
        bad.write_bytes(b"non e' audio")
        self.assertEqual(tags.read(bad)["title"], "rotto")


class OrganizerTest(Base):
    def test_files_move_into_artist_album_folders(self):
        self.drop("a.wav", title="Rosso", artist="Vasco", album="Blasco", track="1")
        result = organizer.sweep()
        self.assertEqual(result["moved"], 1)
        self.assertTrue((layout.library() / "Vasco" / "Blasco" / "01 - Vasco - Rosso.wav").is_file())
        self.assertEqual(list(layout.inbox().iterdir()), [])

    def test_fresh_files_are_left_alone_while_they_are_still_being_copied(self):
        make_wav(self.inbox / "nuovo.wav", title="Nuovo", artist="Qualcuno")
        self.assertEqual(organizer.sweep()["moved"], 0)
        self.assertTrue((self.inbox / "nuovo.wav").exists())

    def test_exact_duplicates_go_to_quarantine_and_names_stay_safe(self):
        self.drop("a.wav", title="Brano", artist="A/B", album="C:D")
        organizer.sweep()
        self.drop("b.wav", title="Brano", artist="A/B", album="C:D")
        result = organizer.sweep()
        self.assertEqual(result["duplicates"], 1)
        self.assertTrue(any(layout.inbox().joinpath(organizer.DUPLICATES).iterdir()))
        found = list(layout.library().rglob("*.wav"))
        self.assertEqual(len(found), 1)
        self.assertTrue(layout.inside(layout.library(), found[0]))

    def test_pending_tells_the_service_when_there_is_something_to_sort(self):
        self.assertFalse(organizer.pending())
        make_wav(self.inbox / "nuovo.wav", title="Nuovo", artist="Qualcuno")
        self.assertTrue(organizer.pending())

    def test_the_service_wakes_up_by_itself_when_a_file_arrives(self):
        import asyncio
        from features.music.service import LibraryService
        service = LibraryService()

        async def scenario():
            with mock.patch("features.music.service.WATCH_EVERY", 0.05):
                task = asyncio.create_task(service.idle())
                await asyncio.sleep(0.15)
                self.assertFalse(task.done())
                make_wav(self.inbox / "arrivato.wav", title="Arrivato", artist="Qualcuno")
                await asyncio.wait_for(task, 2)
        asyncio.run(scenario())

    def test_files_already_put_in_a_structural_folder_are_fixed_by_a_manual_check(self):
        wrong = make_wav(layout.library() / "AC DC" / "06 Musica" / "AC DC - Back in Black.wav")
        age(wrong)
        result = organizer.sweep(True)
        self.assertEqual(result["fixed"], 1)
        self.assertEqual(result["moved"], 1)
        self.assertFalse((layout.library() / "AC DC" / "06 Musica").exists())
        self.assertTrue((layout.library() / "AC DC" / "Singoli" / "AC DC - Back in Black.wav").is_file())

    def test_loose_files_in_the_music_root_are_sorted_too(self):
        path = make_wav(layout.root() / "sciolto.wav", title="Sciolto", artist="Tizio", album="Disco")
        age(path)
        self.assertEqual(organizer.sweep()["moved"], 1)


class CatalogTest(Base):
    def test_scan_indexes_updates_and_removes(self):
        self.filled()
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tracks"), 3)
        again = scanner.scan()
        self.assertEqual((again["added"], again["updated"]), (0, 0))
        victim = next(layout.library().rglob("*Luna*"))
        victim.unlink()
        self.assertEqual(scanner.scan()["removed"], 1)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tracks"), 2)

    def test_search_matches_prefixes_accents_and_groups_results(self):
        self.filled()
        found = catalog.search("vas bla")
        self.assertEqual({t["title"] for t in found["tracks"]}, {"Rosso", "Blu"})
        self.assertEqual([a["album"] for a in found["albums"]], ["Blasco"])
        self.assertEqual(catalog.search("MIN")["artists"][0]["artist"], "Mina")
        self.assertEqual(catalog.search("   ")["tracks"], [])

    def test_browsing_albums_artists_genres_decades(self):
        self.filled()
        self.assertEqual({a["album"] for a in catalog.albums()}, {"Blasco", "Mille"})
        album = catalog.album(catalog.albums()[0]["album_key"])
        self.assertTrue(album["tracks"])
        self.assertEqual({a["artist"] for a in catalog.artists()}, {"Vasco", "Mina"})
        self.assertEqual({g["genre"] for g in catalog.genres()}, {"Rock", "Pop"})
        self.assertEqual({d["decade"] for d in catalog.decades()}, {1990, 1970})
        self.assertEqual(catalog.stats()["tracks"], 3)

    def test_sort_and_limits_are_sanitised(self):
        self.filled()
        self.assertEqual(len(catalog.tracks("drop table", "abc", "x")), 3)
        self.assertEqual(len(catalog.tracks("title", 2)), 2)
        self.assertEqual(catalog.tracks("title")[0]["title"], "Blu")

    def test_edit_updates_the_index_and_regroups_albums(self):
        from features.music.api_library import apply_edit
        self.filled()
        luna = next(t for t in catalog.tracks() if t["title"] == "Luna")
        self.assertEqual(apply_edit(luna["id"], {"album": "Nuovo disco", "genre": "Soul"}, "track"), 1)
        self.assertEqual(catalog.track(luna["id"])["album"], "Nuovo disco")
        self.assertEqual(catalog.search("Nuovo")["albums"][0]["album"], "Nuovo disco")
        with self.assertRaises(HTTPException):
            apply_edit(luna["id"], {}, "track")


class ListeningTest(Base):
    def test_likes_ratings_and_play_counts_are_per_user(self):
        self.filled()
        a, b = catalog.tracks()[:2]
        self.assertTrue(listening.like("ann", a["id"], True))
        self.assertFalse(listening.like("ann", 9999, True))
        self.assertEqual([t["id"] for t in listening.liked("ann")], [a["id"]])
        self.assertEqual(listening.liked("bob"), [])
        listening.rate("ann", b["id"], 9)
        self.assertEqual(catalog.track(b["id"], "ann")["stars"], 5)
        self.assertEqual(catalog.track(b["id"], "bob")["stars"], 0)
        self.assertFalse(listening.played("ann", a["id"], 0.2, False))
        self.assertTrue(listening.played("ann", a["id"], 30, False))
        self.assertTrue(listening.played("ann", b["id"], 0.5, True))
        self.assertEqual(catalog.track(a["id"])["plays"], 1)
        self.assertEqual({t["id"] for t in listening.recent("ann")}, {a["id"], b["id"]})
        summary = listening.summary("ann")
        self.assertEqual(summary["plays"], 2)
        self.assertTrue(summary["artists"])

    def test_removed_tracks_disappear_from_likes_and_playlists(self):
        self.filled()
        a = catalog.tracks()[0]
        listening.like("ann", a["id"], True)
        pid = playlists.create("ann", "Mia")
        playlists.add(pid, "ann", [a["id"]])
        Path(layout.root() / db.row("SELECT path FROM tracks WHERE id=?", (a["id"],))["path"]).unlink()
        scanner.scan()
        self.assertEqual(listening.liked("ann"), [])
        self.assertEqual(playlists.get(pid, "ann")["tracks"], [])


class PlaylistTest(Base):
    def test_manual_playlists_can_be_filled_reordered_and_trimmed(self):
        self.filled()
        ids = [t["id"] for t in catalog.tracks("title")]
        pid = playlists.create("ann", "Viaggio")
        self.assertEqual(playlists.add(pid, "ann", ids + [99999]), 3)
        playlists.reorder(pid, "ann", 0, 2)
        order = [t["id"] for t in playlists.get(pid, "ann")["tracks"]]
        self.assertEqual(order, [ids[1], ids[2], ids[0]])
        playlists.remove(pid, "ann", [0])
        self.assertEqual(len(playlists.get(pid, "ann")["tracks"]), 2)
        self.assertFalse(playlists.reorder(pid, "ann", 0, 9))

    def test_other_users_cannot_edit_but_can_read_shared_ones(self):
        self.filled()
        pid = playlists.create("ann", "Privata")
        self.assertIsNone(playlists.get(pid, "bob"))
        self.assertFalse(playlists.delete(pid, "bob"))
        playlists.rename(pid, "ann", "Privata", shared=True)
        self.assertIsNotNone(playlists.get(pid, "bob"))
        with self.assertRaises(ValueError):
            playlists.add(pid, "bob", [1])
        self.assertEqual([p["mine"] for p in playlists.listing("bob")], [False])

    def test_smart_playlists_follow_their_rules(self):
        self.filled()
        rock = playlists.create("ann", "Rock", "smart", {"genre": "Rock", "sort": "title"})
        self.assertEqual([t["title"] for t in playlists.get(rock, "ann")["tracks"]], ["Blu", "Rosso"])
        old = playlists.create("ann", "Vecchi", "smart", {"year_to": 1980})
        self.assertEqual([t["title"] for t in playlists.get(old, "ann")["tracks"]], ["Luna"])
        never = playlists.create("ann", "Nuovi", "smart", {"never_played": True, "evil": "1; DROP TABLE tracks"})
        self.assertEqual(len(playlists.get(never, "ann")["tracks"]), 3)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tracks"), 3)

    def test_export_writes_a_relative_m3u_into_the_playlist_folder(self):
        self.filled()
        pid = playlists.create("ann", "Per auto")
        playlists.add(pid, "ann", [t["id"] for t in catalog.tracks()])
        target = playlists.export(pid, "ann")
        self.assertEqual(target.parent, layout.playlists())
        text = target.read_text(encoding="utf-8")
        self.assertIn("#EXTM3U", text)
        self.assertIn("../Libreria/", text)

    def test_limits(self):
        with self.assertRaises(ValueError):
            playlists.create("ann", "  ")


class MixesTest(Base):
    def test_mixes_radio_and_home(self):
        self.filled()
        rock = mixes.mix("genre:Rock", "ann")
        self.assertEqual({t["title"] for t in rock}, {"Rosso", "Blu"})
        self.assertEqual(mixes.mix("evil:x", "ann"), [])
        seed = next(t for t in catalog.tracks() if t["title"] == "Rosso")
        follow = mixes.similar(seed["id"], "ann", [])
        self.assertNotIn(seed["id"], [t["id"] for t in follow])
        self.assertEqual(follow[0]["title"], "Blu")
        self.assertEqual(mixes.similar(99999, "ann", []), [])
        home = mixes.home("ann")
        for key in ("recent", "added", "random", "popular", "mixes", "stats"):
            self.assertIn(key, home)
        self.assertTrue(any(m["id"].startswith("artist:") for m in home["mixes"]))


class StreamTest(Base):
    def test_range_parsing(self):
        self.assertIsNone(stream.parse_range(None, 100))
        self.assertEqual(stream.parse_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(stream.parse_range("bytes=90-", 100), (90, 99))
        self.assertEqual(stream.parse_range("bytes=-10", 100), (90, 99))
        for bad in ("bytes=200-300", "bytes=5-2", "items=1-2", "bytes=-"):
            with self.assertRaises(HTTPException):
                stream.parse_range(bad, 100)

    def test_tokens_expire_and_are_bound_to_their_reference(self):
        token = tokens.sign("media", 7, 60)
        self.assertTrue(tokens.verify("media", 7, token))
        self.assertFalse(tokens.verify("media", 8, token))
        self.assertFalse(tokens.verify("art", 7, token))
        self.assertFalse(tokens.verify("media", 7, tokens.sign("media", 7, -5)))
        self.assertFalse(tokens.verify("media", 7, "garbage"))
        stamp, sig = token.split(".")
        self.assertFalse(tokens.verify("media", 7, f"{int(stamp) + 9999}.{sig}"))


class ApiTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def test_browsing_endpoints_and_streaming_with_ranges(self):
        self.filled()
        listing = self.admin.get("/api/music/tracks?sort=title", headers=HEADERS).json()
        self.assertEqual(listing["total"], 3)
        track = listing["tracks"][0]
        full = self.admin.get(f"/api/music/stream/{track['id']}", headers=HEADERS)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full.headers["accept-ranges"], "bytes")
        part = self.admin.get(f"/api/music/stream/{track['id']}", headers={**HEADERS, "Range": "bytes=0-9"})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.content, full.content[:10])
        self.assertEqual(self.admin.get("/api/music/stream/999", headers=HEADERS).status_code, 404)
        self.assertEqual(self.admin.get("/api/music/search?q=mina", headers=HEADERS).json()["artists"][0]["artist"], "Mina")
        self.assertEqual(len(self.admin.get("/api/music/artists", headers=HEADERS).json()["artists"]), 2)
        self.assertIn("mixes", self.admin.get("/api/music/home", headers=HEADERS).json())

    def test_requires_login(self):
        anon = TestClient(atena_supervisor.admin)
        for path in ("/api/music/tracks", "/api/music/stream/1", "/api/music/home", "/api/music/playlists"):
            self.assertEqual(anon.get(path, headers=HEADERS).status_code, 401, path)

    def test_playlists_over_http(self):
        self.filled()
        ids = [t["id"] for t in self.admin.get("/api/music/tracks", headers=HEADERS).json()["tracks"]]
        made = self.admin.post("/api/music/playlists", json={"name": "Sera", "tracks": ids[:2]}, headers=HEADERS)
        self.assertEqual(made.status_code, 200, made.text)
        pid = made.json()["id"]
        detail = self.admin.get(f"/api/music/playlists/{pid}", headers=HEADERS).json()
        self.assertEqual(len(detail["tracks"]), 2)
        self.assertEqual(self.admin.post(f"/api/music/playlists/{pid}/add", json={"tracks": ["x"]}, headers=HEADERS).status_code, 400)
        self.assertEqual(self.admin.post(f"/api/music/playlists/{pid}/move", json={"from": 0, "to": 1}, headers=HEADERS).status_code, 200)
        self.assertEqual(self.admin.get(f"/api/music/playlists/{pid}/m3u", headers=HEADERS).status_code, 200)
        self.assertEqual(self.admin.post(f"/api/music/playlists/{pid}/export", headers=HEADERS).json()["file"], "Sera.m3u8")
        self.assertEqual(self.admin.post(f"/api/music/playlists/{pid}/delete", headers=HEADERS).status_code, 200)
        self.assertEqual(self.admin.get(f"/api/music/playlists/{pid}", headers=HEADERS).status_code, 404)

    def test_upload_goes_to_the_inbox_and_rejects_bad_files(self):
        source = make_wav(self.tmp / "u.wav", title="Caricato", artist="Io", album="Mio")
        ok = self.admin.put("/api/music/upload?name=u.wav", content=source.read_bytes(), headers=HEADERS)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue((layout.inbox() / "u.wav").is_file())
        self.assertEqual(self.admin.put("/api/music/upload?name=virus.exe", content=b"MZ", headers=HEADERS).status_code, 415)
        self.assertEqual(self.admin.put("/api/music/upload?name=../../x.wav", content=b"RIFF", headers=HEADERS).status_code, 200)
        self.assertFalse((self.tmp / "x.wav").exists())

    def test_check_now_sorts_and_indexes_at_once_even_when_the_machine_is_busy(self):
        from features.governor.service import governor
        self.drop("a.wav", title="Rosso", artist="Vasco", album="Blasco", track="1")
        make_wav(self.inbox / "ancora-in-copia.wav", title="Lento", artist="Vasco", album="Blasco")
        with mock.patch.object(governor, "busy", return_value=True):
            r = self.admin.post("/api/music/scan", json={}, headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        result = r.json()["result"]
        self.assertEqual(result["sorted"]["moved"], 1)
        self.assertEqual(result["sorted"]["waiting"], 1)
        self.assertEqual(result["scan"]["added"], 1)
        self.assertEqual(self.admin.get("/api/music/tracks", headers=HEADERS).json()["total"], 1)
        self.assertTrue((layout.library() / "Vasco" / "Blasco" / "01 - Vasco - Rosso.wav").is_file())

    def test_manual_check_reports_why_a_file_was_not_sorted(self):
        self.drop("a.wav", title="Rosso", artist="Vasco", album="Blasco")
        with mock.patch.object(organizer, "move", side_effect=OSError("permesso negato")):
            result = self.admin.post("/api/music/scan", json={}, headers=HEADERS).json()["result"]
        self.assertEqual(result["sorted"]["failed"], 1)
        self.assertIn("permesso negato", result["errors"][0])
        self.assertEqual(self.admin.post("/api/music/scan", json={}, headers=HEADERS).json()["result"]["sorted"]["moved"], 1)

    def test_like_rate_played_and_trash(self):
        self.filled()
        track = self.admin.get("/api/music/tracks", headers=HEADERS).json()["tracks"][0]
        base = f"/api/music/tracks/{track['id']}"
        self.assertTrue(self.admin.post(f"{base}/like", json={"on": True}, headers=HEADERS).json()["liked"])
        self.assertEqual(self.admin.post(f"{base}/rate", json={"stars": 4}, headers=HEADERS).json()["stars"], 4)
        self.assertTrue(self.admin.post(f"{base}/played", json={"seconds": 40}, headers=HEADERS).json()["counted"])
        self.assertEqual(self.admin.get("/api/music/tracks?liked=true", headers=HEADERS).json()["tracks"][0]["id"], track["id"])
        self.assertEqual(self.admin.post(f"{base}/trash", headers=HEADERS).status_code, 200)
        self.assertEqual(self.admin.get("/api/music/tracks", headers=HEADERS).json()["total"], 2)
        trashed = [p for p in layout.trash().rglob("*") if p.is_file()]
        self.assertEqual(len(trashed), 1)
        listed = self.admin.get("/api/music/trash", headers=HEADERS).json()["files"]
        self.assertEqual(len(listed), 1)
        back = self.admin.post("/api/music/trash/restore", json={"path": listed[0]["path"]}, headers=HEADERS)
        self.assertEqual(back.status_code, 200, back.text)
        self.assertEqual(self.admin.get("/api/music/tracks", headers=HEADERS).json()["total"], 3)
        self.assertEqual(self.admin.get("/api/music/trash", headers=HEADERS).json()["files"], [])
        self.assertEqual(self.admin.post("/api/music/trash/restore", json={"path": "06 Musica/../x"}, headers=HEADERS).status_code, 404)
        self.assertEqual(self.admin.post("/api/music/tracks/9999/like", json={}, headers=HEADERS).status_code, 404)


if __name__ == "__main__":
    unittest.main()

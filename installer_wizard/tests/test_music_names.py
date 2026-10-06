import asyncio
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from config import write_env
from features.music import catalog, identify, layout, music, naming, organizer, renamer, scanner, tagwriter, tags
from features.music.db import db
from features.music import service as service_module
from features.music.service import LibraryService
from tests.test_music_library import Base, age, make_wav

HEADERS = {"X-Atena-Request": "1"}
SHAZAM = {"track": {"title": "Back In Black", "subtitle": "AC/DC", "key": "1", "genres": {"primary": "Rock"}, "images": {"coverarthq": "https://img.example/c.jpg"},
                    "sections": [{"metadata": [{"title": "Album", "text": "Back In Black"}, {"title": "Released", "text": "1980"}]}]}}


class NamingTest(unittest.TestCase):
    def test_file_names_carry_number_artist_title_and_year(self):
        info = {"title": "Back in Black", "artist": "AC/DC", "track_no": 6, "disc_no": 1, "year": 1980}
        self.assertEqual(naming.filename(info, ".MP3"), "06 - AC-DC - Back in Black (1980).mp3")
        self.assertEqual(naming.filename({**info, "disc_no": 2}, ".flac"), "2-06 - AC-DC - Back in Black (1980).flac")
        self.assertEqual(naming.filename({**info, "track_no": 0, "year": 0}, ".mp3"), "AC-DC - Back in Black.mp3")
        self.assertEqual(naming.filename({**info, "artist": "Senza artista"}, ".mp3"), "06 - Back in Black (1980).mp3")
        self.assertEqual(naming.filename({**info, "title": "AC/DC - Back in Black"}, ".mp3"), "06 - AC-DC - Back in Black (1980).mp3")

    def test_names_are_safe_and_bounded(self):
        info = {"title": 'Che: cosa? "strana" <x>|y', "artist": "A" * 300, "track_no": 1, "year": 2001}
        name = naming.filename(info, ".mp3")
        for bad in '\\/:*?"<>|':
            self.assertNotIn(bad, name)
        self.assertLessEqual(len(name), 175)
        self.assertTrue(name.endswith("(2001).mp3"))

    def test_similar_folder_names_are_reused(self):
        import tempfile
        from pathlib import Path
        parent = Path(tempfile.mkdtemp())
        (parent / "AC DC").mkdir()
        self.assertEqual(naming.reuse(parent, "AC-DC").name, "AC DC")
        self.assertEqual(naming.reuse(parent, "Queen").name, "Queen")

    def test_which_folders_may_be_rebuilt(self):
        from pathlib import Path
        self.assertTrue(naming.needs_new_folder(Path("AC DC/Album sconosciuto/x.mp3")))
        self.assertTrue(naming.needs_new_folder(Path("x.mp3")))
        self.assertFalse(naming.needs_new_folder(Path("Queen/Greatest Hits (Remastered)/x.mp3")))


class TagWriterTest(Base):
    def test_values_are_written_into_the_file_and_read_back(self):
        path = make_wav(self.tmp / "x.wav")
        self.assertTrue(tagwriter.write(path, {"title": "Titolo", "artist": "Artista", "album": "Album", "year": 1999, "genre": "Pop", "track_no": 3}))
        info = tags.read(path)
        self.assertEqual((info["title"], info["artist"], info["album"], info["year"], info["genre"], info["track_no"]), ("Titolo", "Artista", "Album", 1999, "Pop", 3))

    def test_empty_values_and_unknown_files_are_ignored(self):
        path = make_wav(self.tmp / "y.wav")
        self.assertFalse(tagwriter.write(path, {"title": "", "year": 0}))
        broken = self.tmp / "rotto.mp3"
        broken.write_bytes(b"non audio")
        self.assertFalse(tagwriter.write(broken, {"title": "x"}))


class RenamerTest(Base):
    def test_existing_files_get_complete_names_and_keep_their_identity(self):
        folder = layout.library() / "Vasco" / "Blasco"
        path = make_wav(folder / "Rosso.wav", title="Rosso", artist="Vasco", album="Blasco", year="1990", track="1/9")
        age(path)
        (folder / "Rosso.lrc").write_text("[00:01.00]ciao\n", encoding="utf-8")
        scanner.scan()
        track = catalog.tracks()[0]
        before = renamer.plan()
        self.assertEqual(before[0]["to"], "Libreria/Vasco/Blasco/01 - Vasco - Rosso (1990).wav")
        self.assertEqual(renamer.run(), {"renamed": 1, "failed": 0})
        self.assertTrue((folder / "01 - Vasco - Rosso (1990).wav").is_file())
        self.assertTrue((folder / "01 - Vasco - Rosso (1990).lrc").is_file())
        self.assertEqual(catalog.track(track["id"])["id"], track["id"])
        self.assertEqual(renamer.plan(), [])
        scanner.scan()
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tracks"), 1)

    def test_custom_folders_are_left_in_place_but_unknown_ones_are_rebuilt(self):
        kept = make_wav(layout.library() / "Beatles" / "Abbey Road (Remastered)" / "x.wav", title="Come Together", artist="The Beatles", album="Abbey Road")
        loose = make_wav(layout.library() / "AC DC" / "Album sconosciuto" / "y.wav", title="Hells Bells", artist="AC DC", album="Back In Black")
        for p in (kept, loose):
            age(p)
        scanner.scan()
        steps = {s["from"].split("/")[-1]: s["to"] for s in renamer.plan()}
        self.assertEqual(steps["x.wav"], "Libreria/Beatles/Abbey Road (Remastered)/The Beatles - Come Together.wav")
        self.assertEqual(steps["y.wav"], "Libreria/AC DC/Back In Black/AC DC - Hells Bells.wav")
        renamer.run()
        self.assertFalse((layout.library() / "AC DC" / "Album sconosciuto").exists())

    def test_name_collisions_never_overwrite(self):
        folder = layout.library() / "Mina" / "Mille"
        for name in ("a.wav", "b.wav"):
            age(make_wav(folder / name, title="Luna", artist="Mina", album="Mille"))
        scanner.scan()
        renamer.run()
        self.assertEqual(sorted(p.name for p in folder.glob("*.wav")), ["Mina - Luna (2).wav", "Mina - Luna.wav"])

    def test_new_files_are_named_in_full_by_the_organizer(self):
        self.drop("a.wav", title="Back in Black", artist="AC/DC", album="Back in Black", year="1980", track="6/10")
        organizer.sweep()
        self.assertTrue((layout.library() / "AC-DC" / "Back in Black" / "06 - AC-DC - Back in Black (1980).wav").is_file())


class IdentifyTest(Base):
    def setUp(self):
        super().setUp()
        extra = {"album": "Back In Black", "year": 1980, "genre": "Rock", "track_no": 6, "cover": "", "title": "Back In Black", "artist": "AC/DC"}
        patches = [mock.patch.object(identify.music.watcher, "_recognize", mock.AsyncMock(return_value=SHAZAM)),
                   mock.patch.object(identify, "excerpt", mock.AsyncMock(return_value=b"x" * 30000)),
                   mock.patch.object(identify.sources, "search", mock.AsyncMock(return_value=extra)),
                   mock.patch.object(identify, "store_cover", mock.AsyncMock())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        identify.tried_files.clear()
        organizer.held.clear()

    def dropped(self, name: str, **info):
        path = make_wav(self.inbox / name, **info)
        age(path)
        return path

    def test_a_song_nobody_can_name_stays_in_da_smistare_and_never_makes_unknown_folders(self):
        path = self.dropped("traccia 07.wav")
        result = organizer.sweep(True)
        self.assertEqual((result["moved"], result["unassigned"]), (0, 1))
        self.assertTrue(path.exists())
        self.assertEqual(list(layout.library().rglob("*")), [])
        listed = organizer.unassigned_files()
        self.assertEqual([f["name"] for f in listed], ["traccia 07.wav"])
        self.assertFalse(organizer.pending())

    def test_it_is_identified_by_sound_and_then_filed_with_the_right_names(self):
        path = self.dropped("traccia 07.wav")
        organizer.sweep(True)
        self.assertEqual(asyncio.run(identify.inbox([path], True)), 1)
        organizer.held.clear()
        age(path)
        self.assertEqual(organizer.sweep(True)["moved"], 1)
        final = layout.library() / "AC-DC" / "Back In Black" / "06 - AC-DC - Back In Black (1980).wav"
        self.assertTrue(final.is_file(), [str(p) for p in layout.library().rglob("*.wav")])
        info = tags.read(final)
        self.assertEqual((info["artist"], info["title"], info["album"]), ("AC/DC", "Back In Black", "Back In Black"))
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM hints"), 0)
        self.assertFalse(any("sconosciut" in str(p).lower() or "senza" in str(p).lower() for p in layout.library().rglob("*")))

    def test_the_user_can_assign_a_name_or_put_the_song_in_the_mixes(self):
        from fastapi.testclient import TestClient
        import atena_supervisor
        admin = TestClient(atena_supervisor.admin)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        write_env({"ATENA_MUSIC_IDENTIFY": "0"})
        self.addCleanup(lambda: write_env({"ATENA_MUSIC_IDENTIFY": "1"}))
        first = self.dropped("uno.wav")
        second = self.dropped("due.wav")
        organizer.sweep(True)
        files = admin.get("/api/music/unassigned", headers=HEADERS).json()["files"]
        self.assertEqual(len(files), 2)
        bad = admin.post("/api/music/assign", json={"path": files[0]["path"], "title": "x"}, headers=HEADERS)
        self.assertEqual(bad.status_code, 400)
        ok = admin.post("/api/music/assign", json={"path": "Da smistare/uno.wav", "title": "Canzone Mia", "artist": "Io", "album": "Disco Mio", "year": 2024}, headers=HEADERS)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue((layout.library() / "Io" / "Disco Mio" / "Io - Canzone Mia (2024).wav").is_file(), [str(p) for p in layout.library().rglob("*.wav")])
        self.assertFalse(first.exists())
        mix = admin.post("/api/music/assign", json={"path": "Da smistare/due.wav", "mix": True, "title": "Pezzo"}, headers=HEADERS)
        self.assertEqual(mix.status_code, 200, mix.text)
        self.assertTrue(any("Vari artisti" in str(p) for p in layout.library().rglob("*.wav")))
        self.assertFalse(second.exists())
        self.assertEqual(admin.post("/api/music/assign", json={"path": "../etc/passwd", "artist": "x"}, headers=HEADERS).status_code, 404)

    def test_a_known_artist_without_album_goes_to_singoli_and_is_completed_later(self):
        self.dropped("a.wav", title="Back in Black", artist="AC DC")
        organizer.sweep(True)
        scanner.scan()
        self.assertTrue((layout.library() / "AC DC" / "Singoli").is_dir())
        track = catalog.tracks()[0]
        self.assertEqual(track["album"], "Singoli")
        result = asyncio.run(identify.run(5))
        self.assertEqual((result["identified"], result["tried"]), (1, 1))
        found = catalog.track(track["id"])
        self.assertEqual((found["album"], found["year"], found["genre"], found["track_no"]), ("Back In Black", 1980, "Rock", 6))
        renamer.run()
        self.assertTrue((layout.library() / "AC DC" / "Back In Black" / "06 - AC DC - Back in Black (1980).wav").is_file())
        self.assertFalse((layout.library() / "AC DC" / "Singoli").exists())
        self.assertEqual(asyncio.run(identify.run(5))["tried"], 0)

    def test_existing_good_tags_are_never_overwritten_by_a_different_match(self):
        self.dropped("a.wav", title="Luna", artist="Mina", album="Mille", genre="Pop", year="1975")
        organizer.sweep(True)
        scanner.scan()
        self.assertEqual(asyncio.run(identify.run(5))["tried"], 0)

    def test_failures_do_not_mark_files_so_they_are_retried(self):
        path = self.dropped("c.wav")
        with mock.patch.object(identify.music.watcher, "_recognize", mock.AsyncMock(side_effect=RuntimeError("libreria assente"))):
            self.assertEqual(asyncio.run(identify.inbox([path], True)), 0)
        identify.tried_files.clear()
        self.assertEqual(asyncio.run(identify.inbox([path], True)), 1)

    def test_legacy_unknown_names_are_migrated_and_the_old_folder_emptied(self):
        from features.music import legacy
        old = make_wav(layout.library() / "Artista sconosciuto" / "Album sconosciuto" / "x.wav", title="X", artist="Artista sconosciuto")
        age(old)
        known = make_wav(layout.library() / "Mina" / "Album sconosciuto" / "y.wav", title="Luna", artist="Mina")
        age(known)
        scanner.scan()
        self.assertEqual(legacy.migrate(), 2)
        self.assertEqual(sorted(t["album"] for t in catalog.tracks()), ["Singoli", "Singoli"])
        organizer.sweep(True)
        renamer.run()
        self.assertTrue((layout.library() / "Mina" / "Singoli" / "Mina - Luna.wav").is_file())
        self.assertFalse(any("sconosciut" in str(p).lower() for p in layout.library().rglob("*")))
        self.assertEqual([f["name"] for f in organizer.unassigned_files()], ["x.wav"])

    def test_sample_is_taken_from_the_middle_of_the_song(self):
        command = identify.sample_command(layout.root() / "x.mp3", 200)
        self.assertEqual(command[command.index("-ss") + 1], "60.0")
        self.assertEqual(identify.sample_command(layout.root() / "x.mp3", 8)[5], "0.0")


class ServiceAndApiTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def test_rename_preview_and_apply_over_http(self):
        path = make_wav(layout.library() / "Vasco" / "Blasco" / "Rosso.wav", title="Rosso", artist="Vasco", album="Blasco", track="1")
        age(path)
        scanner.scan()
        preview = self.admin.get("/api/music/rename/preview", headers=HEADERS).json()
        self.assertEqual(preview["total"], 1)
        applied = self.admin.post("/api/music/rename", headers=HEADERS).json()
        self.assertEqual(applied["renamed"], 1)
        self.assertEqual(self.admin.get("/api/music/rename/preview", headers=HEADERS).json()["total"], 0)

    def test_identify_endpoint_reports_what_it_did(self):
        with mock.patch.object(identify, "run", mock.AsyncMock(return_value={"identified": 2, "tried": 3, "available": True, "items": []})):
            r = self.admin.post("/api/music/identify", headers=HEADERS)
        self.assertEqual((r.status_code, r.json()["identified"], r.json()["tried"]), (200, 2, 3))
        self.assertIn("renamed", r.json())

    def test_cycle_identifies_and_renames_unless_switched_off(self):
        write_env({"ATENA_UNOFFICIAL_SERVICES": "1"})
        self.addCleanup(lambda: write_env({"ATENA_UNOFFICIAL_SERVICES": "0"}))
        path = make_wav(layout.library() / "Vasco" / "Blasco" / "Rosso.wav", title="Rosso", artist="Vasco", album="Blasco", track="1")
        age(path)
        scanner.scan()
        calls = []

        async def fake(limit, write):
            calls.append(limit)
            return {"identified": 0, "tried": 0, "available": True, "items": []}
        service = LibraryService()
        with mock.patch.object(identify, "run", fake), mock.patch("features.music.service.covers.complete", mock.AsyncMock(return_value=0)), \
                mock.patch("features.music.enrich.run", mock.AsyncMock(return_value=0)), mock.patch("features.music.service.lyrics_store.fetch_missing", mock.AsyncMock(return_value=0)):
            service_module.state["covers_at"] = 0.0
            asyncio.run(service.cycle(True))
            self.assertEqual(calls, [3])
            self.assertTrue((layout.library() / "Vasco" / "Blasco" / "01 - Vasco - Rosso.wav").is_file())
            write_env({"ATENA_MUSIC_IDENTIFY": "0", "ATENA_MUSIC_RENAME": "0"})
            self.addCleanup(lambda: write_env({"ATENA_MUSIC_IDENTIFY": "1", "ATENA_MUSIC_RENAME": "1"}))
            service_module.state["covers_at"] = 0.0
            asyncio.run(service.cycle(True))
            self.assertEqual(calls, [3])
        self.assertTrue(music.available())


if __name__ == "__main__":
    unittest.main()

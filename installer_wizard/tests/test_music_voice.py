import asyncio
import unittest
from unittest import mock

from config import write_env
from features.music import catalog, commands, playlists
from features.music.outputs import Outputs
from state import store
from tests.test_music_library import Base


class VoiceBase(Base):
    def setUp(self):
        super().setUp()
        self.out = Outputs()
        patches = [mock.patch.object(commands, "outputs", self.out), mock.patch.object(commands, "lan_base", return_value="http://192.168.1.2"),
                   mock.patch.object(self.out, "refresh", mock.AsyncMock(return_value=[]))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: setattr(store, "now_playing", {}))
        self.filled()

    def say(self, text: str):
        return asyncio.run(commands.answer(text))

    def with_display(self, name: str = "Sala"):
        self.out.remote_beat("display:sala", name)

    def queue(self) -> list[str]:
        session = self.out.sessions["display:sala"]
        return [catalog.track(i)["title"] for i in session.queue]


class PlayTest(VoiceBase):
    def test_play_an_artist_on_the_display(self):
        self.with_display()
        speech, ui = self.say("metti la musica di Vasco")
        self.assertIn("Vasco", speech)
        self.assertIn("Sala", speech)
        self.assertEqual(ui["mode"], "face")
        self.assertEqual(sorted(self.queue()), ["Blu", "Rosso"])
        self.assertEqual(self.out.sessions["display:sala"].user, "voce")

    def test_play_a_track_an_album_a_genre_and_a_playlist(self):
        self.with_display()
        speech, _ = self.say("riproduci la canzone Luna")
        self.assertIn("«Luna» di Mina", speech)
        self.assertEqual(self.queue(), ["Luna"])
        speech, _ = self.say("metti l'album Blasco")
        self.assertIn("album Blasco", speech)
        self.assertEqual(sorted(self.queue()), ["Blu", "Rosso"])
        speech, _ = self.say("suona un po' di pop")
        self.assertIn("pop", speech.lower())
        self.assertEqual(self.queue(), ["Luna"])
        pid = playlists.create("ann", "Cena con amici")
        playlists.add(pid, "ann", [t["id"] for t in catalog.tracks("title")][:2])
        speech, _ = self.say("metti la playlist cena con amici")
        self.assertIn("playlist Cena con amici", speech)
        self.assertEqual(len(self.queue()), 2)

    def test_generic_request_plays_something_from_the_library(self):
        self.with_display()
        speech, _ = self.say("metti un po' di musica")
        self.assertIn("Sala", speech)
        self.assertTrue(self.queue())

    def test_named_device_and_unknown_content_and_no_device(self):
        self.out.remote_beat("display:sala", "Sala")
        self.out.remote_beat("display:cucina", "Cucina")
        speech, _ = self.say("metti la musica di Mina in cucina")
        self.assertIn("Cucina", speech)
        self.assertIn("display:cucina", self.out.sessions)
        speech, _ = self.say("metti la canzone Inesistente")
        self.assertIn("Non trovo", speech)
        self.out.devices.clear()
        speech, _ = self.say("metti la musica di Mina")
        self.assertIn("nessuno schermo", speech)

    def test_explicit_music_verbs_only_and_unrelated_requests_are_left_alone(self):
        self.with_display()
        for text in ("metti la sveglia alle sette", "accendi la luce", "che tempo fa", "metti la webcam", "apri la telecamera della cucina"):
            with self.assertRaises(LookupError, msg=text):
                self.say(text)

    def test_the_voice_setting_can_switch_everything_off(self):
        self.with_display()
        write_env({"ATENA_MUSIC_VOICE": "0"})
        self.addCleanup(lambda: write_env({"ATENA_MUSIC_VOICE": "1"}))
        with self.assertRaises(LookupError):
            self.say("metti la musica di Vasco")


class ControlTest(VoiceBase):
    def setUp(self):
        super().setUp()
        self.with_display()
        self.say("metti la musica di Vasco")

    def test_pause_resume_next_previous_stop(self):
        session = self.out.sessions["display:sala"]
        self.assertIn("pausa", self.say("metti in pausa")[0].lower())
        self.assertEqual(session.state, "paused")
        self.say("riprendi la musica")
        self.assertEqual(session.state, "playing")
        first = session.index
        self.say("prossima canzone")
        self.assertEqual(session.index, first + 1) if len(session.queue) > 1 else None
        self.say("ferma la musica")
        self.assertEqual(session.state, "stopped")

    def test_volume_and_likes(self):
        session = self.out.sessions["display:sala"]
        before = session.volume
        self.say("alza il volume")
        self.assertGreater(session.volume, before)
        self.say("abbassa il volume della musica")
        self.assertAlmostEqual(session.volume, before, places=2)
        self.assertIn("40", self.say("metti il volume al 40 per cento")[0])
        self.assertAlmostEqual(session.volume, 0.4)
        self.say("mi piace questa canzone")
        self.assertTrue(catalog.track(session.current, "voce")["liked"])

    def test_without_a_session_control_words_fall_through(self):
        self.out.sessions.clear()
        for text in ("metti in pausa", "alza il volume", "ferma la musica", "prossima canzone"):
            with self.assertRaises(LookupError, msg=text):
                self.say(text)


if __name__ == "__main__":
    unittest.main()

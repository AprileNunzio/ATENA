import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from features.music import id3, tags, tagwriter

FIELDS = {"title": "Città", "artist": "Artista", "album": "Album", "album_artist": "Gruppo", "genre": "Jazz", "year": "2001",
          "track_no": "4"}


def silent_wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * 8000)
    return path


class TagWriterTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def check(self, path: Path) -> None:
        info = tags.read(path)
        self.assertEqual((info["title"], info["artist"], info["album"], info["album_artist"], info["genre"]),
                         ("Città", "Artista", "Album", "Gruppo", "Jazz"))
        self.assertEqual((info["year"], info["track_no"]), (2001, 4))

    def test_wav_tags_round_trip_and_audio_survives(self):
        path = silent_wav(self.dir / "a.wav")
        self.assertTrue(tagwriter.write(path, FIELDS))
        self.assertTrue(tagwriter.write(path, FIELDS))
        self.check(path)
        with wave.open(str(path)) as audio:
            self.assertEqual(audio.getnframes(), 8000)

    def test_rejects_files_that_are_not_wav(self):
        bad = self.dir / "b.wav"
        bad.write_bytes(b"not a riff file")
        self.assertFalse(tagwriter.write(bad, FIELDS))
        with self.assertRaises(ValueError):
            id3.write_wav(bad, FIELDS)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_compressed_formats_are_tagged_through_ffmpeg(self):
        for suffix, codec in ((".mp3", "libmp3lame"), (".flac", "flac"), (".m4a", "aac")):
            with self.subTest(suffix=suffix):
                path = self.dir / f"c{suffix}"
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", "-c:a", codec,
                                str(path)], check=True)
                self.assertTrue(tagwriter.write(path, FIELDS))
                self.check(path)


if __name__ == "__main__":
    unittest.main()

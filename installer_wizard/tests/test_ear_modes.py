import os
import sys
import unittest
from pathlib import Path
from unittest import mock
import numpy as np

EAR_DIR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR_DIR) not in sys.path:
    sys.path.insert(0, str(EAR_DIR))

import enhance
import online_stt
import stt


class EarModesTest(unittest.TestCase):

    def test_audio_to_wav_bytes(self):
        # Genera un secondo di audio float32 di test
        samples = np.sin(np.linspace(0, 2 * np.pi * 440, 16000)).astype(np.float32)
        wav = online_stt.audio_to_wav_bytes(samples, 16000)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav[:16])
        # 16000 campioni a 16 bit (2 byte) + 44 byte header = 32044 byte
        self.assertEqual(len(wav), 32044)

    def test_online_stt_without_key_returns_none(self):
        with mock.patch.dict(os.environ, {"ATENA_ONLINE_STT_KEY": "", "DEEPGRAM_API_KEY": "", "OPENAI_API_KEY": ""}, clear=True):
            samples = np.zeros(16000, dtype=np.float32)
            res = online_stt.transcribe_online(samples, "it")
            self.assertIsNone(res)

    def test_transcribe_default_offline_mode(self):
        # In modalità offline (default), non chiama online_stt
        samples = np.zeros(16000, dtype=np.float32)
        with mock.patch.dict(os.environ, {"ATENA_EAR_MODE": "offline"}):
            with mock.patch("online_stt.transcribe_online") as mock_online:
                dummy_model = mock.Mock()
                dummy_model.transcribe.return_value = ([mock.Mock(text="ciao Atena")], None)
                with mock.patch.dict(stt.ACTIVE, {"model": dummy_model}):
                    text, lang = stt.transcribe(samples, fast=False, detect=False)
                    self.assertEqual(text, "ciao Atena")
                    mock_online.assert_not_called()

    def test_transcribe_online_mode_success(self):
        samples = np.zeros(16000, dtype=np.float32)
        with mock.patch.dict(os.environ, {"ATENA_EAR_MODE": "online"}):
            with mock.patch("online_stt.transcribe_online", return_value="accendi luce salotto") as mock_online:
                text, lang = stt.transcribe(samples, fast=False, detect=False)
                self.assertEqual(text, "accendi luce salotto")
                mock_online.assert_called_once()

    def test_transcribe_online_fallback_to_offline_on_failure(self):
        samples = np.zeros(16000, dtype=np.float32)
        with mock.patch.dict(os.environ, {"ATENA_EAR_MODE": "online"}):
            with mock.patch("online_stt.transcribe_online", return_value=None):
                dummy_model2 = mock.Mock()
                dummy_model2.transcribe.return_value = ([mock.Mock(text="fallback locale")], None)
                with mock.patch.dict(stt.ACTIVE, {"model": dummy_model2}):
                    text, lang = stt.transcribe(samples, fast=False, detect=False)
                    self.assertEqual(text, "fallback locale")

    def test_enhance_clean_fallback(self):
        samples = (np.random.randn(8000) * 0.05).astype(np.float32)
        prof = enhance.NoiseProfile()
        prof.learn(samples)
        # DeepFilterNet assente o disattivato -> fallback spettrale locale
        with mock.patch.dict(os.environ, {"ATENA_EAR_ENHANCE_ENGINE": "spectral"}):
            out = enhance.clean(samples, prof)
            self.assertEqual(len(out), len(samples))
            self.assertIsInstance(out, np.ndarray)

    def test_enhance_far_field_limiter(self):
        # Audio molto forte viene limitato senza clipping duro
        loud = np.ones(1000, dtype=np.float32) * 2.5
        norm = enhance.normalize(loud)
        self.assertTrue(np.all(norm <= 1.0))
        self.assertTrue(np.all(norm >= -1.0))


if __name__ == "__main__":
    unittest.main()

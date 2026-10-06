import os

import numpy as np

from tuning import tuning

try:
    from scipy.signal import lfilter
except ImportError:
    lfilter = None


def _env_f(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.environ.get(key, default))))
    except (TypeError, ValueError):
        return default

RATE = 16000
N_FFT = 512
HOP = 128
WINDOW = np.hanning(N_FFT).astype(np.float32)
HIGHPASS_HZ = 90
OVER_SUBTRACT = 1.6
SPECTRAL_FLOOR = 0.08
TARGET_RMS = 0.075
MAX_GAIN = 18.0
PEAK = 0.97


class NoiseProfile:

    def __init__(self) -> None:
        self.magnitude: np.ndarray | None = None
        self.pending = np.zeros(0, dtype=np.float32)

    def learn(self, frame: np.ndarray) -> None:
        self.pending = np.concatenate([self.pending, frame])
        if len(self.pending) < N_FFT * 8:
            return
        spec = np.abs(_stft(self.pending)).mean(axis=0)
        self.pending = np.zeros(0, dtype=np.float32)
        self.magnitude = spec if self.magnitude is None else self.magnitude * 0.9 + spec * 0.1


def _stft(x: np.ndarray) -> np.ndarray:
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    count = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(count)[:, None]
    return np.fft.rfft(x[idx] * WINDOW, axis=1)


def _istft(spec: np.ndarray, length: int) -> np.ndarray:
    frames = np.fft.irfft(spec, n=N_FFT, axis=1) * WINDOW
    out = np.zeros(HOP * (len(frames) - 1) + N_FFT, dtype=np.float32)
    norm = np.zeros_like(out)
    for i, f in enumerate(frames):
        out[i * HOP:i * HOP + N_FFT] += f
        norm[i * HOP:i * HOP + N_FFT] += WINDOW ** 2
    res = out / np.maximum(norm, 1e-6)
    if len(res) < length:
        res = np.pad(res, (0, length - len(res)))
    return res[:length]


def highpass(x: np.ndarray) -> np.ndarray:
    rc = 1.0 / (2 * np.pi * HIGHPASS_HZ)
    alpha = rc / (rc + 1.0 / RATE)
    diff = np.diff(x, prepend=x[:1])
    if lfilter:
        return lfilter([alpha], [1.0, -alpha], diff).astype(np.float32)
    y = np.empty_like(x)
    acc = 0.0
    for i, d in enumerate(diff):
        acc = alpha * (acc + d)
        y[i] = acc
    return y


def denoise(x: np.ndarray, noise: np.ndarray | None) -> np.ndarray:
    if noise is None or len(x) < N_FFT:
        return x
    spec = _stft(x)
    mag = np.abs(spec)
    gain = np.maximum(1.0 - OVER_SUBTRACT * noise[None, :] / np.maximum(mag, 1e-9), SPECTRAL_FLOOR)
    for i in range(1, len(gain)):
        gain[i] = np.maximum(gain[i], gain[i - 1] * 0.6)
    return _istft(spec * gain, len(x)).astype(np.float32)


_DF_MODEL = None
_DF_TRIED = False


def _init_deepfilternet():
    global _DF_MODEL, _DF_TRIED
    if _DF_TRIED:
        return _DF_MODEL
    _DF_TRIED = True
    engine = os.environ.get("ATENA_EAR_ENHANCE_ENGINE", "auto").strip().lower()
    if engine == "spectral":
        return None
    try:
        from df.enhance import init_df
        _DF_MODEL = init_df()
        return _DF_MODEL
    except Exception:
        _DF_MODEL = None
        return None


def deepfilter_clean(x: np.ndarray) -> np.ndarray | None:
    model = _init_deepfilternet()
    if model is None:
        return None
    try:
        import torch
        from df.enhance import enhance as df_enhance
        tensor = torch.from_numpy(x).unsqueeze(0)
        enhanced = df_enhance(model, df_state=None, audio=tensor)
        return enhanced.squeeze(0).cpu().numpy().astype(np.float32)
    except Exception:
        return None


def normalize(x: np.ndarray) -> np.ndarray:
    frames = x[:len(x) // 320 * 320].reshape(-1, 320) if len(x) >= 320 else x.reshape(1, -1)
    energy = np.sqrt((frames ** 2).mean(axis=1))
    voiced = energy[energy > np.percentile(energy, 60)] if len(energy) > 4 else energy
    rms = float(voiced.mean()) if len(voiced) else 0.0
    if rms <= 1e-5:
        return x
    target = _env_f("ATENA_EAR_TARGET_RMS", TARGET_RMS, 0.03, 0.2)
    max_gain = tuning.max_gain()
    gain = min(max_gain, target / rms)
    # Protezione rumore da lontano: se il segnale e' molto basso, evita di gonfiare solo il fruscio
    gate = min(1.0, max(0.2, (rms / 0.005) ** 2))
    y = x * (gain * gate)
    # Limiter morbido: amplifica la voce lontana senza tagliare i picchi
    return (PEAK * np.tanh(y / PEAK)).astype(np.float32)


def clean(x: np.ndarray, profile: NoiseProfile) -> np.ndarray:
    df_out = deepfilter_clean(x.astype(np.float32))
    if df_out is not None:
        return normalize(df_out)
    return normalize(denoise(highpass(x.astype(np.float32)), profile.magnitude))


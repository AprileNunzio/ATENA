# Third-Party Notices

*Riepilogo in italiano in fondo al documento.*

Atena OS is released under the [MIT License](LICENSE). It uses, downloads or connects to third-party software, models,
data and services that keep their own licenses and terms. This file lists them, gives the attributions their licenses
require and warns about the ones that are **not free for every use**.

Atena is an adviser, not a gatekeeper: it installs safe, permissively licensed defaults, shows the license and any
warning next to every model, voice and service, and lets the administrator install anything else. **Whoever installs and
runs Atena is responsible for complying with the licenses and terms of what they choose to use.** This document is not
legal advice.

## Settings that change the defaults

| Setting | Effect |
| :--- | :--- |
| `ATENA_COMMERCIAL=1` | Declares business use: components licensed for non-commercial use only are not installed automatically and are flagged in the panels. They can still be installed on explicit request. |
| `ATENA_UNOFFICIAL_SERVICES=1` | Records the administrator's acceptance of the terms of services reached through unofficial interfaces (Shazam recognition, Microsoft Edge online voices). Without it those features stay off. |

The administration API `GET /api/licenses` returns the license status of every component together with this file.

## Restricted components (read before use)

| Component | Used for | License / terms | Restriction |
| :--- | :--- | :--- | :--- |
| openWakeWord pre-trained base models (`melspectrogram`, `embedding_model`) by David Scripka | instant "Ehi, Atena" wake word, together with your own `ehi_atena` model | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) ([source](https://github.com/dscripka/openWakeWord#license)) | **Non-commercial only**, share-alike. Not installed automatically when `ATENA_COMMERCIAL=1`; wake-up then uses speech recognition. |
| Qwen 2.5 3B and Qwen 2.5 Coder 3B (Alibaba Cloud) | optional language models | [Qwen Research License](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE) | **Non-commercial, research and evaluation only.** Not a default model. |
| Llama 3.2 Vision (Meta) | optional vision model | [Llama 3.2 Community License](https://www.llama.com/llama3_2/license/) and [Acceptable Use Policy](https://www.llama.com/llama3_2/use-policy/) | **Rights not granted to individuals domiciled in, or companies with a principal place of business in, the European Union.** |
| Piper voices (`rhasspy/piper-voices`) | fallback offline voice | per-voice license in each `MODEL_CARD` | Licenses differ per voice and some are research-only; check the voice's card. Not installed automatically when `ATENA_COMMERCIAL=1`. |
| Shazam recognition through `shazamio` (MIT library) | identifying music | [Shazam terms](https://www.apple.com/legal/internet-services/shazam/) | **Unofficial interface.** Off unless `ATENA_UNOFFICIAL_SERVICES=1`. |
| Microsoft Edge online voices through `edge-tts` (LGPL-3.0 library) | optional cloud voices | [Microsoft Services Agreement](https://www.microsoft.com/servicesagreement) | **Unofficial interface.** Off unless `ATENA_VOICE_ONLINE=1` and `ATENA_UNOFFICIAL_SERVICES=1`. |
| OpenStreetMap tiles and Nominatim | maps and geocoding | [ODbL](https://www.openstreetmap.org/copyright), [tile](https://operations.osmfoundation.org/policies/tiles/) and [Nominatim](https://operations.osmfoundation.org/policies/nominatim/) usage policies | Light personal use only; heavy or commercial traffic needs your own tile server or a commercial provider. |

## Language models offered in the catalog

| Models | License | Notes |
| :--- | :--- | :--- |
| Granite 3.3 2B / 8B (IBM) — **default** | Apache-2.0 | Italian officially supported. |
| Qwen 2.5 0.5B, 1.5B, 7B, 14B, 32B; Qwen 2.5 Coder 1.5B, 7B, 14B; Qwen 2.5 VL 7B | Apache-2.0 | |
| DeepSeek R1 distilled 1.5B, 7B, 14B, 32B | MIT (DeepSeek) on Qwen 2.5 base, Apache-2.0 | |
| DeepSeek R1 distilled 8B, Llama 3.1 8B | [Llama 3.1 Community License](https://www.llama.com/llama3_1/license/) | **Built with Llama.** Acceptable Use Policy applies. |
| Llama 3.2 1B / 3B | [Llama 3.2 Community License](https://www.llama.com/llama3_2/license/) | **Built with Llama.** Acceptable Use Policy applies. |
| Mistral 7B, Mistral Nemo 12B | Apache-2.0 | |
| Phi 3.5 mini, Phi 4 | MIT | |
| Gemma 2, Gemma 3 | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | Prohibited Use Policy applies; terms must be passed on with redistributed copies. |
| LLaVA 1.6 7B (Mistral base) | Apache-2.0 | |
| nomic-embed-text | Apache-2.0 | |
| BGE-M3 | MIT | |

Models installed manually are shown with "license unknown" until the administrator checks them.

## Models, voices and data that require attribution

- **Kokoro-82M** by hexgrad, voices and weights, Apache-2.0; runtime `kokoro-onnx` by thewh1teagle, MIT.
- **WeSpeaker ResNet34** speaker model trained on **VoxCeleb** (A. Nagrani, J. S. Chung, A. Zisserman et al.),
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), distributed through `k2-fsa/sherpa-onnx` (Apache-2.0).
- **OpenCV Zoo** models YuNet face detection (MIT), SFace face recognition (Apache-2.0) and NanoDet (Apache-2.0).
- **faster-whisper** (MIT) with OpenAI Whisper weights (MIT).
- **MediaPipe** Tasks Vision and hand landmarker model, Google, Apache-2.0.
- **Lee Perry-Smith head scan** used by the holographic face, by Lee Perry-Smith / Infinite Realities,
  [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), distributed with the three.js examples.
- **Michelle** character and **X Bot** animations (idle, walk, run, agree, head shake, sad, sneak, samba) used by the
  animated 3D character: Adobe Mixamo assets, royalty-free, downloaded at runtime from the three.js examples (MIT).
- **Wikimedia Commons images** shown on the whiteboard and in presentations: only files under CC0, public domain, CC BY
  or CC BY-SA are used, and each one is captioned with its author and license (also in PDF exports).
- **Wikipedia text** returned by web search: CC BY-SA 4.0, with source links.
- **OpenStreetMap** data © OpenStreetMap contributors, ODbL.

## Software

### Python (supervisor and core)

FastAPI (MIT), Uvicorn (BSD-3-Clause), httpx (BSD-3-Clause), Pydantic (MIT), psutil (BSD-3-Clause), python-pam (MIT),
six (MIT), NumPy (BSD-3-Clause), opencv-python-headless (Apache-2.0; bundles FFmpeg under LGPL-2.1), edge-tts
(LGPL-3.0, used unmodified as a library), websockets (BSD-3-Clause), cryptography (Apache-2.0 or BSD-3-Clause),
tinytag (MIT), SymPy (BSD-3-Clause), ReportLab (BSD), aiomqtt (BSD-3-Clause), python-docx, openpyxl, python-pptx (MIT),
Matplotlib (PSF-based), PyYAML (MIT), SQLAlchemy (MIT), sherpa-onnx (Apache-2.0), onnxruntime (MIT), openWakeWord code
(Apache-2.0), pychromecast (MIT), shazamio (MIT).

### Native core (Rust)

PyO3, tokio, serde, serde_json and landlock (MIT or Apache-2.0); unicode-ident (MIT or Apache-2.0, and Unicode-3.0).
`cargo metadata` lists every crate with its license.

### Web

three.js (MIT), qrcode-generator by Kazuhiko Arase (MIT, downloaded at runtime for VPN QR codes), React (MIT), lucide-react (ISC), Leaflet (BSD-2-Clause), occt-import-js (LGPL-2.1, loaded unmodified
as a separate file), Tailwind CSS, Vite, PostCSS, Autoprefixer, TypeScript (MIT or Apache-2.0), Rajdhani and Inter
fonts through Fontsource ([SIL OFL 1.1](https://openfontlicense.org)), bundled locally so no request reaches Google.

### Android and ESP32

AndroidX, Material Components, OkHttp, Kotlin coroutines (Apache-2.0); ArduinoJson (MIT); Arduino core for ESP32
(LGPL-2.1).

### External programs started by Atena

Blender (GPL-2.0-or-later), LibreDWG (GPL-3.0), FFmpeg (LGPL/GPL), LibreOffice (MPL-2.0), CUPS (Apache-2.0),
Docker (Apache-2.0), gVisor (Apache-2.0), Firecracker (Apache-2.0), Ollama (MIT), Piper engine (MIT), nftables (GPL-2.0),
WireGuard tools (GPL-2.0), OpenVPN (GPL-2.0), strongSwan (GPL-2.0), Tailscale client (BSD-3-Clause), ZeroTier One (MPL-2.0),
linux-enable-ir-emitter (MIT), NVIDIA drivers (proprietary, installed from the distribution). They run as separate
programs and are not part of Atena's code.

## Trademarks

Atena OS (ATENA, Architettura Tecnologica ed Ecosistema Neurale Aprile) is an independent open source project, not
affiliated with, endorsed or sponsored by any company named above. All
trademarks belong to their owners and are used only to identify their products.

---

## Riepilogo in italiano

Atena è distribuita con licenza MIT e usa componenti di terzi con licenze proprie. Atena **consiglia e avvisa, non
vieta**. Installa da sola solo componenti con licenze permissive, mostra licenza e avvisi accanto a ogni modello, voce e
servizio e lascia all'amministratore la libertà di installare altro. La responsabilità del rispetto delle licenze resta
a chi installa e usa Atena.

- **Solo uso non commerciale:** i modelli di base di openWakeWord (CC BY-NC-SA 4.0) e Qwen 2.5 3B (Qwen Research
  License). Alcune voci Piper hanno licenze di sola ricerca.
- **Non concesso nell'Unione Europea:** Llama 3.2 Vision.
- **Servizi non ufficiali** (Shazam, voci online di Edge): spenti finché non imposti `ATENA_UNOFFICIAL_SERVICES=1`.
- **Uso commerciale:** con `ATENA_COMMERCIAL=1` i componenti non commerciali non si installano da soli e vengono
  segnalati.
- **Attribuzioni:** immagini Wikimedia con autore e licenza in didascalia, Wikipedia, OpenStreetMap, VoxCeleb, il
  volto di Lee Perry-Smith e «Built with Llama» per i modelli Llama.
- **Marchi:** Atena OS non è affiliata a nessuna delle aziende citate.

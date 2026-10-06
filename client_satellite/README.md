# Atena Satellite Clients

This folder contains the lightweight client software meant to run on distributed satellite nodes. A satellite node is a remote microphone/speaker unit that streams audio to the central Atena Server.

## Architectures Supported

### 1. `microcontrollers/` (ESP32, ESP32-S3, Arduino)
Designed for extreme low-cost setups (~10€).
- Requires an I2S Microphone (e.g., INMP441).
- Requires an I2S Amplifier/Speaker (e.g., MAX98357A).
- Uses **PlatformIO** and Arduino/ESP-IDF framework.
- Automatically provisioned and flashed via USB by the Atena Server, then updated Over-The-Air (OTA) via Wi-Fi.

### 2. `linux_edge/` (Raspberry Pi, Orange Pi, Generic Linux)
Designed for slightly more powerful setups where you might already have a Raspberry Pi running in another room.
- Can use standard USB microphones and 3.5mm/HDMI audio output.
- Runs a lightweight Python client (`satellite.py`).
- Atena Server can provision this automatically over SSH.

## Auto-Provisioning
You do not need to manually edit code to set Wi-Fi credentials or the Server IP. The `satellite_manager` in the Atena Core handles dynamic compilation and flashing automatically.

## Edge routing (ESP32)

The ESP32 firmware runs a C++ port of the server's System 1 router (`src/edge_router.cpp`) on the transcript it
receives, so confident direct home actions go straight to the supervisor's lean `/api/nodes/intent` path and skip
the core round trip. Everything else, and anything below `ATENA_EDGE_THRESHOLD`, goes to `/api/nodes/chat`.
The supervisor never trusts the satellite's verdict: it re-parses the text, applies the laws guard and still asks
for confirmation on sensitive actions.

- `src/edge_router_model.h` is generated from the server router: `python -m server.core.orchestrator.edge_export`.
  `server/tests/test_edge_router.py` fails when it is stale and checks that the C++ and Python decisions match.
- Transport: put the supervisor CA in `src/atena_ca.h` as `#define ATENA_CA_PEM "..."` and use an `https://`
  `ATENA_SUPERVISOR_URL`. Without it the firmware refuses to send the node token unless built with
  `-D ATENA_ALLOW_PLAINTEXT`.
- Transcripts currently arrive on the serial port (one line per utterance); on-device speech recognition is the
  next step and only needs to call `submit_transcript()`.

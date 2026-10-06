#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "edge_router.h"
#include "edge_router_model.h"

#if __has_include("atena_ca.h")
#include "atena_ca.h"
#endif

namespace {

constexpr uint32_t HEARTBEAT_MS = 30000;
constexpr uint32_t HTTP_TIMEOUT_MS = 8000;
constexpr size_t MAX_LINE = atena_edge::MAX_INPUT_BYTES;
constexpr char FIRMWARE_VERSION[] = "edge-1.0.0";

String pending;
uint32_t last_heartbeat = 0;

bool secure_transport() {
#if defined(ATENA_CA_PEM)
    return true;
#else
    return false;
#endif
}

bool post_json(const char* path, const JsonDocument& body, JsonDocument& reply) {
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }
    const String url = String(ATENA_SUPERVISOR_URL) + path;
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.setReuse(true);
#if defined(ATENA_CA_PEM)
    static WiFiClientSecure client;
    client.setCACert(ATENA_CA_PEM);
    if (!http.begin(client, url)) {
        return false;
    }
#else
    if (!url.startsWith("http://")) {
        Serial.println("[edge] https needs ATENA_CA_PEM (atena_ca.h)");
        return false;
    }
#if !defined(ATENA_ALLOW_PLAINTEXT)
    Serial.println("[edge] refusing to send the node token in clear text: provide atena_ca.h");
    return false;
#else
    static WiFiClient client;
    if (!http.begin(client, url)) {
        return false;
    }
#endif
#endif
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Atena-Node", ATENA_NODE_ID);
    http.addHeader("Authorization", String("Bearer ") + ATENA_NODE_TOKEN);
    String payload;
    serializeJson(body, payload);
    const int status = http.POST(payload);
    if (status != HTTP_CODE_OK) {
        Serial.printf("[edge] %s -> HTTP %d\n", path, status);
        http.end();
        return false;
    }
    const DeserializationError error = deserializeJson(reply, http.getStream());
    http.end();
    return !error;
}

void submit_transcript(const String& text) {
    const atena_edge::Decision decision = atena_edge::classify(text.c_str(), text.length());
    const bool local = atena_edge::handle_locally(decision, ATENA_EDGE_THRESHOLD);
    JsonDocument body;
    body["text"] = text;
    JsonObject edge = body["edge"].to<JsonObject>();
    edge["intent"] = atena_edge::intent_name(decision.intent);
    edge["confidence"] = decision.confidence;
    edge["model"] = atena_edge::MODEL_DIGEST;
    if (decision.agent != nullptr) {
        edge["agent"] = decision.agent;
        edge["action"] = decision.action;
    }
    const uint32_t started = millis();
    JsonDocument reply;
    if (!post_json(local ? "/api/nodes/intent" : "/api/nodes/chat", body, reply)) {
        Serial.println("[edge] request failed");
        return;
    }
    Serial.printf("[edge] %s %.2f %s in %lu ms: %s\n", atena_edge::intent_name(decision.intent), decision.confidence,
                  local ? "local" : "core", static_cast<unsigned long>(millis() - started), reply["reply"] | "");
}

void heartbeat() {
    JsonDocument body;
    body["version"] = FIRMWARE_VERSION;
    body["hostname"] = ATENA_NODE_ID;
    JsonObject metrics = body["metrics"].to<JsonObject>();
    metrics["uptime"] = millis() / 1000.0;
    metrics["ram"] = 100.0 * (1.0 - static_cast<double>(ESP.getFreeHeap()) / ESP.getHeapSize());
    JsonDocument reply;
    post_json("/api/nodes/heartbeat", body, reply);
}

void read_serial() {
    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            pending.trim();
            if (pending.length() > 0) {
                submit_transcript(pending);
            }
            pending = "";
        } else if (pending.length() < MAX_LINE) {
            pending += c;
        }
    }
}

}

void setup() {
    Serial.begin(115200);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(250);
    }
    Serial.printf("[edge] online %s, model %.12s, tls %s\n", WiFi.localIP().toString().c_str(), atena_edge::MODEL_DIGEST,
                  secure_transport() ? "on" : "off");
    heartbeat();
    last_heartbeat = millis();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        WiFi.reconnect();
        delay(500);
        return;
    }
    read_serial();
    if (millis() - last_heartbeat >= HEARTBEAT_MS) {
        heartbeat();
        last_heartbeat = millis();
    }
    delay(5);
}

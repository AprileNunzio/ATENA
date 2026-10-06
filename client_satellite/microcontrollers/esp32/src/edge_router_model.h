#pragma once

#include <stddef.h>

namespace atena_edge {

constexpr char MODEL_DIGEST[] = "b0755e7b62bcc2c6295f9ad48f9e84f69ae94224ee37f4b841a9bfe2433cfe09";

struct ScoredToken {
    const char* token;
    double score;
};

struct ActionToken {
    const char* token;
    const char* agent;
    const char* action;
    double score;
};

constexpr ActionToken ACTION_TOKENS[] = {
    {"accendi", "home_assistant", "turn_on", 4.5},
    {"allarme", "vision_surveillance", "alarm_status", 4.2},
    {"apri", "home_assistant", "open_lock", 2.8},
    {"canzone", "media_player", "play_track", 3.8},
    {"chiudi", "home_assistant", "close_lock", 4.0},
    {"intruso", "vision_surveillance", "detect_intrusion", 4.0},
    {"luce", "home_assistant", "toggle_light", 4.0},
    {"luci", "home_assistant", "toggle_light", 4.0},
    {"musica", "media_player", "play_track", 3.8},
    {"muta", "media_player", "mute", 4.2},
    {"pausa", "media_player", "pause", 4.5},
    {"ping", "sysops_automation", "ping_host", 4.0},
    {"play", "media_player", "play", 4.5},
    {"porta", "home_assistant", "door_lock", 3.8},
    {"riavvia", "sysops_automation", "restart_service", 4.2},
    {"spegni", "home_assistant", "turn_off", 4.5},
    {"stato", "sysops_automation", "system_status", 3.6},
    {"stop", "media_player", "stop", 4.5},
    {"suona", "media_player", "play", 4.2},
    {"telecamera", "vision_surveillance", "view_feed", 4.0},
    {"telecamere", "vision_surveillance", "view_feed", 4.0},
    {"temperatura", "home_assistant", "get_temp", 3.8},
    {"termostato", "home_assistant", "set_temp", 4.0},
    {"volume", "media_player", "set_volume", 4.2},
};
constexpr size_t ACTION_TOKENS_COUNT = sizeof(ACTION_TOKENS) / sizeof(ACTION_TOKENS[0]);

constexpr ScoredToken CHITCHAT_TOKENS[] = {
    {"arrivederci", 5.5},
    {"bene", 3.8},
    {"buonanotte", 5.5},
    {"buonasera", 6.0},
    {"buondi", 5.5},
    {"buongiorno", 6.0},
    {"chi", 3.8},
    {"ciao", 6.0},
    {"come", 3.5},
    {"daccordo", 4.0},
    {"eccomi", 5.0},
    {"grazie", 5.5},
    {"hey", 5.5},
    {"notte", 5.0},
    {"ok", 4.0},
    {"perfetto", 4.0},
    {"prego", 5.0},
    {"salve", 5.5},
    {"sei", 4.5},
    {"stai", 5.0},
};
constexpr size_t CHITCHAT_TOKENS_COUNT = sizeof(CHITCHAT_TOKENS) / sizeof(CHITCHAT_TOKENS[0]);

constexpr ScoredToken WHITEBOARD_TOKENS[] = {
    {"algebra", 5.5},
    {"calcoli", 5.5},
    {"calcolo", 5.5},
    {"canvas", 6.0},
    {"diagramma", 5.2},
    {"disegna", 5.0},
    {"disegniamo", 5.5},
    {"equazione", 5.5},
    {"equazioni", 5.5},
    {"flusso", 4.8},
    {"lavagna", 6.5},
    {"matematica", 6.0},
    {"postit", 5.0},
    {"schema", 5.0},
    {"schematizza", 5.2},
    {"whiteboard", 6.5},
};
constexpr size_t WHITEBOARD_TOKENS_COUNT = sizeof(WHITEBOARD_TOKENS) / sizeof(WHITEBOARD_TOKENS[0]);

constexpr ScoredToken BROWSER_TOKENS[] = {
    {"amazon", 5.5},
    {"browser", 6.0},
    {"github", 5.5},
    {"google", 5.5},
    {"link", 4.5},
    {"naviga", 5.5},
    {"sito", 5.2},
    {"url", 5.0},
    {"visita", 5.2},
    {"web", 4.5},
    {"wikipedia", 5.2},
    {"youtube", 5.5},
};
constexpr size_t BROWSER_TOKENS_COUNT = sizeof(BROWSER_TOKENS) / sizeof(BROWSER_TOKENS[0]);

constexpr ScoredToken COMPLEX_TOKENS[] = {
    {"algoritmo", 5.0},
    {"analizza", 5.0},
    {"architettura", 5.2},
    {"calcola", 4.5},
    {"codice", 4.5},
    {"confronta", 4.6},
    {"debug", 4.8},
    {"dimostra", 5.0},
    {"elabora", 4.8},
    {"ottimizza", 5.0},
    {"pensa", 5.2},
    {"perche", 4.8},
    {"perch\xc3" "\xa9" "", 4.8},
    {"piano", 4.5},
    {"progetta", 5.5},
    {"programma", 4.8},
    {"ragiona", 5.5},
    {"refactoring", 5.2},
    {"riassumi", 4.5},
    {"risolvi", 4.5},
    {"scrivi", 3.8},
    {"sintesi", 4.8},
    {"spiega", 4.5},
    {"strategia", 5.2},
    {"sviluppa", 5.0},
};
constexpr size_t COMPLEX_TOKENS_COUNT = sizeof(COMPLEX_TOKENS) / sizeof(COMPLEX_TOKENS[0]);

}

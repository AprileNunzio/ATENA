#include "edge_router.h"

#include <math.h>
#include <string.h>

#include "edge_router_model.h"

namespace atena_edge {
namespace {

struct Token {
    char text[MAX_TOKEN_BYTES + 1];
    size_t length;
};

template <typename Row>
const Row* find(const Row* rows, size_t count, const char* token) {
    size_t low = 0;
    size_t high = count;
    while (low < high) {
        const size_t mid = low + (high - low) / 2;
        const int order = strcmp(rows[mid].token, token);
        if (order == 0) {
            return &rows[mid];
        }
        if (order < 0) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }
    return nullptr;
}

bool latin_letter(unsigned char lead, unsigned char next) {
    if (lead == 0xC3) {
        return next >= 0x80 && next <= 0xBF && next != 0x97 && next != 0xB7;
    }
    return lead == 0xC4 || lead == 0xC5;
}

size_t tokenize(const char* text, size_t length, Token* out, size_t capacity, bool* truncated) {
    size_t count = 0;
    size_t i = 0;
    *truncated = length > MAX_INPUT_BYTES;
    if (*truncated) {
        length = MAX_INPUT_BYTES;
    }
    Token current{};
    auto flush = [&]() {
        if (current.length == 0) {
            return;
        }
        if (count < capacity) {
            current.text[current.length] = '\0';
            out[count] = current;
        } else {
            *truncated = true;
        }
        ++count;
        current.length = 0;
    };
    auto push = [&](unsigned char byte) {
        if (current.length < MAX_TOKEN_BYTES) {
            current.text[current.length++] = static_cast<char>(byte);
        } else {
            *truncated = true;
        }
    };
    while (i < length) {
        const unsigned char c = static_cast<unsigned char>(text[i]);
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_') {
            push(c);
            ++i;
        } else if (c >= 'A' && c <= 'Z') {
            push(static_cast<unsigned char>(c + 32));
            ++i;
        } else if (c >= 0x80 && i + 1 < length && latin_letter(c, static_cast<unsigned char>(text[i + 1]))) {
            unsigned char next = static_cast<unsigned char>(text[i + 1]);
            if (c == 0xC3 && next >= 0x80 && next <= 0x9E) {
                next = static_cast<unsigned char>(next + 0x20);
            }
            push(c);
            push(next);
            i += 2;
        } else {
            flush();
            if (c < 0x80) {
                ++i;
            } else if ((c & 0xE0) == 0xC0) {
                i += 2;
            } else if ((c & 0xF0) == 0xE0) {
                i += 3;
            } else if ((c & 0xF8) == 0xF0) {
                i += 4;
            } else {
                ++i;
            }
        }
    }
    flush();
    return count;
}

template <typename Row>
bool contains_any(const Token* tokens, size_t count, const Row* rows, size_t rows_count) {
    for (size_t i = 0; i < count; ++i) {
        if (find(rows, rows_count, tokens[i].text) != nullptr) {
            return true;
        }
    }
    return false;
}

}

const char* intent_name(Intent intent) {
    switch (intent) {
        case Intent::Conversation:
            return "conversation";
        case Intent::ActionDirect:
            return "action_direct";
        case Intent::WhiteboardCanvas:
            return "whiteboard_canvas";
        case Intent::BrowserAction:
            return "browser_action";
        case Intent::ComplexTask:
            return "complex_task";
    }
    return "conversation";
}

Decision classify(const char* utf8, size_t length) {
    static Token tokens[MAX_TOKENS];
    Decision decision{};
    for (double& logit : decision.logits) {
        logit = 0.5;
    }
    decision.intent = Intent::Conversation;
    if (utf8 == nullptr) {
        length = 0;
    }
    const size_t total = tokenize(utf8 == nullptr ? "" : utf8, length, tokens, MAX_TOKENS, &decision.truncated);
    const size_t stored = total < MAX_TOKENS ? total : MAX_TOKENS;
    decision.tokens = total;

    double* logits = decision.logits;
    const bool has_whiteboard = contains_any(tokens, stored, WHITEBOARD_TOKENS, WHITEBOARD_TOKENS_COUNT);
    const bool has_browser = contains_any(tokens, stored, BROWSER_TOKENS, BROWSER_TOKENS_COUNT);
    const bool has_chitchat = contains_any(tokens, stored, CHITCHAT_TOKENS, CHITCHAT_TOKENS_COUNT);

    for (size_t i = 0; i < stored; ++i) {
        const char* token = tokens[i].text;
        if (const ScoredToken* row = find(CHITCHAT_TOKENS, CHITCHAT_TOKENS_COUNT, token)) {
            logits[0] += row->score;
        }
        if (const ScoredToken* row = find(WHITEBOARD_TOKENS, WHITEBOARD_TOKENS_COUNT, token)) {
            logits[2] += row->score;
        }
        if (const ScoredToken* row = find(BROWSER_TOKENS, BROWSER_TOKENS_COUNT, token)) {
            logits[3] += row->score;
        }
        if (const ActionToken* row = find(ACTION_TOKENS, ACTION_TOKENS_COUNT, token)) {
            if (!has_whiteboard && !has_browser) {
                logits[1] += row->score;
                if (decision.agent == nullptr) {
                    decision.agent = row->agent;
                    decision.action = row->action;
                }
            }
        }
        if (const ScoredToken* row = find(COMPLEX_TOKENS, COMPLEX_TOKENS_COUNT, token)) {
            logits[4] += row->score;
        }
    }

    if (has_whiteboard) {
        logits[1] = 0.5;
        decision.agent = "whiteboard";
        decision.action = "open_whiteboard";
    } else if (has_browser) {
        logits[1] = 0.5;
        decision.agent = "browser_agent";
        decision.action = "navigate_web";
    } else if (has_chitchat && logits[0] > logits[1] && logits[0] > logits[4]) {
        decision.agent = "atena_conversation";
        decision.action = "chat_reply";
    }

    if (total > 20) {
        const double bonus = static_cast<double>(total - 20) * 0.15;
        logits[4] += bonus < 3.5 ? bonus : 3.5;
    } else if (total <= 6 && logits[1] > 2.0) {
        logits[1] += 2.0;
    }

    double peak = logits[0];
    for (size_t i = 1; i < INTENT_COUNT; ++i) {
        if (logits[i] > peak) {
            peak = logits[i];
        }
    }
    double exps[INTENT_COUNT];
    double sum = 0.0;
    for (size_t i = 0; i < INTENT_COUNT; ++i) {
        exps[i] = exp(logits[i] - peak);
        sum += exps[i];
    }
    size_t best = 0;
    for (size_t i = 1; i < INTENT_COUNT; ++i) {
        if (exps[i] > exps[best]) {
            best = i;
        }
    }
    decision.intent = static_cast<Intent>(best);
    decision.confidence = exps[best] / sum;
    return decision;
}

bool handle_locally(const Decision& decision, double threshold) {
    return decision.intent == Intent::ActionDirect && decision.confidence >= threshold && !decision.truncated &&
           decision.agent != nullptr;
}

}

#pragma once

#include <stddef.h>

namespace atena_edge {

enum class Intent : unsigned char {
    Conversation = 0,
    ActionDirect = 1,
    WhiteboardCanvas = 2,
    BrowserAction = 3,
    ComplexTask = 4,
};

constexpr size_t INTENT_COUNT = 5;
constexpr size_t MAX_TOKENS = 96;
constexpr size_t MAX_TOKEN_BYTES = 48;
constexpr size_t MAX_INPUT_BYTES = 1024;

struct Decision {
    Intent intent;
    double confidence;
    double logits[INTENT_COUNT];
    const char* agent;
    const char* action;
    size_t tokens;
    bool truncated;
};

const char* intent_name(Intent intent);
Decision classify(const char* utf8, size_t length);
bool handle_locally(const Decision& decision, double threshold);

}

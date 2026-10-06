import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from server.core.orchestrator.system1_router import System1Intent, System1Router

DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "client_satellite" / "microcontrollers" / "esp32" / "src" / "edge_router_model.h"
INTENTS: Tuple[str, ...] = tuple(i.value for i in System1Intent)


def model_tables(router: System1Router) -> Dict[str, object]:
    return {
        "intents": list(INTENTS),
        "action": sorted((t, a, s, float(v)) for t, (a, s, v) in router._action_tokens.items()),
        "chitchat": sorted((t, float(v)) for t, v in router._chitchat_tokens.items()),
        "whiteboard": sorted((t, float(v)) for t, v in router._whiteboard_tokens.items()),
        "browser": sorted((t, float(v)) for t, v in router._browser_tokens.items()),
        "complex": sorted((t, float(v)) for t, v in router._complex_tokens.items()),
    }


def digest(tables: Dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(tables, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _literal(text: str) -> str:
    out = []
    for byte in text.encode("utf-8"):
        out.append(chr(byte) if 0x20 <= byte < 0x7F and chr(byte) not in '"\\?' else f"\\x{byte:02x}\" \"")
    return '"' + "".join(out) + '"'


def _scored(name: str, rows: List[Tuple[str, float]]) -> List[str]:
    lines = [f"constexpr ScoredToken {name}[] = {{"]
    lines += [f"    {{{_literal(t)}, {v!r}}}," for t, v in rows]
    lines += ["};", f"constexpr size_t {name}_COUNT = sizeof({name}) / sizeof({name}[0]);", ""]
    return lines


def render(router: System1Router) -> str:
    tables = model_tables(router)
    lines = [
        "#pragma once",
        "",
        "#include <stddef.h>",
        "",
        "namespace atena_edge {",
        "",
        f"constexpr char MODEL_DIGEST[] = \"{digest(tables)}\";",
        "",
        "struct ScoredToken {",
        "    const char* token;",
        "    double score;",
        "};",
        "",
        "struct ActionToken {",
        "    const char* token;",
        "    const char* agent;",
        "    const char* action;",
        "    double score;",
        "};",
        "",
        "constexpr ActionToken ACTION_TOKENS[] = {",
    ]
    lines += [f"    {{{_literal(t)}, {_literal(a)}, {_literal(s)}, {v!r}}}," for t, a, s, v in tables["action"]]
    lines += ["};", "constexpr size_t ACTION_TOKENS_COUNT = sizeof(ACTION_TOKENS) / sizeof(ACTION_TOKENS[0]);", ""]
    lines += _scored("CHITCHAT_TOKENS", tables["chitchat"])
    lines += _scored("WHITEBOARD_TOKENS", tables["whiteboard"])
    lines += _scored("BROWSER_TOKENS", tables["browser"])
    lines += _scored("COMPLEX_TOKENS", tables["complex"])
    lines += ["}", ""]
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Export the System 1 router to a C++ header for edge satellites")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = render(System1Router())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != content:
            print(f"{args.output} is stale: regenerate it", file=sys.stderr)
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

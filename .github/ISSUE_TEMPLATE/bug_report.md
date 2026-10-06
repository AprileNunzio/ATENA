---
name: Bug report
about: Something does not work as documented
title: '[BUG] '
labels: bug
assignees: ''

---

> **Security problem?** Do not open a public issue. Follow [SECURITY.md](../../SECURITY.md).

**What happened**
A clear description of the problem and what you expected instead.

**How to reproduce**
1. …
2. …
3. …

If it involves a voice command, write the **exact sentence** and what Atena answered.

**Environment**
- Atena version: <!-- output of `atenactl version`, or the commit shown at `/api/state` -->
- Installation: <!-- real server (Debian/Ubuntu version, x86_64/arm64) or demo mode (`ATENA_DEMO=1`) -->
- Hardware: <!-- CPU, RAM, GPU, webcam, microphone, display, smart-home hub -->
- Brain: <!-- local model, other server, cloud provider; from the Brain tab -->
- Affected feature: <!-- e.g. music, whiteboard, MCP, understanding, vision, home -->

**Evidence**
- Output of `atenactl status` or the relevant part of `http://<server>/api/state`
- Logs: `atenactl logs <install|supervisor|core|ollama|voice|vision|ear>`
- For a mis-routed command: the decision shown at `/api/understanding`
- For MCP problems: the status code and the entry in `/api/mcp/audit`

**Remove secrets before pasting**: tokens, API keys, passwords, IP addresses you do not want public, and
personal data (names, calendar entries, camera frames, voice samples).

**Additional context**
Anything else that helps: screenshots, recent changes, whether it worked in a previous version.

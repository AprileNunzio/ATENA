## What and why
<!-- The problem, what changes for the user, and why this design. Link the issue: Fixes #123 -->

## Type of change
- [ ] Bug fix
- [ ] New feature, tool, widget, algorithm or installation step
- [ ] Refactoring without behavior change
- [ ] Documentation or tests only
- [ ] Breaking change (configuration, API, data format)

## Verification
<!-- Commands you ran, test names, screenshots or recordings for UI changes. -->

## Security and privacy
- [ ] Every new endpoint declares its audience (`require_admin`, `require_display`, node token or signed URL) and validates input, sizes and paths
- [ ] Sensitive actions are confirmed **in code** (`confirm`), and success is checked with `verify` where possible
- [ ] Untrusted content (web, e-mail, documents, external MCP replies, model output) is treated as data and cannot trigger sensitive actions
- [ ] No secrets, personal data or internal addresses in code, tests, logs or examples
- [ ] Anything that sends data outside the server is optional, documented and can be switched off
- [ ] Not applicable (explain why)

## Engineering checklist
- [ ] Clean architecture and single responsibility respected; code organized by feature
- [ ] No comments or docstrings; expressive names and type hints
- [ ] No file over 500 lines (the README is the only exception)
- [ ] Errors are not silenced; user-facing messages are in Italian
- [ ] Tests added or updated; they run offline without real devices or services
- [ ] CI commands from [CONTRIBUTING.md](../CONTRIBUTING.md#testing-and-checks) pass locally
- [ ] README and `installer_wizard/MCP.md` updated if behavior, variables, API routes or security properties change
- [ ] Commits are signed off (`git commit -s`) and I have the right to submit this code under the MIT License

## Upgrade impact
<!-- Effect on existing installations: defaults, migrations, new steps or variables, rollback considerations. -->

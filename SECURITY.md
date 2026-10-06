# Security Policy

*Riepilogo in italiano in fondo al documento.*

Atena OS runs on a home server with access to microphones, cameras, files, smart-home devices and a shell, and
it can be driven by external assistants over MCP. Security is therefore a design requirement, not an
afterthought: the project follows a **zero-trust** model in which every endpoint, tool call and input is
authenticated, validated and, when it can change the real world, confirmed **in code** (never only in a prompt).
The full model is described in the [README, section 20](README.md#20-sicurezza-e-privacy).

## Supported versions

Security fixes are applied to the current major version. Installations update themselves from `main`, and only
to commits whose CI run is green, so a fix normally reaches every installation within minutes of being merged.

| Version | Supported |
| :--- | :---: |
| 3.x (`main`) | :white_check_mark: |
| 2.x and earlier | :x: |

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for a security problem.**

Report it privately through one of these channels:

1. **GitHub private vulnerability reporting**: *Security → Report a vulnerability* on the repository page
   (when enabled for the repository).
2. **E-mail**: `security@nunziotech.com`, or `aprilenunzio88@gmail.com` if you get no reply.
   Use the subject *Atena security report*. If you need an encrypted channel, say so in a first message without
   technical details and one will be arranged.

Please include, as far as you can:

- the affected component and version (`atenactl version`, or the commit shown by `/api/state`);
- a description of the issue and its impact (what an attacker gains, and what access is required);
- clear reproduction steps or a proof of concept, and the configuration involved (for example the MCP token
  level, the `ATENA_AGENT_ACCESS` value, whether the demo mode was used);
- relevant logs, with secrets, tokens and personal data removed;
- whether you intend to publish your findings, and when.

### What to expect

| Step | Target |
| :--- | :--- |
| Acknowledgement of your report | within **3 working days** |
| Initial assessment and severity (CVSS) | within **7 days** |
| Fix for a *critical* issue | as soon as possible, target **7 days** |
| Fix for a *high* issue | target **14 days** |
| Fix for a *medium* issue | target **30 days** |
| Fix for a *low* issue | next regular release |
| Public advisory | after the fix is released, in agreement with you |

These are targets for a small team, not guarantees; you will be told if one cannot be met and why. We follow
**coordinated disclosure**: please give us a reasonable time to fix the issue before publishing, up to **90
days** from the report. Reporters are credited in the advisory unless they prefer to stay anonymous. A GitHub
Security Advisory (and a CVE, when appropriate) is published for confirmed vulnerabilities. There is no bug
bounty program.

### Safe harbor

We will not take legal action against, and will not ask the authorities to pursue, people who research and
report vulnerabilities in good faith under this policy. Good faith means: testing only on installations you own
or are explicitly authorized to test, not accessing or keeping more data than needed to show the problem, not
degrading the service for others, not using social engineering or physical attacks, and giving us time to fix
the issue before disclosure.

## Scope

In scope:

- the supervisor and its two web applications (display on port 80, admin panel on port 8080), authentication,
  sessions and the anti-CSRF protection;
- the **MCP server** (`/mcp`), its tokens, access levels, origin check, rate limits and audit log, and the **MCP
  client** (connections to external servers);
- tools, agent delegation, the forge (tools, widgets and features created by Atena) and the understanding layer;
- node pairing, node tokens and the satellite agents;
- Atena Core (`server/`), the sandbox broker (`sandbox_broker/`) and the isolation of generated code;
- the music server (signed media URLs, share links, the compatible `/rest` API), the whiteboard and the camera
  streams;
- the installer, the update mechanism and the rollback logic (supply chain of the installation itself);
- secrets handling: sealed files, the cloud vault, `atena.env` permissions.

Out of scope (unless you can show a concrete security impact):

- social engineering, physical access to the server, and attacks that require an already-compromised admin
  account or a token created by the administrator with full access acting as intended;
- volumetric denial of service, and findings against third-party services Atena can be connected to;
- vulnerabilities in dependencies without a demonstrated way to exploit them in Atena;
- missing best-practice headers or settings with no practical impact;
- the `docker-compose.yml` and `Dockerfile` in the repository root, which are for local development only and use
  placeholder credentials;
- behavior that only appears after an administrator deliberately lowers a protection (for example
  `ATENA_UPDATE_REQUIRE_CI=0`, or marking an external MCP server as trusted).

## Security model in brief

| Area | What the project does |
| :--- | :--- |
| Access | Admin panel behind PAM with system admin groups, lockout after repeated failures, signed 12-hour sessions, anti-CSRF header on every change |
| Secrets | Files with `600` permissions, API keys and tokens in Fernet-sealed files, secrets never returned by the API; MCP tokens stored only as SHA-256 digests |
| MCP | Bearer tokens, two access levels, confirmation required in code for sensitive tools, origin check, rate limits, audit trail; external servers untrusted by default and their replies treated as data |
| Agents and forge | Confirmation is decided by each tool, inherited by delegation and by created tools; the forge produces validated descriptions, never executable code |
| Generated code | Analyzed, then run only in an isolated sandbox (no network by default, read-only filesystem, no capabilities, resource limits; gVisor or Firecracker when available) |
| Network | Host firewall, services bound to `127.0.0.1`, signed Core tokens, signed and expiring media URLs |
| Privacy | Local by default; cloud, online voices and music recognition are optional; cameras off by default; widgets with personal data close when the person leaves |
| Updates | Only commits with a green CI run, post-install verification, nightly self-test and automatic rollback |

## Hardening guidance for operators

- Keep ports 80 and 8080 on your **local network**. Do not expose them to the Internet; for remote access use a
  VPN or an HTTPS reverse proxy with its own authentication. The MCP endpoint uses plain HTTP on the LAN.
- Use strong passwords for the system users in the `atena-admin` group and for the shared folder user.
- Create **standard** MCP tokens by default. Give **full access** tokens only to clients you trust, name them,
  review the audit log (`/api/mcp/audit`) and revoke tokens you no longer use.
- Keep **automatic updates** and `ATENA_UPDATE_REQUIRE_CI=1` enabled, and leave the nightly self-test on.
- Use `ATENA_AGENT_ACCESS=standard` if the agent does not need the whole server.
- Mark an external MCP server as *trusted* only if you control it.
- Turn on cameras and recording only with the consent of the people filmed.

If you find a secret (key, token, password) committed to the repository or pasted in an issue, report it
privately at once so that it can be rotated.

---

# Politica di sicurezza (italiano)

Atena OS gira su un server di casa con accesso a microfoni, telecamere, file, domotica e shell, e può essere
guidato da assistenti esterni via MCP: la sicurezza è un requisito di progetto. Modello **zero-trust**: ogni
endpoint, strumento e input è autenticato e validato, e ciò che può cambiare il mondo reale è confermato **dal
codice**, non solo dal prompt (dettagli nel [README, §20](README.md#20-sicurezza-e-privacy)).

- **Versioni supportate**: 3.x (`main`); le installazioni si aggiornano da sole solo con CI verde.
- **Come segnalare**: in privato, mai con una issue pubblica. Con la segnalazione privata di GitHub
  (*Security → Report a vulnerability*, se attiva) oppure via e-mail a `security@nunziotech.com` (in alternativa
  `aprilenunzio88@gmail.com`), oggetto «Atena security report». Indicare componente e versione, impatto, passi
  per riprodurre, configurazione e log senza segreti.
- **Tempi (obiettivi)**: conferma entro 3 giorni lavorativi, valutazione entro 7 giorni; correzione entro 7 giorni
  se critica, 14 se alta, 30 se media, alla prossima versione se bassa; avviso pubblico dopo la correzione.
- **Divulgazione coordinata**: fino a 90 giorni dalla segnalazione; chi segnala è citato se lo desidera; non c'è
  un programma di ricompense.
- **Porto sicuro**: nessuna azione legale verso chi ricerca in buona fede, su installazioni proprie o autorizzate,
  senza danneggiare il servizio né accedere a più dati del necessario.
- **Ambito**: supervisore, pannello, server e client MCP, strumenti e fucina, nodi, Core e sandbox, musica,
  lavagna e telecamere, installatore e aggiornamenti, gestione dei segreti. **Fuori ambito**: ingegneria sociale,
  accesso fisico, DoS volumetrico, dipendenze senza exploit dimostrato, `Dockerfile` e `docker-compose.yml` della
  radice (solo sviluppo locale), comportamenti dovuti a protezioni abbassate di proposito dall'amministratore.
- **Consigli a chi installa**: porte 80 e 8080 solo in rete locale (VPN o proxy HTTPS per l'accesso esterno),
  password robuste, token MCP standard per default e accesso completo solo a client fidati con revoca e controllo
  del registro, aggiornamenti automatici e collaudo attivi, telecamere solo con il consenso delle persone.

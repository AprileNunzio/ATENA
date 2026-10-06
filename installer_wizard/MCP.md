# Atena · agenti, MCP e fucina

Piano di implementazione e guida d'uso. Stato: **realizzato** (fasi 1-7), fase 8 da fare.

## Obiettivo

Qualsiasi assistente AI, locale o cloud, deve poter scoprire e usare tutto ciò che Atena sa fare. Ciò che Atena crea da sola (strumenti, widget, funzionalità) deve diventare subito disponibile senza riavvii. Ogni comando deve avere un esito verificato.

## Fasi

| # | Fase | Contenuto | Stato |
|---|------|-----------|-------|
| 1 | Squadra di agenti | Un agente per ogni funzionalità, con priorità, lavagna comune, messaggi, deleghe, risorse contese | fatto |
| 2 | Catalogo per gli LLM | Frasi, squadra e lavagna nel prompt di ogni modello (locale e cloud); `/api/capabilities` | fatto |
| 3 | Esito verificato | Dopo ogni comando di musica o telecamere si controlla il risultato; un nuovo tentativo, poi errore esplicito | fatto |
| 4 | Server MCP | `POST /mcp` (porta 8080): `initialize`, `tools`, `resources`, `prompts`; versioni 2025-06-18, 2025-03-26, 2024-11-05; schemi JSON dagli stessi strumenti | fatto |
| 5 | Sicurezza MCP | Token con impronta SHA-256 e revoca, blocco dopo tentativi errati, limite di 120 richieste al minuto per token, controllo dell'origine, corpo massimo 256 KB, registro delle chiamate | fatto |
| 6 | Fucina | Atena crea strumenti (sequenze di strumenti con parametri), widget e funzionalità; compaiono subito nell'MCP con notifica `list_changed` | fatto |
| 7 | Client MCP | Atena usa gli strumenti di altri server MCP come propri agenti: pannello "Server MCP", aggiornamento ogni 5 minuti, conferma per i server non fidati, risposte trattate come dati | fatto |
| 8 | Prove su hardware | Chromecast, DLNA, microfono, telecamere reali | da fare |

## Collegare un assistente esterno

1. Pannello admin → **Squadra e MCP** → scrivi il nome del client → **Crea token**.
2. Copia la configurazione mostrata (il token compare una sola volta) nel client.
3. Due livelli di token:
   - **standard**: musica, telecamere, widget, coordinamento, letture;
   - **accesso completo**: tutti gli strumenti, anche file, comandi, impostazioni e fucina. Le azioni delicate richiedono `_confirm=true` dopo la conferma dell'utente.
4. Per revocare: pulsante **Revoca** accanto al token.

Cosa vede il client:
- **Strumenti**: ogni strumento ha schema JSON, agente proprietario e indicazioni (sola lettura, richiede conferma).
- **Risorse**: `atena://capabilities`, `atena://team`, `atena://widgets`, `atena://agent/<id>`.
- **Prompt**: `panoramica` e `agente`.
- **Notifiche**: `GET /mcp` apre un flusso che avvisa quando cambiano strumenti, widget o funzionalità.

## Collegare Atena a server MCP esterni

Pannello **Squadra e MCP** → *Server MCP a cui Atena si collega*: nome, indirizzo http(s)://…, token facoltativo. Gli strumenti compaiono come xt_<server>_<strumento> (massimo 40 per server) e sono disponibili all'agente e ai client con token completo. Un server **non fidato** chiede conferma prima di ogni azione, salvo gli strumenti dichiarati di sola lettura; le risposte sono segnate come dati esterni e non come istruzioni. Il token è salvato in un file leggibile solo dal sistema e non viene mai mostrato dal pannello.

## Fucina

Gli strumenti che Atena crea sono **descrizioni**, non codice:
- `create_tool`: elenco di passi `{tool, args}`; segnaposto `{{parametro}}` e `{{s1}}`, `{{s2}}` per i risultati dei passi precedenti. Massimo 10 passi, 8 parametri. Passi solo su strumenti di sistema (niente ricorsione). La conferma dello strumento è quella dei suoi passi.
- `create_widget`: widget con titolo, valore, testo ed elenco, mostrato poi con `show_widget`.
- `create_feature`: nuova funzionalità, che diventa subito un agente della squadra.
- Le eliminazioni (`delete_tool`, `delete_widget`, `delete_feature`) toccano solo ciò che ha creato Atena e chiedono sempre conferma.

I dati creati stanno nella cartella di stato (`tools/`, `widgets/`, `features/`) e sopravvivono ai riavvii.

## Limiti noti

- L'MCP è su HTTP nella rete locale: per l'uso fuori casa serve un canale cifrato (VPN o proxy HTTPS).
- Un token con accesso completo equivale a un amministratore: crealo solo per client fidati e revocalo quando non serve.
- Niente è stato provato su dispositivi reali.

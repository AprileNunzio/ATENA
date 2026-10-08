# Controllo Remoto dei Computer con ATENA

Questa guida illustra come aggiungere e gestire in sicurezza i computer della tua rete all'interno di ATENA, utilizzando standard di livello Enterprise senza compromettere la sicurezza del sistema.

ATENA non utilizza software "agent" vulnerabili che lasciano porte aperte all'esecuzione di codice arbitrario, ma supporta tre protocolli sicuri:

1. **WinRM** (Nativo per Windows)
2. **OpenSSH** (Standard cross-platform)
3. **REST API** (Microservizio Custom Sicuro)

---

## 1. Configurare un PC Windows con WinRM (Consigliato)
Windows Remote Management è integrato in tutti i PC Windows ed è il metodo più semplice per permettere ad ATENA di controllare lo stato e gli aggiornamenti.

**Sul PC da controllare (es. PC10):**
1. Apri una finestra di PowerShell come Amministratore.
2. Esegui il comando di configurazione rapida:
   ```powershell
   Enable-PSRemoting -Force
   ```
3. Se ATENA si trova su una rete diversa o senza dominio, configura i trusted host:
   ```powershell
   Set-Item WSMan:\localhost\Client\TrustedHosts -Value "<Indirizzo_IP_Atena>" -Force
   ```

**In ATENA:**
Configura il manager nel server passando le credenziali del PC10:
```python
from server.features.remote_control.manager import RemoteComputerManager, WinRMProtocol

manager = RemoteComputerManager()
manager.add_computer("PC10", WinRMProtocol("192.168.1.10", "NomeUtente", "PasswordSegreta"))
```

---

## 2. Configurare un PC tramite OpenSSH
Ideale se preferisci utilizzare certificati crittografici al posto delle password.

**Sul PC da controllare:**
1. Vai su *Impostazioni > App > Funzionalità facoltative* e installa **OpenSSH Server**.
2. Avvia il servizio `sshd` da `services.msc` e impostalo su "Automatico".
3. Aggiungi la chiave pubblica SSH di ATENA nel file `C:\Users\NomeUtente\.ssh\authorized_keys`.

**In ATENA:**
```python
from server.features.remote_control.manager import SSHProtocol

manager.add_computer("PC11", SSHProtocol("192.168.1.11", "NomeUtente", "/percorso/chiave/atena_rsa"))
```

---

## 3. Configurare un Microservizio REST ad API Fisse
Se hai bisogno di creare un tuo agent (es. un servizio in background locale), assicurati che esponga solo endpoint HTTP/REST predefiniti (es. `/api/v1/updates/check`) protetti da un token. In questo modo l'agent agirà come esecutore di compiti chiusi.

**In ATENA:**
```python
from server.features.remote_control.manager import RestApiProtocol

manager.add_computer("PC12", RestApiProtocol("https://192.168.1.12:8443", "il_tuo_token_api"))
```

---

## Eseguire i controlli dalla chat di ATENA

Una volta configurati i PC, l'agente "Sysops" o "Domotics" di ATENA riconoscerà automaticamente i nomi (es. `PC10`). 
Se chiedi in chat:
> *"Controlla gli aggiornamenti su PC10"*

ATENA si connetterà in modo trasparente e ti risponderà con i risultati, senza che alcun comando malevolo possa transitare sulla rete.

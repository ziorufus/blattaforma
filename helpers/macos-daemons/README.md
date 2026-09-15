# Installazione su un Mac (modulo `macos-daemons`)

Questi file vanno installati a mano su ogni Mac che deve poter essere
gestito dal modulo `macos-daemons`. Presuppone che su quella macchina giri
già nginx per il modulo `ollama` (stesso utente, es. `alessio`).

## 1. Albero sotto `/opt/blattaforma-daemons`

```
sudo mkdir -p /opt/blattaforma-daemons/{bin,etc,helper,var/log}
```

Copiare da questo repo:

- `bin/daemonctl` → `/opt/blattaforma-daemons/bin/daemonctl`
- `helper/helper_service.py` → `/opt/blattaforma-daemons/helper/helper_service.py`
- `etc/daemons-whitelist.example.json` → `/opt/blattaforma-daemons/etc/daemons-whitelist.json`
  (poi modificarlo con i demoni reali di questa macchina)

Permessi -- **fondamentale per la sicurezza**, non solo sui file ma sulle
cartelle che li contengono (altrimenti l'utente non privilegiato potrebbe
rimpiazzarli con un `rename`, anche senza permesso di scrittura sul singolo
file):

```
sudo chown -R root:wheel /opt/blattaforma-daemons/bin /opt/blattaforma-daemons/etc
sudo chmod 0755 /opt/blattaforma-daemons /opt/blattaforma-daemons/bin /opt/blattaforma-daemons/etc
sudo chmod 0700 /opt/blattaforma-daemons/bin/daemonctl
sudo chmod 0600 /opt/blattaforma-daemons/etc/daemons-whitelist.json

sudo chown -R alessio:staff /opt/blattaforma-daemons/helper /opt/blattaforma-daemons/var
```

## 2. sudoers

```
sudo visudo -c -f sudoers.d/blattaforma-daemons   # valida PRIMA di installare
sudo cp sudoers.d/blattaforma-daemons /etc/sudoers.d/blattaforma-daemons
sudo chown root:wheel /etc/sudoers.d/blattaforma-daemons
sudo chmod 0440 /etc/sudoers.d/blattaforma-daemons
sudo visudo -c   # valida l'intero set di file sudoers dopo l'installazione
```

Se l'utente che fa girare nginx/l'helper su questa macchina non è `alessio`,
modificare il nome utente nel file prima di installarlo.

## 3. LaunchAgent per l'helper

```
cp launchd/com.blattaforma.macos-daemons-helper.plist \
   ~/Library/LaunchAgents/com.blattaforma.macos-daemons-helper.plist
launchctl bootstrap gui/$(id -u) \
   ~/Library/LaunchAgents/com.blattaforma.macos-daemons-helper.plist
```

Verificare che sia partito: `curl -s http://127.0.0.1:8765/status` deve
rispondere (404 "unknown action" è normale con una GET/path vuoto: conferma
solo che il servizio ascolta).

## 4. Config nginx

Copiare `nginx-conf/macos-daemons/servers/macos-daemons.conf`,
`nginx-conf/macos-daemons/snippets/*.conf` e
`nginx-conf/macos-daemons/macos_daemons_guard.js` nelle stesse cartelle
relative già usate per `ollama` nella config nginx di questa macchina.

**Prima di ricaricare nginx**, modificare
`snippets/macos-daemons-auth-upstream.conf`: sostituire `mac-mini-195` con
lo slug di questa macchina (vedi commento nel file).

```
sudo nginx -t && sudo nginx -s reload
```

## 5. Registrazione lato Blattaforma

Da Amministrazione, assegnare il ruolo `operate` del modulo `macos-daemons`
a chi deve poterlo usare. Poi dalla pagina "Macchine" del modulo:

- creare la macchina con lo stesso slug usato al punto 4 e l'indirizzo IP
  di questa macchina;
- come "chiave di controllo" generare una stringa casuale lunga (es.
  `openssl rand -hex 32`) e usare lo stesso valore... non serve scriverlo
  da nessuna parte sul Mac: è il backend centrale a presentarlo come
  `Authorization: Bearer` quando chiama questa macchina, e questa macchina
  lo verifica facendo eco alla domanda al backend stesso (`/check`) -- la
  chiave vive solo nel DB centrale.

Poi, dalla dashboard del modulo, aggiungere un "Demone" per ogni voce già
presente in `/opt/blattaforma-daemons/etc/daemons-whitelist.json` su questa
macchina (stessa `label` e `plist_path`): è solo una copia per la UI, la
whitelist reale resta quella del file.

## 6. Collaudo

Prima di estendere ad altre macchine, verificare su questa (il "Mac
canarino") che avvio/stop/enable/disable/stato funzionino davvero dalla
dashboard, con un demone di prova non critico.

# Blattaforma — guida per la creazione di moduli

Questo testo descrive l'architettura di Blattaforma per un'AI a cui viene
chiesto di progettare/scrivere un nuovo modulo. Non serve leggere il resto
del codebase per iniziare: quanto segue è sufficiente per capire dove
scrivere cosa e quali regole rispettare.

## 1. Cos'è Blattaforma

Piattaforma modulare con login solo via Google OAuth2 (nessuna password nel
DB), permessi granulari per utente/gruppo/modulo, e moduli funzionali
installabili "a cartella" senza toccare il codice core.

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite, JWT — cartella `backend/`
- **Frontend**: Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue
  Router, Bootstrap 5 — cartella `frontend/`

## 2. Modello di autenticazione e permessi (già implementato, non toccare)

- Login solo Google. Al login il backend rilascia un JWT; il token si
  rinnova da solo ad ogni richiesta (middleware lato backend + interceptor
  axios lato frontend). **Un modulo non deve mai gestire login, token o
  scadenze**: arriva già tutto risolto.
- Tabella `users`: ogni utente ha un flag `is_admin`. Un admin ha **sempre**
  accesso completo a tutti i moduli, con tutti i ruoli disponibili.
- Tabella `groups`: raggruppano utenti per assegnare permessi in blocco.
- Permessi: per ogni coppia (utente **o** gruppo) × modulo si assegnano uno o
  più **ruoli** — stringhe libere definite dal modulo stesso (es.
  `"standard"`, `"premium"`, `"editor"`...). I permessi diretti dell'utente e
  quelli ereditati dai suoi gruppi **si sommano** (unione, mai sovrascrittura).
- Un modulo **non implementa una propria logica di permessi**: dichiara solo
  l'elenco dei ruoli possibili (`MODULE_ROLES`) e il framework centrale
  calcola, per ogni richiesta, l'insieme di ruoli concessi all'utente
  corrente su quel modulo specifico.
- Gestione di utenti/gruppi/permessi è riservata agli admin tramite il menu
  "Amministrazione" già esistente — un modulo non deve fornire una propria UI
  per gestire chi vi ha accesso.

## 3. Contratto di un modulo — Backend

Un modulo backend è **un solo file** in `backend/app/modules/<nome_file>.py`.
Al riavvio del backend viene scoperto automaticamente: il suo router viene
montato su `/api/modules/{MODULE_NAME}/...` e una riga viene
inserita/aggiornata nella tabella `modules` del DB. **Non serve nessuna
registrazione manuale altrove** (non toccare `main.py`).

Il file deve esportare esattamente questi 4 simboli a livello di modulo:

| Simbolo | Significato |
|---|---|
| `MODULE_NAME` | slug univoco in tutta la piattaforma: solo lettere, numeri, `-`, `_`. Diventa il prefisso URL sia in API (`/api/modules/<MODULE_NAME>/...`) sia nel frontend (`/modules/<MODULE_NAME>/...`). |
| `MODULE_LABEL` | nome leggibile mostrato nel menu del frontend. |
| `MODULE_ROLES` | lista di stringhe: i ruoli possibili per questo modulo. |
| `router` | un `fastapi.APIRouter` con gli endpoint del modulo. |

Nota sul nome del file: i moduli Python non possono contenere trattini, quindi
se `MODULE_NAME = "il-mio-modulo"` il file si chiamerà per convenzione
`il_mio_modulo.py` (underscore). `MODULE_NAME` resta invariato (con i
trattini) ovunque venga esposto (URL, DB, frontend).

Per proteggere un endpoint in base ai permessi, usare la dependency già
pronta `require_module_role` (da `app.deps`): restituisce la lista dei ruoli
concessi all'utente corrente per quel modulo — **non è mai vuota**, perché se
l'utente non ha alcun accesso la dependency solleva da sola un 403. Un admin
riceve automaticamente tutti i ruoli dichiarati dal modulo.

Per l'utente autenticato: `Depends(get_current_user)` (da `app.deps`)
restituisce l'oggetto `models.User`. Per accedere al DB:
`Depends(get_db)` (da `app.deps`) dà una sessione SQLAlchemy.

Se il modulo ha bisogno di proprie tabelle: definire i modelli SQLAlchemy nel
file ereditando da `app.database.Base`, e alla fine del file chiamare
esplicitamente `Base.metadata.create_all(bind=engine)` (import da
`app.database`). È necessario perché il bootstrap del DB avviene **prima**
che i file dei moduli vengano importati; la chiamata è idempotente (crea solo
le tabelle mancanti), quindi ripeterla non ha effetti collaterali.

Esempio minimo completo (modulo reale già presente, `hello-world`):

```python
# backend/app/modules/hello_world.py
from fastapi import APIRouter, Depends
from ..deps import require_module_role

MODULE_NAME = "hello-world"
MODULE_LABEL = "Hello world"
MODULE_ROLES = ["standard", "premium"]

router = APIRouter()

@router.get("/greeting")
def get_greeting(roles: list[str] = Depends(require_module_role(MODULE_NAME))):
    message = "Hello wonderful world" if "premium" in roles else "Hello world"
    return {"message": message, "roles": roles}
```

## 4. Contratto di un modulo — Frontend

Un modulo frontend è **una cartella** `frontend/src/modules/<module-name>/`
(nome cartella identico a `MODULE_NAME`, coi trattini). Deve contenere un
`index.js` che esporta di default un manifest:

```js
{ name: "<MODULE_NAME>", routes: [{ path, name, component }, ...] }
```

Il router (`frontend/src/router/index.js`) scopre automaticamente ogni
`src/modules/*/index.js` e monta ogni rotta sotto `/modules/<name>/<path>`,
**già protetta**: se l'utente loggato non ha alcun ruolo su quel modulo (e
non è admin) viene rediretto a una pagina 403 — il componente Vue del modulo
non deve reimplementare questo controllo. La voce di menu compare da sola
nella navbar e nella dashboard (pescano dallo store Pinia `stores/auth.js`):
**non serve toccare `NavBar.vue`, `Dashboard.vue` o `router/index.js`** per
aggiungere un modulo.

Per le chiamate API usare sempre l'istanza axios condivisa
`frontend/src/api/axios.js` (gestisce già token JWT e suo rinnovo
automatico — non va reimplementata).

Se un modulo ha ruoli diversi con UI/dati diversi, due pattern possibili:

- **Lato backend** (preferito quando i dati differiscono per contenuto, non
  solo per aspetto): l'endpoint del modulo decide cosa restituire in base ai
  ruoli ricevuti da `require_module_role` (è il pattern usato da
  `hello-world`).
- **Lato frontend** (solo per differenze puramente di UI, mai per proteggere
  dati sensibili — la vera protezione è sempre lato backend): leggere
  `auth.modules.find(m => m.name === "<MODULE_NAME>").granted_roles` dallo
  store Pinia.

Esempio minimo completo (`hello-world`):

```js
// frontend/src/modules/hello-world/index.js
import HelloWorld from './HelloWorld.vue'

export default {
  name: 'hello-world',
  routes: [{ path: '', name: 'home', component: HelloWorld }],
}
```

```vue
<!-- frontend/src/modules/hello-world/HelloWorld.vue -->
<template>
  <div>
    <h1 class="mb-3">Hello world</h1>
    <p v-if="!loading" class="fs-3">{{ message }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api/axios'

const message = ref('')
const loading = ref(true)

onMounted(async () => {
  const { data } = await api.get('/api/modules/hello-world/greeting')
  message.value = data.message
  loading.value = false
})
</script>
```

## 5. Convenzioni di stile da rispettare in ogni modulo nuovo

- Componenti Vue: sempre Composition API con `<script setup>`, mai Options API.
- Stile: solo classi Bootstrap 5 (niente CSS custom a meno di reale
  necessità); icone da `bootstrap-icons` (classe `bi bi-...`).
- Niente commenti superflui nel codice: solo se descrivono un vincolo o una
  motivazione non ovvia, mai per spiegare cosa fa il codice.
- Non aggiungere dipendenze npm/pip nuove a meno di reale necessità.
- Non toccare `main.py`, `router/index.js`, `NavBar.vue`, `stores/auth.js`
  per "registrare" un modulo: la scoperta è automatica by design.
- Non gestire mai da soli login/JWT/scadenza token/CORS: è già centralizzato.
- Non inventare un sistema di permessi separato: usare sempre
  `require_module_role` lato backend.

## 6. Checklist per creare un nuovo modulo "X"

1. Scegliere un `MODULE_NAME` univoco, in kebab-case (es. `fatture`,
   `crm-clienti`).
2. Creare `backend/app/modules/<nome_file>.py` con
   `MODULE_NAME`/`MODULE_LABEL`/`MODULE_ROLES`/`router`, endpoint protetti
   con `require_module_role`.
3. Creare `frontend/src/modules/<MODULE_NAME>/index.js` + i componenti
   `.vue` necessari.
4. Riavviare il backend (uvicorn) → il modulo compare nella tabella
   `modules` e i suoi endpoint sono attivi.
5. Da admin, in Amministrazione → Utenti/Gruppi, assegnare i ruoli del nuovo
   modulo a chi deve poterlo usare (il modulo di per sé non concede accesso
   a nessuno, nemmeno a chi lo crea).
6. Verificare che un utente senza permessi non veda la voce di menu e
   riceva 403 sia sulla rotta frontend `/modules/<name>` sia sulle API del
   modulo.

## 7. Riferimento

Il modulo `hello-world` (ruoli `standard`/`premium`) esiste già nel
repository come implementazione di riferimento completa e funzionante: puoi
copiarlo come punto di partenza.

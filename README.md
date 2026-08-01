# Blattaforma

Piattaforma modulare con autenticazione Google OAuth2, gestione utenti/gruppi
a permessi granulari e moduli funzionali installabili "a cartella".

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, SQLite, JWT (uvicorn)
- **Frontend**: Vue 3, Vite, Pinia, Vue Router, Bootstrap 5 (npm)

## Struttura del progetto

```
blattaforma/
├── backend/
│   ├── app/
│   │   ├── main.py            # app FastAPI, middleware, bootstrap DB
│   │   ├── config.py          # variabili d'ambiente (.env)
│   │   ├── models.py          # tabelle SQLAlchemy
│   │   ├── module_loader.py   # scopre e monta i moduli backend
│   │   ├── modules/           # <-- un file .py per ogni modulo
│   │   │   └── hello_world.py
│   │   └── routers/           # auth, users, groups, modules
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── modules/           # <-- una cartella per ogni modulo
    │   │   └── hello-world/
    │   ├── views/              views generiche + views/admin/
    │   ├── router/, stores/, api/, components/
    └── .env.example
```

## Avvio rapido

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # poi compila i valori (vedi sotto)
uvicorn app.main:app --reload --port 8000
```

Al primo avvio il database SQLite viene creato automaticamente e viene
inserito un account amministratore con l'email indicata in `ADMIN_EMAIL`
(default `admin@example.com`). Questo avviene **solo** se il DB è vuoto: nelle
esecuzioni successive la tabella utenti non viene più toccata, quindi puoi
modificarla liberamente a mano.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL deve puntare al backend
npm run dev
```

## Variabili d'ambiente (`backend/.env`)

| Variabile | Descrizione | Default |
|---|---|---|
| `ADMIN_EMAIL` | Email Google dell'amministratore creato al primo avvio | `admin@example.com` |
| `GOOGLE_CLIENT_ID` | Client ID OAuth2 di Google | _(vuoto)_ |
| `GOOGLE_CLIENT_SECRET` | Client Secret OAuth2 di Google | _(vuoto)_ |
| `SECRET_KEY` | Chiave per firmare i JWT (`openssl rand -hex 32`) | _placeholder, da cambiare_ |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durata/scadenza scorrevole del token | `30` |
| `BASE_URL` | URL pubblico del backend, usato per il redirect URI di Google | `http://localhost:8000` |
| `FRONTEND_URL` | URL pubblico del frontend, usato per i redirect dopo il login | `http://localhost:5173` |

Il frontend legge invece `VITE_API_BASE_URL` da `frontend/.env`.

### Configurazione Google OAuth2

1. Vai su [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. Crea un client OAuth2 di tipo "Web application".
3. Aggiungi come **Authorized redirect URI**: `{BASE_URL}/api/auth/google/callback`
   (es. `http://localhost:8000/api/auth/google/callback`).
4. Copia Client ID e Client Secret in `backend/.env`.

## Autenticazione e sessione

- Il login avviene solo tramite Google (nessuna password è mai salvata nel DB).
- Solo gli utenti già presenti nella tabella `users` (creati da un admin)
  possono accedere: un account Google non registrato riceve un errore e non
  viene creato automaticamente.
- Al login il backend rilascia un JWT con scadenza `ACCESS_TOKEN_EXPIRE_MINUTES`.
- **Ad ogni richiesta autenticata** il backend rilascia un nuovo token con
  scadenza rinnovata, restituito nell'header di risposta `X-New-Token`. Il
  frontend lo intercetta (`src/api/axios.js`) e lo salva automaticamente,
  così la sessione resta viva finché l'utente resta attivo.

## Modello dei permessi

- Ogni utente ha un flag `is_admin`: un amministratore ha sempre accesso
  completo a tutti i moduli, con tutti i ruoli.
- Un admin può creare/modificare/eliminare utenti, attivare o disattivare
  altri admin, ma **non può rimuovere i propri privilegi di admin né
  disattivare se stesso** (per evitare di restare fuori dalla piattaforma).
- Gli utenti possono essere raggruppati in **gruppi**; i permessi assegnati
  direttamente a un utente e quelli ereditati dai suoi gruppi **si sommano**
  (unione dei ruoli per modulo), non si sovrascrivono.
- Tutta la gestione di utenti, gruppi e permessi è riservata agli admin
  (menu "Amministrazione" nel frontend).

## Aggiungere un nuovo modulo

Un modulo è composto da due parti indipendenti, entrambe opzionali ma
tipicamente presenti insieme:

**1. Backend** — `backend/app/modules/<nome_file>.py`:

```python
from fastapi import APIRouter, Depends
from ..deps import require_module_role

MODULE_NAME = "il-mio-modulo"      # slug univoco: lettere, numeri, - e _
MODULE_LABEL = "Il mio modulo"     # nome mostrato nel menu
MODULE_ROLES = ["standard"]        # ruoli disponibili per questo modulo

router = APIRouter()

@router.get("/qualcosa")
def endpoint(roles: list[str] = Depends(require_module_role(MODULE_NAME))):
    ...
```

Al riavvio del backend il file viene scoperto automaticamente, il router
viene montato su `/api/modules/{MODULE_NAME}/...` e il modulo viene
registrato (o aggiornato) nella tabella `modules`.

**2. Frontend** — `frontend/src/modules/<nome-modulo>/`:

```
frontend/src/modules/il-mio-modulo/
├── IlMioModulo.vue
└── index.js
```

```js
// index.js
import IlMioModulo from './IlMioModulo.vue'

export default {
  name: 'il-mio-modulo',           // deve combaciare con MODULE_NAME
  routes: [{ path: '', name: 'home', component: IlMioModulo }],
}
```

Il router (`src/router/index.js`) scopre automaticamente ogni cartella con
un `index.js` e registra le rotte sotto `/modules/il-mio-modulo/...`,
proteggendole in base ai permessi effettivi dell'utente. La voce compare nel
menu solo se l'utente loggato (direttamente o tramite un gruppo) ha almeno un
ruolo assegnato su quel modulo.

## Modulo di esempio: hello-world

Incluso come riferimento. Due ruoli:

- `standard` → mostra "Hello world"
- `premium` → mostra "Hello wonderful world"

Un utente senza alcun ruolo su `hello-world` non vede la voce di menu e
riceve 403 se prova ad accedere direttamente a `/modules/hello-world` o
all'endpoint `/api/modules/hello-world/greeting`.

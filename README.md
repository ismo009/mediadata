# Studio Ops Dashboard

Dashboard local de production connecté à ShotGrid (Flow Production Tracking),
Ollama et, en option, Google Drive.

L'application fournit :

- une interface web organisée par projets ;
- des indicateurs de production et des cartes projet ;
- l'affichage détaillé des Shots, Tasks, Assets, Versions et Notes ;
- des liens directs vers les fiches ShotGrid ;
- une synchronisation manuelle vers une base SQLite locale ;
- un assistant IA Ollama capable d'interroger les données synchronisées ;
- un historique de conversation pour les questions de suivi ;
- une interface responsive pour ordinateur, tablette et mobile.

> **État actuel :** la synchronisation et l'interface sont en lecture seule.
> Le dashboard ne crée ni ne modifie encore de données ShotGrid.

## Architecture

```text
Navigateur
    |
    v
FastAPI + Uvicorn
    |              \
    v               v
ShotGrid API      Ollama
    |
    v
SQLite (dashboard.sqlite3)
```

- [`index.html`](./index.html) : interface du dashboard et assistant IA.
- [`backend/main.py`](./backend/main.py) : API FastAPI, synchronisation,
  recherche et connexion aux services.
- [`test_api_rest.py`](./test_api_rest.py) : test direct de connexion ShotGrid.
- [`requirements.txt`](./requirements.txt) : dépendances Python.
- [`.env.example`](./.env.example) : modèle de configuration.
- `dashboard.sqlite3` : cache local créé automatiquement.

## Pré-requis

- macOS, Linux ou Windows ;
- Python 3.9 ou supérieur ;
- un accès ShotGrid ;
- Ollama installé et lancé ;
- un modèle Ollama installé, par exemple `llama3.1`.

Vérifier Python et Ollama :

```bash
python3 --version
ollama list
```

## Installation

Depuis le dossier du projet :

```bash
cd /Users/lolot/html_server
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Ne versionne ou ne partage jamais `.env`. Il contient des identifiants
ShotGrid et peut contenir des jetons Google.

## Configuration

Édite `.env` :

```env
APP_SECRET=une-valeur-secrete-longue
APP_BASE_URL=http://localhost:8000

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:latest

SHOTGRID_SERVER_URL=https://votre-site.shotgrid.autodesk.com
SHOTGRID_LOGIN=login-legacy-shotgrid
SHOTGRID_PASSPHRASE=passphrase-legacy-shotgrid
SHOTGRID_PAT=pat-shotgrid
```

### Authentification ShotGrid

Le fonctionnement actuel utilise le login legacy et la passphrase :

- `SHOTGRID_LOGIN` : identifiant exact du compte ShotGrid ;
- `SHOTGRID_PASSPHRASE` : passphrase legacy ;
- `SHOTGRID_PAT` : PAT lié au site, conservé dans la configuration.

Le mode script est également pris en charge en secours :

```env
SHOTGRID_SCRIPT_NAME=nom-du-script
SHOTGRID_SCRIPT_KEY=cle-api-du-script
```

Ne mets jamais de vraies clés dans ce README.

### Google Drive

Google Drive est optionnel. Pour la bêta locale, un token peut être fourni :

```env
GOOGLE_ACCESS_TOKEN=token-google
```

La configuration OAuth complète utilise aussi :

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

## Lancement local

```bash
cd /Users/lolot/html_server
python3 -m uvicorn backend.main:app --reload --port 8000
```

Ouvre ensuite :

<http://localhost:8000>

Le serveur sert automatiquement `index.html`.

## Accès depuis une tablette ou un autre ordinateur

Le serveur doit écouter sur toutes les interfaces réseau :

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Trouver l'adresse IP du Mac :

```bash
ipconfig getifaddr en0
```

Puis ouvrir depuis le même réseau Wi-Fi :

```text
http://ADRESSE_IP_DU_MAC:8000
```

Pour Ollama, `localhost` ne convient pas sur la tablette : il désigne la
tablette elle-même. Lance Ollama sur le réseau local :

```bash
OLLAMA_HOST=0.0.0.0:11434 OLLAMA_ORIGINS="*" ollama serve
```

Dans les réglages du dashboard, utilise :

```text
http://ADRESSE_IP_DU_MAC:11434
```

Les appareils doivent être sur le même réseau et le pare-feu macOS doit
autoriser Python et Ollama.

## Synchroniser ShotGrid

1. Lance le serveur.
2. Ouvre le dashboard.
3. Clique sur **Synchroniser ShotGrid**.
4. Attends l'état `completed`.

La synchronisation s'exécute en arrière-plan et récupère les entités suivantes :

- `Project`
- `Shot`
- `Task`
- `Asset`
- `Version`
- `HumanUser`
- `Note`

Tous les champs disponibles dans le schéma ShotGrid sont stockés sous forme
JSON dans SQLite. La synchronisation est progressive et son état est visible
dans le dashboard.

La base locale est :

```text
dashboard.sqlite3
```

Pour repartir d'un cache vide, arrête le serveur puis supprime uniquement ce
fichier :

```bash
rm dashboard.sqlite3
```

Il sera recréé au prochain démarrage.

## API disponible

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health` | Vérifie que le backend répond |
| `GET` | `/api/dashboard` | Indicateurs et projets |
| `GET` | `/api/projects/{id}` | Détails et entités liées d'un projet |
| `POST` | `/api/sync` | Lance une synchronisation en arrière-plan |
| `GET` | `/api/sync/status` | État de la dernière synchronisation |
| `GET` | `/api/data/{entity}` | Données en cache d'une entité |
| `POST` | `/api/query` | Question à l'assistant IA |
| `GET` | `/auth/google/login` | Démarre Google OAuth |
| `GET` | `/auth/google/callback` | Retour OAuth Google |
| `POST` | `/auth/logout` | Ferme la session |
| `GET` | `/api/me` | Utilisateur connecté |

Exemple :

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/sync/status
curl 'http://localhost:8000/api/data/projects?limit=10'
```

Question à l'assistant :

```bash
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Quels sont les projets actifs ?","history":[]}'
```

## Tester ShotGrid directement

Le script de test charge `.env` automatiquement :

```bash
python3 test_api_rest.py
```

Il vérifie l'authentification puis affiche le nombre d'utilisateurs actifs et
les projets accessibles.

## Assistant IA

L'assistant :

- utilise le modèle défini par `OLLAMA_MODEL` ;
- reçoit les données ShotGrid trouvées dans le cache ;
- conserve les derniers messages de la conversation ;
- reconnaît les projets par nom et identifiant ;
- recherche les Tasks, Shots, Notes et autres entités liées ;
- fournit les liens `source_url` vers ShotGrid quand ils existent ;
- doit répondre uniquement avec les informations présentes dans les sources.

Si une réponse semble incorrecte :

1. vérifie que la synchronisation est terminée ;
2. synchronise à nouveau ShotGrid ;
3. recharge la page avec `Cmd + Shift + R` ;
4. pose une question contenant le nom exact du projet ou l'identifiant de
   l'entité.

## Sécurité

Cette version est prévue pour un réseau local de développement :

- ne publie pas le port `8000` sur Internet ;
- ne partage jamais `.env`, un PAT, une passphrase ou un token Google ;
- régénère tout secret exposé ;
- n'utilise pas `OLLAMA_ORIGINS="*"` sur un serveur public ;
- la gestion fine des permissions utilisateurs n'est pas encore activée ;
- les modifications ShotGrid depuis le dashboard ne sont pas encore activées.

## Dépannage

### `uvicorn: command not found`

Utilise le module Python :

```bash
python3 -m uvicorn backend.main:app --port 8000
```

### `Ollama est indisponible`

Vérifie le modèle et le service :

```bash
ollama list
curl http://localhost:11434/api/tags
```

### La tablette ne peut pas ouvrir le dashboard

Lance Uvicorn avec `--host 0.0.0.0`, vérifie l'IP du Mac, le même réseau Wi-Fi
et le pare-feu.

### La synchronisation semble lente

Une synchronisation complète peut récupérer plusieurs milliers
d'enregistrements. Elle s'exécute en arrière-plan ; consulte le statut dans le
dashboard ou :

```bash
curl http://localhost:8000/api/sync/status
```

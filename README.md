# MedIAData — Production Dashboard & Assistant IA

Dashboard local haute performance pour la supervision de studios d'animation et VFX, connecté en temps réel à **Autodesk ShotGrid** (Flow Production Tracking), **Ollama** (LLM local en streaming SSE) et, en option, **Google Drive**.

L'application associe un backend **FastAPI + SQLite (indexation relationnelle & recherche plein-texte FTS5)** à une interface réactive développée en **React (Vite)** suivant une direction artistique studio sombre et immersive.

---

## 🌟 Fonctionnalités Principales

### 🖥️ Interface
- **Direction « salle d'étalonnage »** : surfaces gris neutre, la couleur est réservée aux données (statuts, retards). Thème clair et sombre (suit le système, bascule manuelle). Typographie **Archivo** (largeur variable).
- **Vue d'ensemble** : une « bande de production » par projet (avancement des tâches par statut), triée par retard, activité ou nom, et le fil des dernières notes.
- **Espace production** : synthèse par étape et par séquence, tâches en retard et bloquées, équipe, puis onglets *Tâches* (filtres étape / personne / statut / retard / bloquées, recherche plein texte, pagination), *Plans* (vignettes fraîches depuis ShotGrid), *Assets*, *Notes*, *Versions*.
- **Équipe** : charge ouverte, review et retards par personne ; fiche individuelle avec toutes ses tâches.
- **Synchronisation** : historique, types de données synchronisés et comparaison en direct avec ShotGrid.
- **Recherche globale** (`Ctrl K`) sur toutes les entités. Lia est un panneau latéral contextuel (connaît la production ouverte). Responsive jusqu'au mobile.

### 🤖 Assistante Lia (RAG)
- **Périmètre structuré** : la question est analysée (production, séquence, étape — y compris par nom court comme « comp » —, personne, type d'entité, groupe de statut, retard, tâches bloquées par une tâche amont).
- **Statistiques exactes** : totaux et répartitions (par statut, étape, personne, nombre en retard) calculés en SQL sur toute la base, même quand seule une partie des enregistrements est envoyée au modèle.
- **Statuts du site** : les codes propres à ShotGrid (`intapp`, `av`, `valide`, `rtk`…) sont regroupés en *Terminé / En review / En cours / En attente* et leurs noms lisibles sont fournis au modèle.
- Recherche plein texte FTS5 en dernier recours, streaming SSE, sources cliquables.

---

## 🏗️ Architecture Technique

```text
   Navigateur (React 18 + Vite)  ──REST / SSE──▶  FastAPI (Uvicorn)
                                                   ├── ShotGrid (shotgun_api3)
                                                   ├── Ollama (LLM local)
                                                   └── Google Drive (optionnel)
                                                          │
                          SQLite : enregistrements + liens entre entités + index FTS5
```

### Arborescence du Projet

```text
html_server/
├── requirements.txt / requirements-dev.txt
├── .env.example
├── dashboard.sqlite3          # copie locale de ShotGrid (non versionnée)
├── backend/
│   ├── main.py                # assemblage de l'app FastAPI, planificateur
│   ├── config.py              # variables d'environnement
│   ├── db.py                  # schéma SQLite versionné et migrations
│   ├── records.py             # noms, statuts, projets actifs, retards
│   ├── shotgrid.py            # client ShotGrid
│   ├── sync.py                # synchro complète / incrémentale, audit
│   ├── retrieval.py           # question → périmètre, enregistrements, stats
│   ├── assistant.py           # endpoint de l'assistante (streaming)
│   ├── prompt.py              # prompt système de Lia
│   ├── auth.py                # Google OAuth (jetons stockés côté serveur)
│   ├── api.py                 # API de lecture pour l'interface
│   └── migrate_db.py          # migration / reconstruction manuelle
├── tests/                     # pytest (faux client ShotGrid)
└── frontend/src/
    ├── App.jsx                # coquille, routage, thème, synchro
    ├── api.js / lib.js        # client HTTP, routeur, formatage
    ├── index.css              # système visuel
    ├── pages/                 # Overview, ProjectPage, PeoplePage, PersonPage, SyncPage
    └── components/            # ui, TaskTable, SearchPalette, Assistant
```

---

## 📋 Prérequis

- **macOS**, **Linux** ou **Windows**
- **Python 3.9+**
- **Node.js 18+** & **npm**
- **Ollama** lancé localement avec au moins un modèle installé (ex: `llama3.1`, `mistral`)
- Un compte ou accès script sur un site **Autodesk ShotGrid**

Vérifiez vos versions :
```bash
python3 --version
node -v
npm -v
ollama list
```

---

## ⚙️ Installation & Configuration

### 1. Installation des dépendances Python

```bash
cd /Users/lolot/html_server
python3 -m pip install -r requirements.txt
```

### 2. Installation et compilation du Frontend React

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Configuration des variables d'environnement (`.env`)

Copiez le fichier d'exemple :
```bash
cp .env.example .env
```

Éditez `.env` avec vos identifiants :
```env
APP_SECRET=votre-cle-secrete-aleatoire-et-longue
APP_BASE_URL=http://localhost:8000

# Configuration Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:latest

# Autodesk ShotGrid (Authentification utilisateur ou script)
SHOTGRID_SERVER_URL=https://votre-site.shotgrid.autodesk.com
SHOTGRID_LOGIN=votre_identifiant
SHOTGRID_PASSPHRASE=votre_passphrase
SHOTGRID_PAT=votre_personal_access_token

# Ou via Script Key :
# SHOTGRID_SCRIPT_NAME=mon_script
# SHOTGRID_SCRIPT_KEY=ma_cle_api

# Google Drive (Optionnel)
# GOOGLE_ACCESS_TOKEN=token_optionnel
```

> 🔒 **Sécurité** : Le fichier `.env` et la base `dashboard.sqlite3` sont exclus de Git. Ne partagez jamais vos clés API ou tokens.

---

## 🚀 Lancement de l'Application

### Mode Standard / Production (Recommandé)
FastAPI sert directement l'interface React compilée :

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

Ouvrez votre navigateur sur :
👉 **`http://localhost:8000`**

### Mode Développement Frontend (Hot-Reload)
Pour travailler sur les composants React avec rechargement instantané :

1. **Terminal 1 (Backend FastAPI)** :
   ```bash
   python3 -m uvicorn backend.main:app --reload --port 8000
   ```
2. **Terminal 2 (Serveur Vite)** :
   ```bash
   cd frontend
   npm run dev
   ```
   👉 Ouvrez **`http://localhost:5173`** *(les requêtes `/api` et `/auth` sont automatiquement redirigées vers FastAPI)*.

---

## 🔄 Synchronisation ShotGrid & Base SQLite

- **Automatique** : au démarrage puis toutes les `SYNC_INTERVAL_MINUTES` (30 par défaut), une synchronisation *incrémentale* récupère les enregistrements modifiés (`updated_at`) et applique les suppressions lues dans le journal d'événements ShotGrid. Une synchronisation *complète* a lieu si la dernière date de plus de `FULL_SYNC_EVERY_HOURS` (24 par défaut).
- **Manuelle** : bouton de synchronisation en haut de l'écran, ou page *Synchronisation* (incrémentale, complète, comparaison avec ShotGrid).
- **Types synchronisés** : avec `SYNC_ENTITIES=auto`, tous les types ShotGrid non système qui contiennent des données (tâches, plans, séquences, étapes, notes, réponses, versions, playlists, temps saisis, fichiers, entités personnalisées…). Ou une liste explicite : `SYNC_ENTITIES=Project,Shot,Task`.
- Chaque lien entre entités (tâche → étape, plan → séquence, tâche → tâches amont…) est indexé dans `shotgrid_links`.

Le schéma se met à jour tout seul. Pour reconstruire à la main l'index plein texte et les liens :
```bash
python -m backend.migrate_db --rebuild
```

---

## 🧪 Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

---

## 🔌 Référence de l'API REST

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Projets avec avancement, retards, activité ; totaux ; dernières notes |
| `GET` | `/api/projects/{id}` | Synthèse d'une production (étapes, séquences, retards, blocages, équipe) |
| `GET` | `/api/records/{EntityType}` | Liste filtrée : `project_id`, `sequence_id`, `step_id`, `person_id`, `bucket`, `late`, `blocked`, `search`, `sort`, `page`, `limit` |
| `GET` | `/api/people`, `/api/people/{id}` | Charge par personne, tâches d'une personne |
| `GET` | `/api/search?q=` | Recherche plein texte globale |
| `GET` | `/api/thumbnails?entity_type=&ids=` | URLs de vignettes fraîches (les URLs ShotGrid expirent) |
| `GET` | `/api/statuses`, `/api/entity-types` | Noms des statuts, types synchronisés |
| `POST` | `/api/sync?mode=auto\|full\|incremental` | Lance une synchronisation |
| `GET` | `/api/sync/status`, `/api/sync/runs` | Dernière synchro, historique |
| `GET` | `/api/sync/audit?include_unsynced=true` | Comparaison en direct ShotGrid ↔ copie locale |
| `GET` | `/api/models` | Modèles Ollama disponibles |
| `POST` | `/api/query/stream` | Assistante Lia en streaming SSE |
| `GET` | `/auth/google/login`, `/auth/google/callback`; `POST /auth/logout`; `GET /api/me` | Google OAuth |

---

## 🛠️ Dépannage Fréquent

### `uvicorn: command not found`
Utilisez la commande via le module Python :
```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```
*(Pour créer un raccourci direct, ajoutez `export PATH="$HOME/Library/Python/3.9/bin:$PATH"` dans votre `~/.zshrc`)*.

### `Ollama est indisponible`
Vérifiez qu'Ollama est bien lancé sur votre machine :
```bash
curl http://localhost:11434/api/tags
```

### L'interface ne prend pas en compte les dernières modifications
Recompilez les assets React :
```bash
cd frontend && npm run build
```
Puis faites un rafraîchissement complet dans le navigateur avec `Cmd + Shift + R`.

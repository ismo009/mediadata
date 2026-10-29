# Studio Ops — Production Dashboard & Assistant IA

Dashboard local moderne de supervision de studio VFX / Animation connecté à **Autodesk ShotGrid** (Flow Production Tracking), **Ollama** (LLM local) et, en option, **Google Drive**.

L'application associe un backend haute performance sous **FastAPI** et **SQLite (FTS5)** à une interface réactive développée en **React (Vite)**.

---

## 🌟 Fonctionnalités

- **Interface React moderne** : navigation fluide par projet, shots, tâches, notes, versions et assets.
- **Cartes KPI & Supervision** : suivi instantané des projets actifs, volumes de tâches et dernière synchronisation.
- **Explorateur Master-Detail** : consultation d'un projet avec onglets dédiés (*Tâches*, *Shots*, *Notes*, *Versions*, *Assets*) et liens directs vers ShotGrid.
- **Grille de données paginée (DataGrid)** : recherche instantanée, filtres par statut et pagination serveur pour naviguer confortablement dans plus de 16 000 enregistrements.
- **Assistant IA en Streaming temps réel (SSE)** : réponses mot-par-mot propulsées par Ollama, rendu Markdown complet, accordéon des sources consultées et sélecteur de modèle.
- **Moteur de recherche Full-Text (SQLite FTS5)** : indexation ultra-rapide des notes, descriptions et noms.
- **Synchronisation ShotGrid en arrière-plan** : cache local structuré et indexé, sans bloquer l'interface.

---

## 🏗️ Architecture

```text
       Navigateur Web (React + Vite)
                     │
       (HTTP REST & Server-Sent Events)
                     │
                     ▼
          Backend FastAPI (Uvicorn)
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   Autodesk       Ollama    Google Drive
   ShotGrid     (LLM Local)  (Optionnel)
         │
         ▼
  SQLite 3 (B-Tree + FTS5 Full-Text)
```

### Arborescence du projet

```text
html_server/
├── README.md               # Documentation du projet
├── requirements.txt        # Dépendances Python (FastAPI, ShotGrid, etc.)
├── .env.example            # Modèle des variables d'environnement
├── .gitignore              # Protection des secrets et fichiers générés
├── test_api_rest.py        # Script de test de connexion ShotGrid
├── dashboard.sqlite3       # Base SQLite locale (indexée + FTS5)
│
├── backend/
│   ├── __init__.py
│   ├── main.py             # API FastAPI, streaming SSE, cache & RAG
│   └── migrate_db.py       # Script d'indexation et migration FTS5
│
└── frontend/               # Application React moderne
    ├── package.json        # Dépendances NPM (React, Lucide, React-Markdown)
    ├── vite.config.js      # Configuration Vite avec proxy backend
    ├── index.html          # Point d'entrée HTML
    ├── dist/               # Build de production (servi par FastAPI)
    └── src/
        ├── App.jsx         # Composant racine et gestion d'état
        ├── api.js          # Client HTTP et streaming SSE
        ├── index.css       # Design System sombre pour studio
        └── components/
            ├── Sidebar.jsx           # Barre latérale & statut sync
            ├── DashboardOverview.jsx # KPIs & grille de projets
            ├── ProjectDetail.jsx     # Vue détaillée par projet (onglets)
            ├── EntityTable.jsx       # Tableau paginé avec filtres
            └── ChatAssistant.jsx     # Assistant IA conversationnel en streaming
```

---

## 📋 Prérequis

- **macOS**, **Linux** ou **Windows**
- **Python 3.9+**
- **Node.js 18+** & **npm** (installé sur le Mac : v26.11 / npm 11)
- **Ollama** lancé localement avec au moins un modèle (ex: `llama3.1`, `mistral`, etc.)
- Un accès à un site **Autodesk ShotGrid**

Vérifiez vos installations :
```bash
python3 --version
node -v
npm -v
ollama list
```

---

## ⚙️ Installation & Configuration

### 1. Dépendances Python

```bash
cd /Users/lolot/html_server
python3 -m pip install -r requirements.txt
```

### 2. Dépendances Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Fichier d'environnement (`.env`)

Copiez le modèle et renseignez vos identifiants :
```bash
cp .env.example .env
```

Modifiez `.env` avec vos accès :
```env
APP_SECRET=votre-cle-secrete-longue
APP_BASE_URL=http://localhost:8000

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:latest

# Autodesk ShotGrid
SHOTGRID_SERVER_URL=https://votre-site.shotgrid.autodesk.com
SHOTGRID_LOGIN=votre_login
SHOTGRID_PASSPHRASE=votre_passphrase
SHOTGRID_PAT=votre_pat

# Ou authentification par Script (alternative) :
# SHOTGRID_SCRIPT_NAME=mon_script
# SHOTGRID_SCRIPT_KEY=ma_cle_api

# Google Drive (Optionnel)
# GOOGLE_ACCESS_TOKEN=token-drive-si-disponible
```

> ⚠️ **Sécurité** : Le fichier `.env` et la base `dashboard.sqlite3` sont exclus de Git via `.gitignore`. Ne committez jamais vos secrets.

---

## 🚀 Démarrage

### Option A : Mode Standard / Production (Recommandé)

FastAPI sert directement l'interface React compilée :

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

Ouvrez ensuite dans votre navigateur :
👉 **`http://localhost:8000`**

### Option B : Mode Développement Frontend (Hot-Reload)

Pour modifier les composants React avec rechargement instantané :

1. **Terminal 1 (Backend FastAPI)** :
   ```bash
   python3 -m uvicorn backend.main:app --reload --port 8000
   ```

2. **Terminal 2 (Serveur Vite)** :
   ```bash
   cd frontend
   npm run dev
   ```
   👉 Ouvrez **`http://localhost:5173`** *(tous les appels `/api` et `/auth` sont automatiquement redirigés vers FastAPI sur le port 8000)*.

---

## 🔄 Synchronisation ShotGrid

1. Lancez le serveur et ouvrez l'interface.
2. Dans le panneau latéral gauche en bas, cliquez sur l'icône de rafraîchissement à côté de **ShotGrid Sync**.
3. La synchronisation s'exécute en tâche de fond (`completed` dès que terminée).

Entités synchronisées :
- `Project`
- `Shot`
- `Task`
- `Asset`
- `Version`
- `HumanUser`
- `Note`

Pour forcer une réindexation SQLite et FTS5 manuelle :
```bash
python3 backend/migrate_db.py
```

---

## 🤖 Assistant IA & RAG

L'assistant intelligent situé dans le volet droit :
- Analyse votre question et extrait les entités pertinentes via la recherche **SQLite FTS5** et la base relationnelle.
- Épure le JSON transmis au LLM pour éviter d'engorger la fenêtre de tokens.
- Streame la réponse en direct via Server-Sent Events (**SSE**).
- Affiche un accordéon des **sources consultées** avec liens cliquables vers ShotGrid.
- Permet de changer de modèle Ollama à la volée depuis le menu déroulant.

---

## 🔌 Référence de l'API REST

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health` | Vérifie l'état de l'API (`{"status": "ok"}`) |
| `GET` | `/api/models` | Liste les modèles Ollama installés localement |
| `GET` | `/api/dashboard` | Métriques globales et liste des projets |
| `GET` | `/api/projects/{id}` | Détail complet d'un projet et ses entités liées |
| `GET` | `/api/data/{entity}` | Données paginées (`?page=1&limit=50&search=...&status=...`) |
| `POST` | `/api/sync` | Lance une synchronisation ShotGrid en arrière-plan |
| `GET` | `/api/sync/status` | Statut de la dernière synchronisation |
| `POST` | `/api/query/stream` | Requête assistant IA en **streaming SSE** |
| `POST` | `/api/query` | Requête assistant IA standard (compatibilité JSON) |
| `GET` | `/auth/google/login` | Initialisation de la connexion Google OAuth |
| `GET` | `/auth/google/callback` | Callback de redirection Google |
| `POST` | `/auth/logout` | Déconnexion |
| `GET` | `/api/me` | Informations de session utilisateur |

---

## 🛠️ Dépannage rapide

### `zsh: command not found: uvicorn`
Utilisez la syntaxe module Python :
```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```
*(Ou ajoutez `export PATH="$HOME/Library/Python/3.9/bin:$PATH"` dans votre `~/.zshrc`)*.

### `Ollama est indisponible`
Vérifiez qu'Ollama est bien démarré :
```bash
curl http://localhost:11434/api/tags
```

### Le frontend React ne reflète pas les dernières modifications
Recompilez les assets :
```bash
cd frontend && npm run build
```
Puis faites un rafraîchissement complet dans le navigateur avec `Cmd + Shift + R`.

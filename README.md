# MedIAData — Production Dashboard & Assistant IA

Dashboard local haute performance pour la supervision de studios d'animation et VFX, connecté en temps réel à **Autodesk ShotGrid** (Flow Production Tracking), **Ollama** (LLM local en streaming SSE) et, en option, **Google Drive**.

L'application associe un backend **FastAPI + SQLite (indexation relationnelle & recherche plein-texte FTS5)** à une interface réactive développée en **React (Vite)** suivant une direction artistique studio sombre et immersive.

---

## 🌟 Fonctionnalités Principales

### 🖥️ Interface & Ergonomie (DA Studio Obsidian)
- **Palette Studio Sombre** : Design inspiré des standards studio (*Autodesk Flow*, *Linear*, *Raycast*) avec typographie premium **Plus Jakarta Sans** et **JetBrains Mono**.
- **Vue d'ensemble & KPIs en direct** : Suivi des projets actifs, volumes de tâches, plans (shots) et notes synchronisées.
- **Catalogue de Projets filtrable** : Recherche instantanée, filtrage par statut (*Tous*, *Actifs*), avatars de projet dynamiques et liens directs ShotGrid.
- **Espace Projet (Master-Detail)** : Navigation par projet avec onglets dédiés (*Tâches*, *Shots*, *Notes*, *Versions*, *Assets*), compteurs numériques intégrés et fil d'Ariane intuitif.
- **Grille de Données Paginée (DataGrid)** : Recherche plein-texte, filtres par statut de production et pagination serveur pour explorer sans latence plus de **16 500 enregistrements**.

### 🤖 Assistant IA & Moteur RAG v2
- **Streaming mot-par-mot (SSE)** : Réponses en direct propulsées par Ollama sans aucun temps mort.
- **Capacité étendue à 75–80 sources** : Contexte riche et précis avec compactage intelligent des données pour respecter la fenêtre de tokens.
- **Routage sémantique d'intention** :
  - *Questions générales sur les projets* (ex: « Quels sont les projets actifs ? ») : injection de **100 % des projets de la base** (55 projets) pour une exhaustivité totale sans notes parasites.
  - *Questions ciblées sur un projet* (ex: « Tâches de Devant les Projecteurs ») : récupération de la fiche projet et des tâches, shots ou notes rattachés spécifiquement à ce projet.
  - *Recherche plein-texte FTS5* : filtrage automatique des mots vides (*stop-words*) pour cibler les mots-clés techniques (*texturing*, *caméra*, *roto*, etc.).
- **Master Prompt Superviseur VFX** :
  - Décodage rigoureux des statuts ShotGrid : `wtg` (En attente), `ip` (En cours), `rev` (En review), `fin` (Terminé), `apr` (Approuvé).
  - Distinction nette entre statut projet (`Actif`, `Archivé`, `Template`) et statuts de tâches.
  - Règle anti-hallucination stricte (interdiction d'inventer des ID ou des noms).
  - Liens Markdown contextuels : `[Devant les Projecteurs (ID 223)](url)` au lieu de liens génériques répétitifs.
- **Tiroir des Sources Interactif** : Accordéon détaillé avec répartition par type d'entités (ex. *55 Projets* ou *52 Tâches, 13 Shots*) et liens directs ShotGrid.

---

## 🏗️ Architecture Technique

```text
       Navigateur Web (React 18 + Vite)
                     │
       (HTTP REST & Server-Sent Events / SSE)
                     │
                     ▼
          Backend FastAPI (Uvicorn)
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   Autodesk       Ollama    Google Drive
   ShotGrid     (LLM Local)  (Optionnel)
         │
         ▼
  SQLite 3 (B-Tree + FTS5 Full-Text Search)
```

### Arborescence du Projet

```text
html_server/
├── README.md               # Documentation complète du projet
├── requirements.txt        # Dépendances Python (FastAPI, ShotGrid API, etc.)
├── .env.example            # Modèle des variables d'environnement
├── .gitignore              # Protection des secrets (.env) et bases locales
├── test_api_rest.py        # Script de test de connexion directe ShotGrid
├── dashboard.sqlite3       # Base SQLite locale indexée (16 500+ records)
│
├── backend/
│   ├── __init__.py
│   ├── main.py             # API FastAPI, moteur RAG, streaming SSE & cache
│   └── migrate_db.py       # Script d'indexation SQLite et création table FTS5
│
└── frontend/               # Application React moderne (Vite)
    ├── package.json        # Dépendances NPM (React, Lucide, React-Markdown)
    ├── vite.config.js      # Configuration Vite avec proxy backend
    ├── index.html          # Point d'entrée HTML
    ├── dist/               # Build de production (servi directement par FastAPI)
    └── src/
        ├── App.jsx         # Composant racine et gestion d'état globale
        ├── api.js          # Client HTTP fetch et streaming SSE
        ├── index.css       # Design System studio (Obsidian & Electric Indigo)
        └── components/
            ├── Sidebar.jsx           # Barre latérale & statut de synchronisation
            ├── DashboardOverview.jsx # Métriques KPIs & grille des projets
            ├── ProjectDetail.jsx     # Vue détaillée par projet avec onglets
            ├── EntityTable.jsx       # Tableau paginé serveur avec filtres
            └── ChatAssistant.jsx     # Assistant conversationnel streaming & sources
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

1. Lancez l'application et ouvrez l'interface web.
2. Dans la barre latérale gauche (en bas), cliquez sur le bouton de rafraîchissement à côté de **ShotGrid Cache**.
3. La synchronisation s'exécute en tâche de fond (`completed` une fois terminée) et met à jour les entités :
   - `Project`
   - `Shot`
   - `Task`
   - `Asset`
   - `Version`
   - `HumanUser`
   - `Note`

Pour forcer manuellement la réindexation SQLite et la reconstruction de la table plein-texte FTS5 :
```bash
python3 backend/migrate_db.py
```

---

## 🔌 Référence de l'API REST

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health` | Vérification de l'état de santé de l'API |
| `GET` | `/api/models` | Liste des modèles Ollama détectés localement |
| `GET` | `/api/dashboard` | Métriques globales (KPIs) et liste des projets |
| `GET` | `/api/projects/{id}` | Détail complet d'un projet et entités rattachées |
| `GET` | `/api/data/{entity}` | Données paginées (`?page=1&limit=50&search=...&status=...`) |
| `POST` | `/api/sync` | Déclenche une synchronisation ShotGrid en tâche de fond |
| `GET` | `/api/sync/status` | Statut et historique de la dernière synchronisation |
| `POST` | `/api/query/stream` | Assistant IA en **streaming temps réel SSE** (RAG v2) |
| `POST` | `/api/query` | Assistant IA standard (réponse JSON non-streamée) |
| `GET` | `/auth/google/login` | Initialisation de l'authentification Google OAuth |
| `GET` | `/auth/google/callback` | Callback de retour Google OAuth |
| `POST` | `/auth/logout` | Déconnexion de la session utilisateur |
| `GET` | `/api/me` | Informations de la session courante |

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

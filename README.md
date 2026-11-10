# MedIAData

Tableau de bord local pour suivre des productions d'animation, de VFX et de tournage à partir d'**Autodesk ShotGrid** (Flow Production Tracking), avec **Lia**, une assistante qui répond aux questions en langage naturel grâce à un modèle **Ollama** exécuté sur la machine.

L'application garde une copie locale de ShotGrid dans SQLite, synchronisée automatiquement. L'interface et l'assistante lisent cette copie : tout est rapide, et rien n'est jamais modifié dans ShotGrid. Chaque personne se connecte avec son compte Autodesk et ne voit que les productions auxquelles elle a droit.

---

## Sommaire

1. [Ce que fait l'application](#ce-que-fait-lapplication)
2. [Lia, l'assistante](#lia-lassistante)
3. [Connexion et droits](#connexion-et-droits)
4. [Architecture](#architecture)
5. [Installation](#installation)
6. [Lancement](#lancement)
7. [Synchronisation avec ShotGrid](#synchronisation-avec-shotgrid)
8. [Tests et évaluation](#tests-et-évaluation)
9. [Référence de l'API](#référence-de-lapi)
10. [Dépannage](#dépannage)

---

## Ce que fait l'application

L'interface montre peu de choses à la fois : l'accueil liste les productions, et tout le détail apparaît quand on clique sur l'une d'elles.

| Page | Contenu |
|---|---|
| **Connexion** | Bouton « Se connecter avec Autodesk ». Voir [Connexion et droits](#connexion-et-droits). |
| **Productions** (accueil) | Une carte par production visible : nom, dernière activité, pourcentage de tâches terminées et nombre de tâches en retard. Recherche, tri (activité récente, les plus en retard, nom) et filtre « Mes productions / En cours / Toutes ». |
| **Mes tâches** | Les tâches assignées à la personne connectée, toutes productions confondues (non terminées par défaut). |
| **Production** | Quatre chiffres clés (% terminé, tâches, en retard, plans), puis des onglets. *Vue d'ensemble* : les 5 tâches à surveiller (en retard ou bloquées) et l'avancement par étape. *Tâches* : tableau filtrable par étape, personne et état (non terminées par défaut, en retard, bloquées…), avec recherche et tri. *Plans* (vignettes, filtre par séquence), *Équipe*, *Notes*, *Versions*, *Assets*. |
| **Équipe** | Charge ouverte, tâches en review et en retard par personne, et fiche individuelle avec toutes ses tâches. |
| **Synchronisation** (administrateurs) | Historique des synchronisations, types de données synchronisés, bouton « Comparer avec ShotGrid » qui vérifie en direct que la copie locale est complète. |

Dans la barre du haut :
- **Recherche globale** (icône loupe ou `Ctrl K`) sur les productions, plans, tâches, notes et personnes visibles.
- **Synchronisation** : l'icône indique l'état de la dernière synchronisation ; un administrateur peut en lancer une au clic.
- **Thème** clair ou sombre (suit le système par défaut).
- **Demander à Lia** ouvre l'assistante dans un panneau latéral ; elle sait qui lui parle et quelle production est affichée.
- **Compte** (initiales) : nom, groupe ShotGrid, périmètre visible et déconnexion.

L'interface est utilisable sur mobile. Direction visuelle : surfaces gris neutre, comme une salle d'étalonnage, la couleur étant réservée aux données (avancement, statuts, retards) ; police Archivo.

---

## Lia, l'assistante

### Exemples de questions

- « Où en est Les Cocottes en Papier ? »
- « Quelles tâches sont en retard sur Devant les Projecteurs ? »
- « Quelle production a le plus de tâches en retard ? »
- « Qui a le plus de tâches ouvertes ? »
- « Combien de tâches de compositing sont en cours ? »
- « Sur quoi travaille Maxime Pierre ? »
- « Résume les dernières notes de Un homme de tête »
- puis, en suite de conversation : « et combien sont en retard ? »

Les fautes de frappe et les noms partiels sont tolérés : « des cocottes en pappier » est reconnu comme *Les Cocottes en Papier*, « stranger thing » comme *Stranger Things - PXFK*.

### Comment une question est traitée

```text
Question
  │
  ├─ 1. Analyse (backend/retrieval.py)
  │     production, séquence, personne (tolérance aux fautes), étape (« comp » = Compositing),
  │     type d'élément, état (en attente / en cours / en review / terminé / non terminé),
  │     retard, blocage, question de comptage ou de classement
  │
  ├─ 2. Requêtes SQL sur la copie locale
  │     → chiffres exacts sur toute la base (total, par état, par étape, par personne, par production)
  │     → un échantillon d'éléments pertinents (aucun pour un classement)
  │
  ├─ 3. Mise en forme (backend/context.py)
  │     texte français étiqueté : date du jour, statuts traduits, « EN RETARD de 15 jours »,
  │     chiffres exacts en premier, liste signalée comme PARTIELLE si elle est incomplète
  │
  └─ 4. Ollama (backend/prompt.py)
        prompt court à règles hiérarchisées, température 0,2, réponse en streaming
```

Points importants :
- **Les chiffres viennent de SQL, pas du modèle.** Même si seuls quelques éléments sont envoyés, les totaux et les classements sont calculés sur toute la base.
- **Lia n'invente pas.** Si l'information n'est pas dans les données, elle répond « Je ne trouve pas cette information dans les données ShotGrid. »
- **Questions de suite.** Une question courte qui ne nomme ni production, ni séquence, ni personne reprend le sujet de la question précédente (et seulement le sujet, pas les filtres).
- **Sources.** Sous chaque réponse, l'interface liste les éléments consultés avec leur lien vers ShotGrid.

### Statuts

Les codes de statut ShotGrid, y compris ceux propres au site, sont regroupés en quatre états affichés partout dans l'interface et donnés à Lia :

| État | Codes |
|---|---|
| Terminé | `fin`, `apr`, `cmpt`, `clsd`, `na`, `omt`, `dlvr`, `vwd`, `res`, `cfrm`, `recd`, `valide`, `cliapp`, `intapp` |
| En review | `rev`, `av` (A valider), `rsb`, `pub` |
| En cours | `ip`, `act`, `wip`, `ren`, `rtk` (retake), `tr` (Tout roule) |
| En attente | `wtg`, `rdy`, `rdysta`, `hld`, `opn`, `pndng`, statut vide |

Une tâche est **en retard** si son échéance est dépassée et qu'elle n'est pas terminée. Elle est **bloquée** si l'une de ses tâches amont n'est pas terminée.

Une production est **active** si elle n'est ni archivée, ni un template, et que son statut n'est pas *Done*, *Lost* ou *Bidding*. Le même calcul sert au tableau de bord et à Lia.

---

## Connexion et droits

Chaque personne se connecte avec **son compte Autodesk**, le même que pour ShotGrid. L'application ne voit jamais son mot de passe : la connexion se fait sur la page d'Autodesk (avec sa double authentification), puis l'adresse e-mail du compte est rapprochée de l'utilisateur ShotGrid correspondant.

### Ce que voit chaque personne

| Groupe de droits ShotGrid (`permission_rule_set`) | Productions visibles |
|---|---|
| Groupes listés dans `ROLES_SEE_ALL` (par défaut Admin, Admin Copy, Manager, Supervisor, Audit - Conseil) | Toutes |
| Tous les autres (Artist, Vendor…) | Seulement celles dont la personne est membre dans ShotGrid (champ *Users* de la production) |

Ce filtre s'applique partout : accueil, pages de production, tâches, équipe, recherche, vignettes **et Lia**. Techniquement, chaque requête d'un utilisateur passe par une connexion SQLite où la table des enregistrements est remplacée par une vue qui ne contient que ses productions. Les éléments d'une autre production n'existent donc pas pour lui, même dans les totaux ou les classements, et Lia ne peut pas en parler puisqu'elle ne les reçoit jamais.

Autres règles :
- Seuls les groupes listés dans `ADMIN_ROLES` (par défaut Admin, Admin Copy) voient la page *Synchronisation* et peuvent lancer une synchronisation.
- Un compte désactivé dans ShotGrid ne peut pas se connecter. Si plusieurs comptes ShotGrid actifs partagent la même adresse e-mail, la connexion est refusée tant qu'un administrateur n'a pas corrigé le doublon (sauf si l'un d'eux a cette adresse comme login).
- Les droits sont relus à chaque requête depuis la copie locale : un changement de groupe ou d'équipe dans ShotGrid est pris en compte à la synchronisation suivante.
- Lia comprend « mes tâches », « mes productions », « qu'est-ce que je dois rendre ? » : elle sait qui lui parle. La page *Mes tâches* liste les tâches assignées à la personne connectée.

Limite actuelle : la règle ci-dessus approche les droits ShotGrid à partir du groupe et de l'appartenance aux productions. Les règles fines d'un groupe personnalisé (masquer certains champs, filtrer certaines entités) ne sont pas reproduites. Pour une correspondance exacte, il faudra interroger ShotGrid au nom de chaque utilisateur avec une clé de script autorisée à le faire (*sudo*).

### Configurer la connexion Autodesk

Le guide pas à pas, du compte développeur Autodesk à la mise en ligne en HTTPS, est dans [docs/connexion-autodesk.md](docs/connexion-autodesk.md). En résumé :

1. Sur [aps.autodesk.com](https://aps.autodesk.com), préparez un plan APS (le niveau **Free** suffit) et un **developer hub** : Autodesk les exige avant toute création d'application.
2. Dans **My applications**, créez une application de type **Traditional Web App**.
3. Dans **Callback URL**, déclarez exactement `<APP_BASE_URL>/auth/autodesk/callback` : `http://localhost:8000/auth/autodesk/callback` pour tester sur son poste, puis `https://<domaine>/auth/autodesk/callback` pour le serveur de l'équipe (plusieurs URL sont acceptées). L'URL proposée par défaut, `http://localhost:8080/`, ne convient pas.
4. Collez l'identifiant et le secret **directement dans `.env`** (`APS_CLIENT_ID`, `APS_CLIENT_SECRET`), définissez `APP_SECRET`, puis redémarrez le serveur : il ne relit `.env` qu'au démarrage.
5. Vérifiez :
   ```bash
   python scripts/check_login_setup.py
   ```
   Le script ne modifie rien. Il contrôle `.env`, demande à Autodesk si l'URL de rappel est bien déclarée (et affiche celle qui l'est sinon), et liste les comptes ShotGrid qui ne pourront pas se connecter (sans e-mail valide, ou adresse partagée par plusieurs comptes actifs) ainsi que ce que verra chaque groupe.

Le secret Autodesk donne le droit d'agir au nom de l'application : ne le collez jamais dans un e-mail ou une conversation. S'il a circulé, régénérez-le dans les réglages de l'application et remplacez-le dans `.env`.

Pour que plusieurs personnes l'utilisent, l'application doit tourner sur une machine accessible par tous, en HTTPS (`APP_BASE_URL=https://…`).

**Développement local sans Autodesk** : avec `APP_BASE_URL` sur `localhost` et `DEV_LOGIN_AS=<login ou e-mail ShotGrid>`, la page de connexion propose un bouton « Connexion de développement » qui ouvre une session au nom de cet utilisateur. Ce bouton n'existe jamais sur une autre adresse que `localhost`.

---

## Architecture

```text
Navigateur (React 18 + Vite) ──REST / SSE──▶ FastAPI (Uvicorn)
                                              ├── ShotGrid (shotgun_api3) ─ synchronisation, vignettes
                                              ├── Ollama ───────────────── réponses de Lia
                                              └── Google Drive (optionnel)
                                                     │
                     SQLite : enregistrements + liens entre entités + index plein texte FTS5
```

```text
html_server/
├── requirements.txt / requirements-dev.txt
├── .env.example
├── dashboard.sqlite3          # copie locale de ShotGrid (non versionnée)
├── backend/
│   ├── main.py                # assemblage de l'application, planificateur de synchronisation
│   ├── config.py              # variables d'environnement
│   ├── db.py                  # schéma SQLite versionné, migrations automatiques
│   ├── records.py             # noms, statuts, productions actives, retards
│   ├── shotgrid.py            # client ShotGrid
│   ├── sync.py                # synchronisation complète / incrémentale, audit
│   ├── retrieval.py           # question → périmètre, éléments, chiffres exacts
│   ├── context.py             # mise en forme des données pour le modèle
│   ├── prompt.py              # prompt système de Lia
│   ├── assistant.py           # endpoint de l'assistante (streaming)
│   ├── users.py               # utilisateur connecté : compte ShotGrid, rôle, productions visibles, sessions
│   ├── auth.py                # connexion Autodesk, contrôle d'accès, connexion Google Drive
│   ├── api.py                 # API de lecture pour l'interface
│   └── migrate_db.py          # migration / reconstruction manuelle
├── scripts/
│   ├── eval_assistant.py      # évaluation de Lia sur les vraies données
│   └── check_login_setup.py   # vérifie que la connexion Autodesk est prête
├── docs/
│   └── connexion-autodesk.md  # guide de mise en service de la connexion
├── tests/                     # pytest, avec un faux client ShotGrid
└── frontend/src/
    ├── App.jsx                # barre du haut, routage, thème, état de la synchronisation
    ├── api.js / lib.js        # client HTTP, routeur, formatage
    ├── index.css              # système visuel
    ├── pages/                 # Overview, ProjectPage, PeoplePage, PersonPage, SyncPage
    └── components/            # ui (barres, statuts, vignettes), TaskTable, SearchPalette, Assistant
```

### Tables SQLite

| Table | Contenu |
|---|---|
| `shotgrid_records` | Un enregistrement ShotGrid par ligne (JSON complet + colonnes indexées : type, id, nom, production, statut) |
| `shotgrid_links` | Chaque lien entre entités : tâche → étape, plan → séquence, tâche → personnes assignées, tâche → tâches amont… |
| `shotgrid_fts` | Index plein texte (FTS5) des noms, descriptions et contenus de notes |
| `entity_types` | Types synchronisés, nom lisible, nombre d'enregistrements, dates de synchronisation |
| `sync_runs` | Historique des synchronisations |
| `user_sessions` | Sessions ouvertes (le cookie ne contient qu'une clé aléatoire) |
| `user_tokens` | Jetons Google Drive par session (jamais stockés dans le cookie) |

---

## Installation

### Prérequis

- **Python 3.10 ou plus récent**
- **Node.js 18+** et **npm**
- **Ollama** avec au moins un modèle de discussion téléchargé (testé avec `llama3.1:latest`)
- Un accès à un site **Autodesk ShotGrid** (identifiant ou clé de script)

### 1. Dépendances Python

```bash
python -m pip install -r requirements.txt
```

### 2. Interface

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Modèle Ollama

```bash
ollama pull llama3.1
```

### 4. Configuration (`.env`)

```bash
cp .env.example .env
```

| Variable | Rôle | Par défaut |
|---|---|---|
| `SHOTGRID_SERVER_URL` | Adresse du site ShotGrid | — |
| `SHOTGRID_LOGIN` / `SHOTGRID_PASSPHRASE` | Connexion par identifiant | — |
| `SHOTGRID_SCRIPT_NAME` / `SHOTGRID_SCRIPT_KEY` | Ou connexion par clé de script | — |
| `OLLAMA_URL` | Adresse d'Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modèle utilisé par défaut (modifiable dans le panneau de Lia) | premier modèle trouvé |
| `OLLAMA_NUM_CTX` | Taille de contexte demandée à Ollama | `16384` |
| `SYNC_ENTITIES` | `auto` (tous les types utiles) ou une liste : `Project,Shot,Task` | `auto` |
| `SYNC_INTERVAL_MINUTES` | Intervalle de la synchronisation automatique (`0` la désactive) | `30` |
| `FULL_SYNC_EVERY_HOURS` | Fréquence de la synchronisation complète | `24` |
| `APP_SECRET` | Clé de signature des sessions. **Obligatoire en production** : sans elle, une clé aléatoire est générée et tout le monde est déconnecté à chaque redémarrage. | aléatoire |
| `APP_BASE_URL` | Adresse publique de l'application | `http://localhost:8000` |
| `APS_CLIENT_ID` / `APS_CLIENT_SECRET` | Application Autodesk pour la connexion (voir *Connexion et droits*) | — |
| `APS_CALLBACK_URL` | URL de rappel, si elle diffère de `APP_BASE_URL/auth/autodesk/callback` | — |
| `SESSION_DAYS` | Durée d'une session | `7` |
| `ROLES_SEE_ALL` | Groupes ShotGrid qui voient toutes les productions | `Admin,Admin Copy,Manager,Supervisor,Audit - Conseil` |
| `ADMIN_ROLES` | Groupes qui gèrent la synchronisation | `Admin,Admin Copy` |
| `DEV_LOGIN_AS` | Développement local uniquement : login ou e-mail ShotGrid à utiliser sans Autodesk | — |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Optionnel : permet à chacun de connecter son Google Drive pour que Lia y cherche des fichiers | — |
| `DATABASE_PATH` | Emplacement de la base SQLite | `dashboard.sqlite3` |

Le fichier `.env` et la base `dashboard.sqlite3` sont exclus de Git : ne les partagez pas.

---

## Lancement

```bash
python -m uvicorn backend.main:app --port 8000
```

Puis ouvrez **http://localhost:8000** et connectez-vous. FastAPI sert l'interface compilée. Une première synchronisation démarre automatiquement après quelques secondes.

### Développement de l'interface (rechargement à chaud)

Dans un premier terminal :

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Dans un second :

```bash
cd frontend
npm run dev
```

Ouvrez **http://localhost:5173** : les appels `/api` et `/auth` sont redirigés vers FastAPI.

---

## Synchronisation avec ShotGrid

- **Automatique** : au démarrage, puis toutes les `SYNC_INTERVAL_MINUTES`. La synchronisation est *incrémentale* : elle récupère les enregistrements modifiés depuis la dernière fois (`updated_at`) et applique les suppressions lues dans le journal d'événements ShotGrid. Une synchronisation *complète* a lieu quand la dernière date de plus de `FULL_SYNC_EVERY_HOURS`.
- **Manuelle** : icône de synchronisation dans la barre du haut, ou page *Synchronisation* (« Synchroniser les changements », « Synchronisation complète »).
- **Types synchronisés** : avec `SYNC_ENTITIES=auto`, tous les types ShotGrid qui contiennent des données, sauf les types techniques (journaux, pages, permissions…). Cela inclut tâches, plans, séquences, étapes, assets, versions, notes et réponses, playlists, temps saisis, fichiers, dépendances et les entités personnalisées du site.
- **Fiabilité** : chaque type est enregistré en une seule transaction ; les enregistrements supprimés dans ShotGrid sont retirés ; une réponse vide de ShotGrid n'efface jamais la copie locale ; une synchronisation interrompue ne bloque pas les suivantes.
- **Vérification** : « Comparer avec ShotGrid » (page *Synchronisation*) ou `GET /api/sync/audit` compare chaque type, enregistrement par enregistrement, et signale les écarts.

Le schéma de la base se met à jour tout seul au démarrage. Pour reconstruire à la main l'index plein texte et les liens :

```bash
python -m backend.migrate_db --rebuild
```

---

## Tests et évaluation

### Tests unitaires

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

Ils couvrent la synchronisation (complète, incrémentale, suppressions, migration), l'analyse des questions, la mise en forme du contexte, l'API, la connexion et le cloisonnement des données entre utilisateurs (y compris pour Lia), avec un faux client ShotGrid. Ils ne nécessitent ni ShotGrid, ni Autodesk, ni Ollama.

### Évaluation de Lia sur les vraies données

`scripts/eval_assistant.py` pose une série de questions à Lia via le serveur en cours d'exécution, connecté avec `DEV_LOGIN_AS` (un compte qui voit toutes les productions). Il vérifie chaque réponse contre des faits calculés dans la base locale : nombre de productions actives, tâches en retard, classements, questions de suite, noms avec fautes de frappe, refus d'inventer un budget ou un réalisateur.

```bash
python scripts/eval_assistant.py --model llama3.1:latest
python scripts/eval_assistant.py --only 2,8,13   # seulement certaines questions
```

Relancez-le après toute modification du prompt (`backend/prompt.py`), de la mise en forme (`backend/context.py`) ou de l'analyse des questions (`backend/retrieval.py`). Avec `llama3.1:latest`, l'ancien prompt obtenait 6/10 ; la version actuelle a obtenu 13/13 sur une exécution complète.

---

## Référence de l'API

| Méthode | Route | Description |
|---|---|---|
| | | Toutes les routes `/api` (sauf `/api/me`) exigent une session et ne renvoient que les données visibles par l'utilisateur. |
| `GET` | `/api/dashboard` | Productions avec avancement, retards et activité ; totaux ; dernières notes |
| `GET` | `/api/projects/{id}` | Synthèse d'une production : étapes, séquences, retards, blocages, équipe |
| `GET` | `/api/records/{EntityType}` | Liste filtrée : `project_id`, `sequence_id`, `step_id`, `person_id`, `bucket` (`open`, `waiting`, `in_progress`, `review`, `done`), `late`, `blocked`, `search`, `sort`, `page`, `limit` |
| `GET` | `/api/people`, `/api/people/{id}` | Charge par personne, tâches d'une personne |
| `GET` | `/api/search?q=` | Recherche plein texte globale |
| `GET` | `/api/thumbnails?entity_type=&ids=` | Liens de vignettes à jour (ceux de ShotGrid expirent) |
| `GET` | `/api/statuses`, `/api/entity-types` | Noms des statuts, types synchronisés |
| `POST` | `/api/sync?mode=auto\|full\|incremental` | Lance une synchronisation (administrateurs) |
| `GET` | `/api/sync/status`, `/api/sync/runs` | Dernière synchronisation, historique |
| `GET` | `/api/sync/audit?include_unsynced=true` | Comparaison en direct ShotGrid ↔ copie locale (administrateurs) |
| `GET` | `/api/models` | Modèles Ollama disponibles |
| `POST` | `/api/query/stream` | Lia, réponse en streaming (SSE) |
| `GET` | `/auth/autodesk/login`, `/auth/autodesk/callback` | Connexion avec le compte Autodesk |
| `GET` | `/auth/dev-login` | Connexion de développement (localhost et `DEV_LOGIN_AS` uniquement) |
| `POST` | `/auth/logout` | Déconnexion |
| `GET` | `/api/me` | Utilisateur connecté (nom, rôle, productions) ou options de connexion |
| `GET` | `/auth/google/login`, `/auth/google/callback` | Connexion de son Google Drive pour Lia (optionnelle) |

---

## Dépannage

**Lia répond « Ollama est injoignable »**
Ollama n'est pas lancé. Démarrez-le, puis vérifiez :
```bash
curl http://localhost:11434/api/tags
```

**Lia répond « … does not support chat »**
Le modèle est mal installé : il apparaît dans la liste mais ses fichiers sont incomplets. Retéléchargez-le, puis testez :
```bash
ollama pull llama3.1
```
```bash
ollama run llama3.1 "Réponds juste : ok"
```
En attendant, choisissez un autre modèle dans le menu du panneau de Lia.

**Une production n'est pas reconnue par Lia**
Utilisez au moins deux mots de son nom (« cocottes en papier »). Les noms trop courts ou trop génériques (« test », « 1 ») ne sont reconnus que s'ils sont écrits exactement.

**`uvicorn` introuvable, ou `ModuleNotFoundError: fastapi`**
Lancez le serveur avec le même Python que celui qui a installé les dépendances : `python -m uvicorn …`. Sous Windows, si plusieurs Python sont installés, vérifiez lequel est utilisé avec `python -c "import sys; print(sys.executable)"`.

**Erreurs SQLite après une mise à jour**
Arrêtez tout ancien serveur encore lancé : une ancienne version du code n'est pas compatible avec le nouveau schéma. Redémarrez ensuite le serveur, qui migre la base automatiquement.

**Pas de bouton « Se connecter avec Autodesk »**
`APS_CLIENT_ID` ou `APS_CLIENT_SECRET` est vide, ou le serveur n'a pas été redémarré depuis la modification de `.env`. Si le redémarrage échoue avec « address already in use » (`[Errno 10048]` sous Windows), une ancienne instance occupe encore le port 8000 : arrêtez-la (`Ctrl + C` dans son terminal) avant de relancer.

**Autodesk affiche « Request error — There was a problem opening this page. »**
L'URL de rappel n'est pas déclarée dans l'application Autodesk. Lancez `python scripts/check_login_setup.py`, qui affiche l'URL déclarée et celle attendue, puis ajoutez la bonne dans *Callback URL* sur aps.autodesk.com. Pas besoin de redémarrer MedIAData.

**« Aucun utilisateur ShotGrid ne correspond à … » à la connexion**
Le compte Autodesk utilisé n'a pas la même adresse e-mail qu'un utilisateur ShotGrid actif. Connectez-vous avec le compte Autodesk lié à ShotGrid, ou demandez à un administrateur de corriger l'adresse dans ShotGrid (puis attendez la synchronisation suivante).

**Une personne ne voit pas une production**
Elle n'est pas membre de cette production dans ShotGrid et son groupe n'est pas dans `ROLES_SEE_ALL`. Ajoutez-la à l'équipe de la production dans ShotGrid, ou ajoutez son groupe à `ROLES_SEE_ALL`.

**Tout le monde est déconnecté à chaque redémarrage**
Définissez `APP_SECRET` dans `.env`.

**L'interface ne reflète pas les dernières modifications**
Recompilez l'interface :
```bash
cd frontend && npm run build
```
Puis rechargez la page sans cache (`Ctrl + Shift + R`).

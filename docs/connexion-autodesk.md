# Mettre en service la connexion Autodesk

Ce guide explique comment passer de la connexion de développement à la vraie connexion : chaque personne se connecte à MedIAData avec son compte Autodesk (le même que pour ShotGrid) et ne voit que les productions auxquelles elle a droit.

**Durée** : environ 30 minutes pour l'étape Autodesk, plus le temps de préparer le serveur si l'application doit être utilisée par toute l'équipe.

**Il vous faut** :
- un compte Autodesk (celui qui gérera l'application) ;
- l'accès au fichier `.env` de la machine qui fait tourner MedIAData ;
- pour un usage en équipe : une machine joignable par tous et un nom de domaine (voir l'étape 6).

À chaque étape, vous pouvez vérifier où vous en êtes avec :

```bash
python scripts/check_login_setup.py
```

Ce script ne modifie rien. Il contrôle la configuration, vérifie que le service Autodesk est joignable, signale les comptes ShotGrid qui ne pourront pas se connecter et résume ce que verra chaque groupe.

---

## Étape 1 — Préparer le compte développeur Autodesk

Autodesk demande un **plan APS** et un **developer hub** avant de pouvoir créer une application.

1. Allez sur [aps.autodesk.com](https://aps.autodesk.com) et cliquez sur **Sign in** (en haut à droite). Connectez-vous avec votre compte Autodesk, ou créez-en un avec **Create account**.
   Si Autodesk vous donne un *backup code* pendant la création du compte, conservez-le en lieu sûr.
2. **Si votre école ou votre studio a déjà un developer hub**, demandez à son administrateur de vous y ajouter, puis passez à l'étape 2.
3. **Sinon, choisissez un plan** : sur la page *It seems you don't have a hub yet*, cliquez sur **View options** dans la carte *Get an APS plan*. Dans la section *Autodesk Platform Services cloud APIs*, choisissez le niveau **Free** : il suffit, puisque MedIAData n'utilise que la connexion.
4. **Créez le hub** : allez sur [manage.autodesk.com](https://manage.autodesk.com), puis **Products and Services > Hubs**, cliquez sur **Create hub**, choisissez **APS developer hub**, donnez-lui un nom (par exemple « MedIAData ») et cliquez sur **Create and Activate**.

## Étape 2 — Créer l'application

1. Retournez sur [aps.autodesk.com](https://aps.autodesk.com), ouvrez le menu de votre profil et choisissez **My applications**.
2. Dans la liste **Developer Hub**, sélectionnez votre hub.
3. Cliquez sur **Create application** :
   - **Name** : `MedIAData` ;
   - **Application Type** : **Traditional Web App** (une application web qui garde son secret côté serveur, ce qui est le cas de MedIAData).
4. Dans les réglages de l'application :
   - **Description** : par exemple « Tableau de bord ShotGrid de l'équipe » ;
   - **Callback URL** : ajoutez les adresses de retour après connexion. Le type *Traditional Web App* en accepte plusieurs ; déclarez-en une par adresse où MedIAData tournera :

     | Usage | URL de rappel |
     |---|---|
     | Tester sur votre poste | `http://localhost:8000/auth/autodesk/callback` |
     | Serveur de l'équipe | `https://<votre-domaine>/auth/autodesk/callback` |

     L'adresse doit correspondre **exactement** à celle que MedIAData envoie : `APP_BASE_URL` suivi de `/auth/autodesk/callback`, avec le même port et sans `/` final. Le script de vérification affiche celle à déclarer.

     Attention : le portail propose parfois une URL par défaut (`http://localhost:8080/`). Elle ne convient pas : remplacez-la, ou ajoutez la bonne à côté.
   - **API Access** : MedIAData n'appelle aucune API Autodesk ; il utilise seulement la connexion (identité et e-mail). Ne cochez que ce que le portail exige.
5. Cliquez sur **Save changes**.

## Étape 3 — Récupérer l'identifiant et le secret

Dans les réglages de l'application (*App settings*), copiez :
- le **Client ID** ;
- le **Client Secret**.

Leur longueur varie selon la date de création de l'application (une application récente a un identifiant de 48 caractères et un secret de 64) : copiez-les en entier, sans espace.

Le secret donne le droit d'agir au nom de l'application. Ne l'envoyez pas par e-mail, ne le mettez pas dans Git (le fichier `.env` est déjà exclu) et ne le collez pas dans une conversation ou un chat. S'il a circulé, régénérez-le dans les réglages de l'application, puis remplacez-le dans `.env`.

## Étape 4 — Configurer MedIAData

Ouvrez le fichier `.env` à la racine du projet et renseignez :

```env
APS_CLIENT_ID=<Client ID copié à l'étape 3>
APS_CLIENT_SECRET=<Client Secret copié à l'étape 3>
APP_SECRET=<clé aléatoire, voir ci-dessous>
APP_BASE_URL=http://localhost:8000
DEV_LOGIN_AS=
```

- **`APP_SECRET`** signe les cookies de session. Générez une valeur longue et aléatoire, puis gardez-la : la changer déconnecte tout le monde.
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- **`APP_BASE_URL`** est l'adresse exacte à laquelle les utilisateurs ouvrent MedIAData. Pour l'instant, `http://localhost:8000` permet de tester sur votre poste (étape 5).
- **`DEV_LOGIN_AS`** : videz-le une fois la vraie connexion testée.

Redémarrez ensuite le serveur MedIAData (arrêtez l'ancien, puis relancez-le), et vérifiez :

```bash
python scripts/check_login_setup.py
```

Il ne doit plus rester de ligne `[BLOQUANT]` (l'avertissement sur l'adresse locale est normal à ce stade).

## Étape 5 — Tester sur votre poste

1. Ouvrez [http://localhost:8000](http://localhost:8000) : la page de connexion affiche **Se connecter avec Autodesk**.
2. Cliquez dessus, connectez-vous sur la page d'Autodesk et acceptez l'accès demandé par MedIAData la première fois.
3. Vous revenez sur MedIAData, connecté. Cliquez sur vos initiales en haut à droite : votre nom, votre groupe ShotGrid et votre périmètre (« voit toutes les productions » ou « voit N productions ») s'affichent.

Si un message d'erreur apparaît sur la page de connexion, voir [Dépannage](#dépannage).

## Étape 6 — Ouvrir l'application à l'équipe

Pour que d'autres personnes s'y connectent, MedIAData doit tourner sur une machine joignable par tous, **en HTTPS** : Autodesk exige une adresse de retour sûre, et les cookies de session ne sont envoyés que de façon sécurisée.

1. **Choisissez la machine** : un serveur ou un poste toujours allumé du réseau de l'école ou du studio. Ollama doit tourner sur la même machine (ou être joignable via `OLLAMA_URL`). Comptez une carte graphique correcte : les réponses de Lia sont traitées l'une après l'autre.
2. **Obtenez un nom de domaine** pointant vers cette machine, par exemple `mediadata.mon-ecole.fr` (à demander au service informatique).
3. **Mettez un proxy HTTPS devant MedIAData.** Avec [Caddy](https://caddyserver.com), qui obtient et renouvelle le certificat tout seul, le fichier `Caddyfile` suffit :
   ```
   mediadata.mon-ecole.fr {
       reverse_proxy localhost:8000
   }
   ```
   Si votre service informatique a déjà un proxy (Nginx, IIS, un pare-feu applicatif…), demandez-lui de rediriger ce domaine vers le port 8000 de la machine.
4. **Mettez à jour `.env`** sur cette machine :
   ```env
   APP_BASE_URL=https://mediadata.mon-ecole.fr
   DEV_LOGIN_AS=
   ```
5. **Vérifiez que l'URL de rappel** `https://mediadata.mon-ecole.fr/auth/autodesk/callback` est bien déclarée dans l'application Autodesk (étape 2).
6. **Lancez MedIAData** de façon à ce qu'il redémarre avec la machine (service Windows, tâche planifiée ou service systemd selon le système), avec :
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
   `--host 127.0.0.1` garde MedIAData accessible seulement via le proxy HTTPS.
7. Relancez `python scripts/check_login_setup.py` sur cette machine : plus aucune ligne `[BLOQUANT]`, et `APP_BASE_URL` en HTTPS.

La connexion de développement disparaît automatiquement dès que `APP_BASE_URL` n'est plus `localhost`.

## Étape 7 — Vérifier les droits

Le script de vérification affiche ce que verra chaque groupe ShotGrid :

```
   Admin                         28 personnes : toutes les productions, gère la synchronisation
   Manager                       19 personnes : toutes les productions
   Artist                         3 personnes : ses productions seulement
```

- Les groupes listés dans `ROLES_SEE_ALL` voient toutes les productions ; les autres ne voient que celles dont ils sont membres dans ShotGrid (champ *Users* de la production).
- Les groupes listés dans `ADMIN_ROLES` gèrent la synchronisation.
- Pour vérifier, demandez à une personne d'un groupe restreint (par exemple *Artist*) de se connecter. Elle ne doit voir que ses productions, et Lia ne doit rien savoir des autres.
- Si un groupe voit tout dans ShotGrid mais pas dans MedIAData, ajoutez-le à `ROLES_SEE_ALL`. À l'inverse, si une personne ne voit pas une production, ajoutez-la à l'équipe de cette production dans ShotGrid. Le changement est pris en compte à la synchronisation suivante (30 minutes au plus).

Le script signale aussi les comptes qui ne pourront pas se connecter :
- **compte sans adresse e-mail valide** : renseignez l'e-mail dans ShotGrid ;
- **adresse partagée par plusieurs comptes actifs** : désactivez le compte en trop dans ShotGrid, ou faites en sorte que le login de l'un d'eux soit cette adresse.

---

## Dépannage

| Ce que vous voyez | Cause probable | Que faire |
|---|---|---|
| Pas de bouton « Se connecter avec Autodesk » | `APS_CLIENT_ID` ou `APS_CLIENT_SECRET` vide, ou serveur non redémarré | Vérifiez `.env`, redémarrez le serveur, lancez le script de vérification |
| Autodesk affiche « Request error — There was a problem opening this page. » dès le clic sur « Se connecter avec Autodesk » | L'URL de rappel `APP_BASE_URL/auth/autodesk/callback` n'est pas déclarée dans l'application Autodesk (souvent, seule l'URL par défaut `http://localhost:8080/` l'est) | Lancez `python scripts/check_login_setup.py` : il indique l'URL déclarée et celle attendue. Ajoutez la bonne dans *Callback URL*, enregistrez, puis réessayez |
| Autodesk affiche une erreur sur l'URL de redirection (*redirect_uri*) | L'URL de rappel déclarée chez Autodesk ne correspond pas exactement à `APP_BASE_URL/auth/autodesk/callback` | Comparez caractère par caractère : `http` / `https`, port, `/` final |
| « La connexion Autodesk a échoué. Réessayez. » | Secret incorrect, horloge du serveur décalée, ou réseau qui bloque `developer.api.autodesk.com` | Recopiez le secret, vérifiez l'heure de la machine, regardez le journal du serveur (ligne « Échec de la connexion Autodesk ») |
| « Aucun utilisateur ShotGrid ne correspond à … » | Le compte Autodesk n'a pas la même adresse e-mail qu'un utilisateur ShotGrid actif | Se connecter avec le compte Autodesk lié à ShotGrid, ou corriger l'e-mail dans ShotGrid puis attendre la synchronisation |
| « Votre compte ShotGrid est désactivé » | Le compte est désactivé dans ShotGrid | Le réactiver dans ShotGrid |
| « Plusieurs utilisateurs ShotGrid actifs utilisent … » | Adresse partagée par plusieurs comptes actifs | Voir l'étape 7 |
| Connecté, puis renvoyé sur la page de connexion | Site ouvert en `http` alors que `APP_BASE_URL` est en `https` (cookie sécurisé non envoyé), ou `APP_SECRET` changé | Ouvrez l'adresse exacte de `APP_BASE_URL` ; ne changez pas `APP_SECRET` |
| Tout le monde est déconnecté à chaque redémarrage | `APP_SECRET` absent | Définissez-le (étape 4) |
| Une personne ne voit pas une production | Elle n'en est pas membre dans ShotGrid et son groupe n'est pas dans `ROLES_SEE_ALL` | Voir l'étape 7 |

## Rappels de sécurité

- `APS_CLIENT_SECRET` et `APP_SECRET` ne doivent exister que dans le `.env` du serveur.
- Laissez `DEV_LOGIN_AS` vide sur le serveur de l'équipe (il est de toute façon ignoré hors `localhost`).
- MedIAData ne voit jamais les mots de passe : la connexion se fait chez Autodesk, et l'application ne reçoit que l'identité et l'adresse e-mail.
- Une session dure `SESSION_DAYS` jours (7 par défaut). « Se déconnecter » la supprime immédiatement côté serveur.

## Sources

- [Create an App](https://aps.autodesk.com/en/docs/oauth/v2/tutorials/create-app/) — création du compte, du plan, du hub et de l'application
- [Traditional Web App](https://aps.autodesk.com/en/docs/oauth/v2/developers_guide/App-types/traditionalweb/) — type d'application, URL de rappel multiples, format de l'identifiant et du secret

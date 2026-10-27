# ADR 0005 — API HTTP et conteneur

Date : 2026-10-22 · Statut : accepté

## Contexte

L'étape 4 (spec A6) expose l'extraction : `POST /v1/extract`, `GET /health`, authentification par clé API, erreurs du tableau A3 et conteneur Docker. Critère : `docker compose up`, puis un appel avec une image, renvoie le JSON attendu.

## Décisions

### Requêtes
- **Lecture multipart en flux et en mémoire** (`api/upload.py`). Le parseur de Starlette bascule sur un fichier temporaire au-delà de 1 Mo, ce qui écrirait l'image sur disque (interdit par A2). La taille est contrôlée pendant la réception : un envoi trop gros est coupé avant d'être lu en entier (413). Un test vérifie qu'aucun fichier temporaire n'est créé pendant un envoi de 2 Mo.
- Seules les parties `front` et `back` sont conservées, chacune une seule fois. 4 parties au plus.
- **Code `invalid_request` (400)** pour une requête mal formée : pas de multipart, `front` absent, champ en double, corps illisible. Ce cas manquait au tableau A3 ; il reprend le même format `{ "error": { "code", "message" } }`. Les 404 et 405 aussi.

### Authentification
- `Authorization: Bearer <clé>`. Seules les **empreintes SHA-256** des clés sont configurées (`VISIONDOC_API_KEY_HASHES`) : une fuite de la configuration ne révèle aucune clé. La comparaison se fait en temps constant, sur toutes les empreintes, sans sortie anticipée.
- Sans clé configurée, toute requête est refusée.
- `python -m inference.api.keys` génère une clé (`vd_` + 32 octets aléatoires) et son empreinte.

### Exécution
- Les modèles sont chargés une fois, au démarrage. `/health` ne répond qu'une fois le service prêt.
- L'extraction tourne hors de la boucle d'événements, une à la fois par processus : les prédicteurs PaddleOCR ne sont pas sûrs en multithread. La montée en charge passe par plusieurs conteneurs. Le service reste sans état, conformément à la spec B4.

### Journaux
- Une ligne JSON par requête : identifiant, méthode, route, statut, durée, code d'erreur. Jamais d'image, de donnée extraite ni de message d'exception.
- Une erreur inattendue est capturée dans le middleware et n'est jamais relancée : le serveur en journaliserait sinon la trace et le message. Seul le type d'exception est noté.
- Le journal d'accès d'uvicorn est désactivé (doublon).

### Conteneur
- Image `linux/amd64` : PaddlePaddle 3.3 ne publie pas de paquet Linux ARM. Sur Apple Silicon, l'image tourne sous émulation.
- `python:3.12-slim-bookworm`, avec `libgl1`, `libglib2.0-0` et `libgomp1`. Dépendances installées avec uv à partir du `uv.lock` figé.
- Modèles téléchargés à la construction : le conteneur démarre sans accès réseau. Utilisateur non root (uid 10001).
- `docker-compose.yml` : port publié sur `127.0.0.1` uniquement, **système de fichiers en lecture seule** (aucune image ne peut être écrite sur disque, même par erreur), `/tmp` en mémoire (64 Mo), toutes les capacités Linux retirées, `no-new-privileges`, 3 Go de mémoire maximum.
- La CI construit l'image puis lance un test de fumée sur le conteneur en lecture seule : santé, refus sans clé, extraction d'un passeport synthétique.

## Mesures (Apple Silicon, image x86 émulée)

| | Valeur |
|---|---|
| Taille de l'image | 910 Mo |
| Mémoire au repos, puis après extractions | ≈ 760 Mo |
| Passeport (une face) | ≈ 4,7 s |
| Nouvelle CNI (deux faces) | ≈ 6 s |
| Journaux : occurrences de nom, prénom ou numéro | 0 |

Sous émulation, ces temps sont pessimistes ; ils seront mesurés en x86 natif à l'étape 5.

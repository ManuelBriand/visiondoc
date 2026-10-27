# Document de référence — Extraction et collecte de pièces justificatives

Oct 21, 2026 · @Manuel

## Comment lire ce document

Ce document rassemble tout le projet en deux parties.

- **Partie A — V0** : une API simple d'extraction des données des pièces d'identité françaises, sur un moteur open source propriétaire. C'est ce qui se code en premier.
- **Partie B — V1** : la plateforme complète de collecte et de contrôle de dossiers, multi-secteur, avec moteur de règles configurable. C'est la cible.

La V0 est développée en premier. La partie B sert de contexte : chaque choix fait en V0 doit rester compatible avec elle.

**Passage de la V0 à la V1**

- Le code de la V0 vit dès le départ dans `/apps/inference` : il devient le service d'inférence de la V1 sans déménagement.
- La route `/v1/extract` de la V0 devient une route interne du service d'inférence, appelée par l'API métier de la V1 à travers l'interface `ExtractionProvider`. Elle peut aussi rester un produit public à part entière.
- Le format des champs `{ value, confidence, source }` et les règles de calcul de la confiance sont identiques en V0 et en V1.
- Correspondance des types : `fr_id_card_2021` et `fr_id_card_legacy` de la V0 deviennent `fr_id_card` (avec un champ `variant`) dans le catalogue de la V1 ; `fr_passport` devient `passport`.
- Stack commune : Python 3.12, FastAPI, Pydantic, uv, pytest, mypy, Ruff.

# Partie A — V0 : API d'extraction de pièces d'identité

## A1. Objectif

Une API qui reçoit une ou deux photos d'une **CNI française ou d'un passeport français** et renvoie les données en JSON, avec une validation de la MRZ et un niveau de confiance par champ. Tout tourne sur un moteur open source propriétaire, sans API externe, sur CPU. Projet de formation et de démonstration, et socle de la V1.

## A2. Périmètre

**Inclus**

- Trois documents : nouvelle CNI (depuis 2021), ancienne CNI, passeport.
- Une route d'extraction, une route de santé, une authentification par clé API.
- Prétraitement de l'image, OCR, lecture et validation de la MRZ, cohérence entre MRZ et zone visuelle.
- Traitement en mémoire : aucune image n'est stockée.
- Un script de benchmark sur des spécimens.

**Exclu** : autres pièces, base de données des dossiers, front, règles configurables, facturation, GPU, entraînement de modèles.

## A3. Contrat d'API

`POST /v1/extract`, en `multipart/form-data`, avec `front` (obligatoire) et `back` (optionnel), en JPEG, PNG ou PDF d'une page, 10 Mo maximum. Authentification par en-tête `Authorization: Bearer <clé>`. `GET /health` renvoie l'état du service et la version du moteur.

Exemple de réponse :

```json
{
  "document_type": "fr_id_card_2021",
  "issuing_country": "FRA",
  "fields": {
    "last_name":       { "value": "MARTIN", "confidence": 1.0, "source": "mrz" },
    "first_names":     { "value": ["CAMILLE", "MARIE"], "confidence": 1.0, "source": "mrz" },
    "birth_date":      { "value": "1990-04-12", "confidence": 1.0, "source": "mrz" },
    "sex":             { "value": "F", "confidence": 1.0, "source": "mrz" },
    "document_number": { "value": "X4RTBPFW4", "confidence": 1.0, "source": "mrz" },
    "expiry_date":     { "value": "2031-06-30", "confidence": 1.0, "source": "mrz" },
    "birth_place":     { "value": "LYON", "confidence": 0.7, "source": "ocr" }
  },
  "mrz": {
    "raw": ["IDFRAX4RTBPFW46...", "...", "..."],
    "format": "TD1",
    "checksums_valid": true
  },
  "checks": [
    { "code": "mrz_checksums", "status": "pass" },
    { "code": "mrz_matches_visual", "status": "pass" },
    { "code": "document_expired", "status": "pass" }
  ],
  "warnings": [],
  "processing_ms": 1840
}
```

Valeurs de `document_type` : `fr_id_card_2021`, `fr_id_card_legacy`, `fr_passport`. Valeurs de `source` : `mrz`, `ocr`, `computed`. Dates en ISO 8601.

Erreurs au format `{ "error": { "code", "message" } }` :

| Code | Statut HTTP | Cas |
| --- | --- | --- |
| `unsupported_document` | 422 | Ni CNI ni passeport français |
| `image_unreadable` | 422 | Flou, coupé, trop sombre ; le message précise la cause |
| `mrz_not_found` | 422 | MRZ absente ou illisible ; pour une CNI 2021, le verso manque peut-être |
| `file_too_large` | 413 | Fichier de plus de 10 Mo |
| `invalid_format` | 415 | Format non accepté ou fichier corrompu |
| `unauthorized` | 401 | Clé API absente ou invalide |

## A4. Pipeline

1. **Contrôle du fichier** : vrai type vérifié par signature binaire (pas par extension), limite de taille, protection contre les images piégées à la décompression, rendu des PDF en image dans un processus isolé.
2. **Prétraitement (OpenCV)** : correction de l'orientation, détection des bords de la carte, redressement, mesure du flou. Une image illisible est refusée avec un code précis.
3. **Localisation et lecture de la MRZ**, puis validation des sommes de contrôle. Trois formats :
   - passeport : 2 lignes de 44 caractères (TD3) ;
   - nouvelle CNI : 3 lignes de 30 caractères (TD1), au verso ;
   - ancienne CNI : 2 lignes de 36 caractères, structure propre à la France, sans date d'expiration dans la MRZ (à lire dans la zone visuelle).
4. **OCR de la zone visuelle** (PaddleOCR, licence Apache 2.0) pour les champs absents de la MRZ : lieu de naissance, date de délivrance, prénoms complets, expiration de l'ancienne CNI.
5. **Fusion et confiance** : la MRZ valide fait foi (1,0) ; un champ OCR confirmé par la MRZ monte à 0,9 ; un champ OCR seul reste à 0,7 ; une divergence entre MRZ et zone visuelle produit un avertissement.
6. **Contrôles** : sommes de contrôle, cohérence MRZ et zone visuelle, document expiré ou non.

## A5. Stack et organisation

Python 3.12, FastAPI, Pydantic, OpenCV, PaddleOCR, dépendances gérées avec uv, tests avec pytest, typage mypy strict, linting Ruff, le tout dans un conteneur Docker. Clés API dans une variable d'environnement : pas de base de données en V0.

```
/apps/inference
  /api          Routes FastAPI, authentification, erreurs
  /mrz          Parseurs TD1, TD3, ancienne CNI, sommes de contrôle
  /vision       Contrôle du fichier, prétraitement, détection de la carte, localisation de la MRZ
  /ocr          OCR de la zone visuelle et extraction des champs
  /pipeline     Orchestration, fusion, confiance, contrôles
  /tests
/benchmarks     Spécimens annotés et script de mesure
/docs           Ce document, décisions d'architecture (ADR)
```

## A6. Étapes

| Étape | Contenu | Terminée quand |
| --- | --- | --- |
| 1. Lecture MRZ | Parseur des trois formats et sommes de contrôle, testés sur des chaînes MRZ, sans image | Les trois formats sont parsés et une erreur d'un seul caractère est détectée, hors équivalences de l'algorithme ICAO 7-3-1 dans les champs alphanumériques (voir ADR 0002) |
| 2. Vision | Contrôle du fichier, prétraitement, détection de la carte, localisation et OCR de la MRZ | La MRZ est lue sur les spécimens nets, une photo floue est refusée |
| 3. Zone visuelle | OCR des champs complémentaires et fusion | Les champs hors MRZ sont extraits avec leur confiance |
| 4. API | Routes, authentification, erreurs, Docker | `docker compose up` puis un appel avec une image renvoie le JSON attendu |
| 5. Benchmark | Précision par champ et par type, temps de traitement | Rapport généré sur l'ensemble des spécimens |

## A7. Spécimens

La qualité de la V0 dépend du jeu de test : spécimens officiels et images synthétiques, de qualités, d'angles et d'éclairages variés, chacun annoté avec les valeurs attendues. Aucune vraie pièce d'identité, y compris personnelle, dans le dépôt, les tests ou les logs. À constituer en parallèle de l'étape 1.

# Partie B — V1 : plateforme de collecte et de contrôle de dossiers

La V1 réutilise le moteur de la V0 comme service d'inférence et construit autour la plateforme complète. Elle ne démarre qu'une fois la V0 terminée et son benchmark publié.

## B1. Vision

Le produit permet à une entreprise d'envoyer un lien à une personne (candidat, locataire, client, fournisseur), de recevoir ses pièces justificatives depuis un téléphone, d'en extraire les données, de les contrôler selon ses propres règles, puis de les injecter dans son système.

## B2. Périmètre de la V1

Le MVP est un SaaS multi-client en libre-service, multi-secteur, complet de la création du lien jusqu'à l'export des données. Tout ce qui n'est pas listé dans « Inclus » est hors périmètre, et ne doit pas être développé sans validation.

**Inclus**

1. Inscription d'une organisation, essai gratuit, rôles et agences (branches).
2. Catalogue commun d'une quinzaine de types de pièces, avec schéma d'extraction et contrôles intrinsèques.
3. Modèles de parcours sectoriels livrés : Intérim et embauche, Location immobilière, Location de véhicule, Onboarding client ou fournisseur B2B.
4. Éditeur de parcours par formulaire : pièces, obligatoire ou optionnel, questions, variables de dossier, conditions, règles de contrôle.
5. Moteur de règles configurable par le client, avec bibliothèque de règles prêtes à l'emploi et mode test.
6. Création de dossiers à l'unité, par import CSV ou par API ; envoi du lien par SMS et e-mail.
7. Page candidat web mobile, en français et en anglais, avec contrôle qualité immédiat des photos.
8. Service d'inférence propriétaire (classification, OCR, MRZ, extraction, niveaux de confiance) avec API externe en secours ; contrôles unitaires et croisés.
9. Back-office de revue : image et champs côte à côte, correction, validation.
10. Relances automatiques configurables.
11. Sorties : JSON, webhooks signés, CSV avec correspondance de colonnes, PDF du dossier, API REST publique documentée.
12. Personnalisation de la page candidat : logo, couleur, nom.
13. Facturation Stripe à l'usage.
14. Sécurité, purge automatique, journal d'audit, hébergement en France.

**Exclu du MVP**

- Éditeur de parcours en glisser-déposer.
- Signature électronique.
- Détection de faux documents et vérification biométrique.
- Vérification du titre de séjour auprès de l'administration (un rappel au recruteur suffit).
- Connecteurs dédiés à des logiciels métier précis.
- Application mobile native et SDK.
- Alertes d'expiration sur les dossiers déjà validés (V1.1).
- Lecture du 2D-Doc (à étudier ; à intégrer seulement si le planning le permet).

## B3. Utilisateurs et parcours

Cinq profils interagissent avec le produit : trois avec un compte, le demandeur par lien magique, le système client par clé API.

| Profil | Rôle technique | Ce qu'il fait |
| --- | --- | --- |
| Administrateur d'organisation | `owner` / `admin` | Inscrit l'organisation, gère agences, utilisateurs, parcours, règles, clés API, webhooks, facturation |
| Responsable d'agence | `manager` | Voit et traite tous les dossiers de son agence, ajuste les parcours si autorisé |
| Opérateur (recruteur, gestionnaire) | `operator` | Crée des dossiers, relit, corrige, valide, exporte |
| Demandeur (candidat, locataire, client) | aucun compte, lien magique | Dépose ses pièces et répond aux questions |
| Système client | clé API | Crée des dossiers, reçoit les webhooks, lit les données |

**Parcours principal**

1. L'opérateur crée un dossier à partir d'un parcours, renseigne le contact du demandeur et les variables du dossier (par exemple loyer, date de début de mission).
2. Le système envoie le lien par SMS et e-mail.
3. Le demandeur ouvre le lien, répond aux questions, photographie chaque pièce ; chaque photo est contrôlée avant d'être acceptée.
4. Chaque pièce est classée, extraite, puis soumise aux contrôles unitaires.
5. Quand toutes les pièces obligatoires sont là, les contrôles croisés et les règles de dossier s'exécutent.
6. Le dossier devient « complet » si tout passe ; sinon « à revoir », ou retour au demandeur pour les erreurs qu'il peut corriger.
7. L'opérateur relit les dossiers « à revoir », corrige et valide.
8. Le dossier complet déclenche le webhook, la facturation et devient exportable ; la purge des images est planifiée.

**Parcours secondaires :** relances automatiques, expiration du lien, annulation par l'opérateur, création par API, import CSV en masse.

## B4. Architecture et stack

Un monorepo avec deux services Python : une API métier FastAPI qui porte toute la logique, et un service d'inférence sur GPU qui héberge les modèles propriétaires. Une application Next.js sert la page candidat et le back-office. Les règles s'évaluent uniquement côté serveur : la page candidat reçoit les résultats par l'API, il n'y a donc qu'une seule implémentation.

| Couche | Choix | Remarque |
| --- | --- | --- |
| API métier | FastAPI (Python 3.12+), Pydantic v2 | API REST, authentification, moteur de règles, facturation |
| Accès aux données | SQLAlchemy 2 + Alembic | Migrations versionnées |
| Traitements asynchrones | Celery ou Dramatiq sur Redis | Choix à trancher au J1 ; extraction, règles, relances, webhooks, purge |
| Service d'inférence | FastAPI interne, PyTorch, OpenCV, PaddleOCR ou docTR, modèle multimodal open source | Déployé séparément, sur GPU |
| Secours d'extraction | API externe derrière `ExtractionProvider` (par exemple Mistral) | Activable par configuration, type de pièce par type de pièce |
| Front | Next.js (App Router, TypeScript) | `/c/{token}` pour le demandeur, `/app` pour le back-office ; types générés depuis l'OpenAPI |
| Base de données | PostgreSQL | JSONB pour schémas, valeurs extraites, règles |
| Stockage des fichiers | Objet compatible S3 hébergé en France (Scaleway ou OVHcloud) | Bucket privé, URL signées à courte durée |
| MRZ, IBAN, NIR, SIREN | Implémentations internes | Algorithmes de somme de contrôle simples et testables |
| SMS et e-mail | Fournisseurs derrière des interfaces `SmsSender`, `Mailer` | Fournisseur européen à choisir |
| Paiement | Stripe, facturation à l'usage (meters) |  |
| Hébergement | Serveurs et GPU en France (Scaleway ou OVHcloud) | Aucune donnée personnelle hors UE |

**Organisation du dépôt**

```
/apps/api        API métier (FastAPI)
/apps/inference  Service d'inférence (FastAPI, GPU)
/apps/web        Next.js
/packages/types  Types TypeScript générés depuis l'OpenAPI de l'API
/benchmarks      Spécimens annotés et scripts de mesure par type de pièce
/docs            Cette spécification, décisions d'architecture (ADR)
/fixtures        Spécimens synthétiques uniquement
```

**Principes d'architecture**

- Multi-tenant par colonne `organization_id` sur toutes les tables métier, imposée par une couche d'accès aux données qui reçoit l'organisation courante en dépendance FastAPI ; Row Level Security de PostgreSQL en seconde barrière. Aucune requête ne doit pouvoir la contourner.
- Toute dépendance externe (inférence, SMS, e-mail, stockage, paiement) passe par une interface, avec une implémentation factice pour les tests.
- Les traitements longs sont toujours asynchrones et idempotents ; un job relancé ne doit ni doubler une facturation ni renvoyer un webhook déjà livré.
- L'API publique est décrite par un fichier OpenAPI, source unique des types du front.
- Le service d'inférence est sans état : pas d'accès à la base, aucun fichier conservé après la requête, accessible uniquement sur le réseau interne avec un jeton de service. Il reçoit une URL signée et renvoie un résultat structuré.

**Pipeline d'inférence propriétaire**

1. Prétraitement (OpenCV) : détection des bords, redressement, recadrage, mesure du flou.
2. Classification : un petit modèle qui reconnaît les 15 types du catalogue.
3. Lectures déterministes : MRZ pour CNI, passeports et titres de séjour.
4. OCR et extraction : OCR classique et règles de position pour les pièces au format fixe ; modèle multimodal open source pour les pièces variables (factures, bulletins de salaire).
5. Confiance calculée comme décrit en section B8.

**Points à trancher avant le J4**

- Coût : un GPU allumé en continu coûte de l'ordre de plusieurs centaines d'euros par mois (à vérifier selon la carte) ; le coût par dossier est mesuré dès le premier jour.
- Licences : chaque modèle et ses poids doivent autoriser l'usage commercial ; vérification consignée dans un ADR.
- Bascule : le benchmark du J4 décide, type de pièce par type de pièce, si le modèle propriétaire remplace l'API de secours.

## B5. Modèle de données et statuts

Le principe central : un dossier pointe vers une **version figée** de son parcours, si bien qu'une modification ultérieure du parcours ou des règles ne change jamais un dossier déjà créé.

| Table | Contenu principal | Remarques |
| --- | --- | --- |
| `organizations` | nom, personnalisation (logo, couleur), paramètres de purge, `stripe_customer_id` | Racine du multi-tenant |
| `branches` | agences d'une organisation | Optionnel pour les petits clients |
| `users` | e-mail, rôle, `organization_id`, agences accessibles |  |
| `document_types` | clé (`fr_id_card`…), libellé, schéma des champs (JSONB), contrôles intrinsèques, version | Catalogue global, non modifiable par les clients |
| `templates` | parcours d'une organisation, secteur d'origine | Copie modifiable d'un modèle sectoriel |
| `template_versions` | instantané complet : exigences, questions, variables, conditions, règles | Immuable une fois publié |
| `dossiers` | `template_version_id`, statut, contact du demandeur, variables (JSONB), réponses aux questions (JSONB), `token_hash`, `expires_at`, agence, créateur |  |
| `dossier_items` | une exigence du parcours dans un dossier, son statut | Une ligne par pièce attendue |
| `files` | clé de stockage, face (recto, verso), score qualité, `purged_at` | Plusieurs fichiers par pièce |
| `extractions` | type détecté, champs extraits (valeur, confiance, source), fournisseur, modèle, coût | Plusieurs tentatives possibles |
| `field_overrides` | correction manuelle d'un champ : ancienne valeur, nouvelle valeur, auteur | La valeur corrigée prime sur l'extraction |
| `rule_results` | règle, version, résultat (`pass`, `fail`, `undetermined`), valeurs comparées, sévérité | Recalculé après toute correction |
| `reminders` | calendrier, prochaine échéance, canal, compteur |  |
| `webhook_endpoints` / `webhook_deliveries` | URL, secret, événements ; tentatives, statut, réponse | Relances exponentielles |
| `api_keys` | préfixe visible, hash, portée, dernière utilisation | La clé complète n'est affichée qu'une fois |
| `usage_records` | dossier facturé, date, identifiant d'envoi à Stripe | Unicité sur le dossier : jamais deux facturations |
| `audit_logs` | acteur, action, cible, horodatage, IP | Aucune donnée extraite dans les logs |

**Statuts d'un dossier**

| Statut | Signification | Transition suivante |
| --- | --- | --- |
| `draft` | Créé, lien pas encore envoyé | `sent`, `cancelled` |
| `sent` | Lien envoyé, pas encore ouvert | `in_progress`, `expired`, `cancelled` |
| `in_progress` | Le demandeur a commencé | `processing`, `expired`, `cancelled` |
| `processing` | Toutes les pièces obligatoires reçues, contrôles en cours | `complete`, `to_review`, `in_progress` (pièce à refaire) |
| `to_review` | Au moins un contrôle en revue humaine ou indéterminé | `complete`, `in_progress` (demande au demandeur), `rejected` |
| `complete` | Validé, facturé, exportable | `exported` |
| `exported` | Récupéré par le client (export, API ou webhook acquitté) | — |
| `rejected` / `expired` / `cancelled` | Fin sans dossier complet | — (non facturé) |

**Statuts d'une pièce (`dossier_items`) :** `missing`, `uploaded`, `rejected_quality`, `processing`, `needs_reupload`, `to_review`, `validated`.

## B6. Catalogue de pièces

Quinze types couvrent les parcours de lancement. Chaque type déclare ses champs (nom, type, obligatoire) et ses contrôles intrinsèques, toujours exécutés, quelles que soient les règles du client.

| Clé | Pièce | Champs extraits | Contrôles intrinsèques |
| --- | --- | --- | --- |
| `fr_id_card` | CNI française (ancien et nouveau format) | `last_name`, `first_names`, `birth_date`, `birth_place`, `sex`, `document_number`, `issue_date`, `expiry_date`, `mrz` | MRZ et sommes de contrôle, cohérence MRZ / zone visuelle, dates plausibles |
| `passport` | Passeport | `last_name`, `first_names`, `birth_date`, `nationality`, `sex`, `document_number`, `issuing_country`, `expiry_date`, `mrz` | MRZ et sommes de contrôle, cohérence MRZ / zone visuelle |
| `fr_residence_permit` | Titre de séjour | `last_name`, `first_names`, `birth_date`, `nationality`, `permit_type`, `document_number`, `expiry_date`, `work_authorization_mention`, `mrz` | MRZ si présente, dates plausibles |
| `driving_licence` | Permis de conduire (format UE) | `last_name`, `first_names`, `birth_date`, `licence_number`, `categories[]` avec dates d'obtention, `expiry_date` | Dates plausibles, catégories connues |
| `proof_of_address` | Facture d'énergie, de télécom ou quittance | `holder_name`, `address`, `postal_code`, `city`, `issue_date`, `issuer` | Date d'émission non future |
| `rib` | RIB | `holder_name`, `iban`, `bic`, `bank_name` | Clé IBAN (mod 97), format BIC |
| `fr_social_security` | Carte Vitale ou attestation | `last_name`, `first_names`, `nir` | Clé du NIR, cohérence NIR / sexe / année et mois de naissance si connus |
| `payslip` | Bulletin de salaire | `employee_name`, `employer_name`, `period_month`, `gross_salary`, `net_salary`, `net_before_tax`, `contract_type` si présent | Net ≤ brut, période non future |
| `tax_notice` | Avis d'imposition | `declarants[]`, `tax_year`, `reference_income`, `tax_amount`, `tax_number`, `reference_notice` | Année cohérente |
| `kbis` | Extrait Kbis | `company_name`, `siren`, `legal_form`, `registered_address`, `legal_representatives[]`, `issue_date` | Clé du SIREN (Luhn) |
| `urssaf_certificate` | Attestation de vigilance URSSAF | `company_name`, `siren`, `issue_date`, `validity_end_date` | Clé du SIREN |
| `insurance_certificate` | Attestation d'assurance | `insured_name`, `insurer`, `policy_number`, `coverage_type`, `start_date`, `end_date` | Début ≤ fin |
| `vehicle_registration` | Carte grise | `registration_number`, `holder_name`, `vin`, `first_registration_date`, `make`, `model` | Format d'immatriculation, longueur du VIN |
| `certificate` | CACES, habilitation, diplôme | `holder_name`, `certificate_type`, `categories[]`, `issue_date`, `expiry_date` | Dates plausibles |
| `other` | Pièce libre | Aucun champ ; simple dépôt | Qualité de l'image uniquement |

**Règles communes à tous les champs**

- Chaque champ extrait est stocké sous la forme `{ value, confidence, source }`, où `source` vaut `extraction`, `mrz`, `computed` ou `override`.
- Les dates sont normalisées en ISO 8601, les montants en centimes d'euro (entiers), les noms en majuscules sans accents dans une valeur normalisée, la valeur brute étant conservée.
- Le catalogue est versionné : ajouter un champ crée une nouvelle version du type, sans casser les parcours existants.

**Restriction légale sur le NIR** : l'usage du numéro de sécurité sociale est strictement encadré. Le champ `nir` n'est extrait et conservé que dans les parcours où sa collecte est autorisée (embauche et paie) ; dans tous les autres, il est ignoré, et l'éditeur de parcours empêche de le demander.

## B7. Moteur de règles

Une règle compare deux opérandes avec un opérateur et produit `pass`, `fail` ou `undetermined` ; le client les compose dans l'éditeur sans écrire de code, et elles sont stockées en JSON dans la version du parcours.

**Forme lisible :** \[opérande gauche\] \[opérateur\] \[opérande droite\] → \[sévérité\]. Exemple : *moyenne du salaire net des 3 derniers bulletins* **≥** *3 × loyer* → alerte.

**Format JSON**

```json
{
  "id": "rule_income_3x_rent",
  "name": "Revenus ≥ 3 × loyer",
  "scope": "aggregate",
  "left": {
    "kind": "aggregate",
    "fn": "avg",
    "document_type": "payslip",
    "field": "net_salary",
    "latest": 3
  },
  "operator": "gte",
  "right": {
    "kind": "expression",
    "op": "mul",
    "args": [
      { "kind": "variable", "key": "rent" },
      { "kind": "const", "value": 3 }
    ]
  },
  "severity": "warning",
  "applies_if": null,
  "message_applicant": null,
  "message_reviewer": "Revenus moyens inférieurs à 3 fois le loyer"
}
```

**Portées (`scope`)**

| Portée | Évaluée quand | Exemple |
| --- | --- | --- |
| `document` | Dès l'extraction de la pièce | CNI valide au moins 30 jours |
| `cross_document` | Quand toutes les pièces concernées sont présentes | Nom du RIB correspond au nom de la pièce d'identité |
| `aggregate` | Quand le nombre de pièces requis est atteint | Moyenne de 3 bulletins ≥ 3 × loyer |
| `dossier` | À la soumission | Au moins une pièce d'identité valide parmi CNI et passeport |

**Opérandes (`kind`)**

| Kind | Paramètres | Valeur |
| --- | --- | --- |
| `field` | `document_type`, `field`, `occurrence` (`first`, `any`, `all`) | Champ extrait, ou corrigé s'il existe un override |
| `aggregate` | `fn` (`sum`, `avg`, `min`, `max`, `count`), `document_type`, `field`, `latest` optionnel | Calcul sur plusieurs pièces du même type |
| `variable` | `key` | Variable du dossier, saisie à la création ou par le demandeur |
| `answer` | `key` | Réponse à une question du parcours |
| `const` | `value` | Valeur fixe |
| `today` | `offset_days` optionnel | Date du jour, éventuellement décalée |
| `expression` | `op` (`add`, `sub`, `mul`, `div`, `add_days`, `add_months`), `args` | Calcul simple entre opérandes |

**Opérateurs**

| Type | Opérateurs |
| --- | --- |
| Dates | `before`, `after`, `between`, `valid_for_at_least_days`, `issued_within_months` |
| Nombres | `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `between` |
| Textes | `eq`, `contains`, `in`, `matches_name` (comparaison tolérante) |
| Présence | `present`, `absent` |

**`matches_name`** normalise les deux côtés (majuscules, sans accents, tirets et apostrophes en espaces), ignore l'ordre des prénoms, accepte qu'un côté ne contienne qu'une partie des prénoms et tolère une distance d'édition de 1 par mot de plus de 5 lettres. C'est l'opérateur le plus exposé aux faux positifs : il doit avoir sa propre suite de tests.

**Résultats et sévérités**

- `pass` : la condition est vraie.
- `fail` : la condition est fausse, avec des valeurs connues et sûres.
- `undetermined` : une valeur manque, ou sa confiance est sous le seuil (0,85 par défaut, configurable par organisation). Un `undetermined` envoie toujours le dossier en revue, quelle que soit la sévérité.

| Sévérité (`severity`) | Effet d'un `fail` |
| --- | --- |
| `blocking` | Si `message_applicant` est renseigné : le demandeur est prévenu et doit corriger. Sinon : revue humaine |
| `review` | Le dossier passe en `to_review` |
| `warning` | Alerte visible par l'opérateur, le dossier peut être complet |

**Conditions (`applies_if`)** : même structure qu'une règle, sans sévérité. Elle détermine si la règle s'applique (par exemple « si la réponse `nationality_eu` = non »). Les mêmes conditions servent à rendre une pièce obligatoire ou non.

**Exigences de conception**

1. Évaluation uniquement côté serveur, par un évaluateur pur (entrées : règle, valeurs du dossier, date de référence ; sortie : résultat et valeurs comparées), sans accès à la base.
2. Chaque résultat stocke les valeurs effectivement comparées, pour l'affichage en revue et l'audit.
3. Les règles sont recalculées après chaque correction manuelle et chaque nouvelle pièce.
4. La date de référence d'un dossier est figée à sa soumission, pour que la revue d'un dossier ne change pas d'un jour à l'autre.
5. Validation des règles à l'enregistrement : champs existants dans le catalogue, opérateur compatible avec le type, variables déclarées dans le parcours.
6. Mode test : appliquer une règle en brouillon aux 100 derniers dossiers de l'organisation et afficher combien auraient échoué, sans rien enregistrer.

**Bibliothèque de règles par défaut** : pièce d'identité valide à la date de référence ; pièce valide encore N jours ; justificatif de domicile de moins de 3 mois ; titulaire du RIB = demandeur ; noms identiques sur toutes les pièces d'identité ; date de naissance identique sur toutes les pièces ; revenus ≥ N × variable ; Kbis de moins de 3 mois ; attestation URSSAF en cours de validité ; titre de séjour valide à la date de début de mission ; catégorie de permis requise présente.

**Garde-fou légal** : les modèles sectoriels livrés doivent respecter la réglementation (liste des pièces exigibles en location, non-discrimination). L'éditeur affiche un avertissement sur toute règle portant sur la nationalité ou le lieu de naissance. À faire valider par un juriste avant le lancement.

## B8. Pipeline de traitement

Une pièce passe par une vérification rapide et synchrone (réponse au demandeur en moins de 5 secondes), puis par une extraction asynchrone ; les règles de dossier s'exécutent ensuite.

1. **Réception** : le front envoie le fichier directement au stockage par URL signée (PUT), puis notifie l'API. Formats acceptés : JPEG, PNG, HEIC, PDF ; 15 Mo maximum. Les photos sont redimensionnées (côté long 2 000 px) et l'orientation EXIF corrigée.
2. **Vérification rapide (synchrone)** : le service d'inférence (OpenCV et modèle de classification) répond à trois questions : est-ce lisible, est-ce le type attendu, la pièce est-elle entière. Échec → `rejected_quality` avec un message précis pour le demandeur (« photo floue », « ce document n'est pas un RIB », « le verso est attendu »).
3. **Extraction (job asynchrone)** : appel au fournisseur avec le schéma JSON du type de pièce ; sortie structurée obligatoire, validée contre le schéma ; une sortie invalide est retentée une fois.
4. **Lectures déterministes** : MRZ, IBAN, NIR, SIREN sont recalculés et vérifiés par le code, jamais pris tels quels du modèle.
5. **Calcul de la confiance** : les modèles ne donnent pas de confiance fiable, elle est donc calculée par champ :
   - 1,0 si le champ est confirmé par une somme de contrôle ou par la MRZ ;
   - 0,9 si le format est valide et la valeur cohérente avec une autre source du dossier ;
   - 0,7 si le format est valide sans autre confirmation ;
   - 0,3 si le format est invalide ou le champ illisible. Ces seuils sont un point de départ, à recalibrer sur les corrections réelles des opérateurs.
6. **Contrôles intrinsèques et règles de portée `document`**, puis mise à jour du statut de la pièce.
7. **Règles de dossier** : quand toutes les pièces obligatoires (selon les conditions) sont `validated` ou `to_review`, exécution des règles `cross_document`, `aggregate` et `dossier`, puis décision du statut du dossier.
8. **Clôture** : dossier `complete` → enregistrement d'usage, webhook `dossier.completed`, planification de la purge.

**Exigences**

- Chaque appel au fournisseur enregistre modèle, durée, jetons et coût estimé : le coût par dossier doit être visible dès le premier jour.
- Une file dédiée par étape, avec des tentatives limitées et une file d'erreurs consultable.
- Les jobs sont idempotents, identifiés par pièce et par version de fichier.
- Le fournisseur est interchangeable : un benchmark sur les spécimens compare les fournisseurs champ par champ, et le choix est un paramètre de configuration.

## B9. Page candidat

C'est l'écran qui détermine le taux de dossiers aboutis, donc le revenu : elle doit fonctionner sur un téléphone d'entrée de gamme, en 4G, sans compte ni installation.

**Accès**

- URL `/c/{token}` ; le token fait 32 octets aléatoires, seul son hash est stocké.
- Validité configurable par parcours (7 jours par défaut) ; un lien expiré affiche le contact de l'organisation.
- Vérification légère à l'ouverture : saisie des 4 derniers chiffres du téléphone ou d'un code reçu par SMS, configurable.

**Déroulé**

1. Accueil aux couleurs de l'organisation : ce qui va être demandé, durée estimée, mention d'information RGPD et consentement.
2. Questions du parcours (elles peuvent conditionner les pièces demandées).
3. Une pièce par écran, dans l'ordre du parcours : consigne illustrée, capture caméra ou import de fichier, recto puis verso si nécessaire.
4. Résultat immédiat de la vérification rapide ; reprise demandée sur place en cas d'échec.
5. Récapitulatif : pièces acceptées, en cours, à refaire ; bouton d'envoi final.
6. Écran de fin, et e-mail ou SMS si une pièce doit être refaite après l'extraction.

**Exigences**

- Mobile d'abord, accessible (contraste, tailles, libellés), français et anglais, langue choisie automatiquement puis modifiable.
- Reprise exacte de la progression à la réouverture du lien.
- Aucune donnée extraite n'est réaffichée au demandeur, hormis ce qui est nécessaire pour qu'il corrige.
- Poids de la page initiale inférieur à 300 Ko, sans dépendance lourde côté client.

## B10. Back-office et éditeur de parcours

Le back-office sert deux usages : traiter les dossiers au quotidien, et configurer parcours et règles.

**Liste des dossiers**

- Filtres : statut, parcours, agence, opérateur, période ; recherche par nom ou e-mail du demandeur.
- File « à revoir » mise en avant, triée par ancienneté.
- Actions : créer, créer en masse (CSV), renvoyer le lien, relancer, annuler, exporter.

**Vue d'un dossier**

- Pour chaque pièce : l'image (zoom, rotation) à gauche, les champs extraits à droite avec leur confiance (code couleur) et leur source.
- Correction d'un champ en ligne : elle crée un `field_override`, recalcule les règles, et reste tracée.
- Liste des résultats de règles, avec les valeurs comparées et le message opérateur.
- Actions : valider le dossier, demander une nouvelle pièce au demandeur (avec motif), rejeter, télécharger le PDF.
- Historique des événements du dossier.

**Éditeur de parcours (formulaire, sans glisser-déposer)**

1. Partir d'un modèle sectoriel ou d'un parcours vide.
2. Pièces : choisir dans le catalogue, obligatoire ou optionnelle, faces attendues, condition d'apparition.
3. Questions : texte, date, nombre, oui/non, choix ; obligatoires ou non.
4. Variables de dossier : nom, type, saisies par l'opérateur à la création ou par API (par exemple `rent`, `mission_start_date`, `required_licence_category`).
5. Règles : ajouter depuis la bibliothèque puis ajuster, ou composer avec les listes déroulantes (opérande, opérateur, opérande, sévérité, messages). Mode test disponible.
6. Relances : calendrier et canaux.
7. Sortie : correspondance des colonnes CSV, événements webhook.
8. Publication : crée une nouvelle `template_version` immuable ; les dossiers en cours restent sur leur version.

**Administration** : utilisateurs et rôles, agences, personnalisation de la page candidat, durée de conservation, clés API, webhooks, facturation, tableau de bord (dossiers par statut, taux de complétion, délai moyen jusqu'au dossier complet, part des champs corrigés, coût d'extraction moyen).

## B11. API publique et webhooks

Une API REST versionnée (`/v1`), authentifiée par clé API en en-tête `Authorization: Bearer`, décrite en OpenAPI et documentée publiquement.

| Méthode | Route | Rôle |
| --- | --- | --- |
| `GET` | `/v1/templates` | Lister les parcours publiés et leurs variables attendues |
| `POST` | `/v1/dossiers` | Créer un dossier : `template_id`, contact, variables, `external_ref`, `send` (bool) ; renvoie l'URL du lien |
| `GET` | `/v1/dossiers/{id}` | Lire un dossier : statut, réponses, champs (valeurs finales), résultats de règles |
| `GET` | `/v1/dossiers` | Lister avec filtres (statut, `external_ref`, dates) et pagination par curseur |
| `POST` | `/v1/dossiers/{id}/send` | Envoyer ou renvoyer le lien |
| `POST` | `/v1/dossiers/{id}/cancel` | Annuler |
| `POST` | `/v1/dossiers/{id}/ack` | Marquer comme exporté |
| `GET` | `/v1/dossiers/{id}/files/{file_id}` | URL signée temporaire vers une pièce (tant qu'elle n'est pas purgée) |
| `GET` | `/v1/dossiers/{id}/pdf` | PDF du dossier |

**Format de sortie d'un dossier** : les champs sont regroupés par exigence du parcours (clé définie dans le parcours), chacun sous la forme `{ value, confidence, source }` ; le schéma de sortie d'un parcours est publié et versionné avec lui.

**Webhooks**

- Événements : `dossier.opened`, `dossier.to_review`, `dossier.completed`, `dossier.rejected`, `dossier.expired`, `document.needs_reupload`.
- Signature HMAC-SHA256 du corps avec le secret de l'endpoint, horodatage dans l'en-tête, tolérance de 5 minutes.
- Relances exponentielles pendant 24 heures, puis désactivation de l'endpoint et alerte à l'administrateur.
- Le corps contient l'identifiant et le statut ; le client récupère les données par `GET` (pas de données personnelles dans les webhooks).

**Règles générales** : en-tête `Idempotency-Key` accepté sur les `POST` ; limite de débit par clé ; erreurs au format `{ error: { code, message, details } }` ; aucune rupture de compatibilité dans `/v1`.

## B12. Facturation à l'usage

L'unité facturée est le dossier passé au statut `complete`, une seule fois par dossier ; tout dossier expiré, annulé ou rejeté est gratuit.

- Essai gratuit : 20 dossiers complets, sans carte bancaire ; ensuite, carte obligatoire pour créer de nouveaux dossiers.
- Stripe : un client par organisation, un abonnement à prix à l'usage (meter) ; chaque `usage_record` est envoyé à Stripe avec une clé d'idempotence égale à l'identifiant du dossier.
- Paliers de prix configurés dans Stripe, pas dans le code ; les montants définitifs restent à fixer.
- Les options payantes (par exemple les relances SMS) sont comptées comme des usages séparés, activés par parcours.
- Écran facturation : consommation du mois en cours, factures Stripe, moyen de paiement.
- Un minimum mensuel pour les grands comptes se configure par organisation, sans développement spécifique.

## B13. Sécurité et RGPD

Le produit traite des pièces d'identité : la sécurité est une fonctionnalité vendue, pas une couche ajoutée à la fin. Le client est responsable de traitement, le produit est sous-traitant.

**Données et stockage**

- Hébergement, base, stockage, sauvegardes et fournisseurs de traitement en France ou dans l'UE ; fournisseur d'extraction sans conservation ni entraînement sur les données, sous contrat.
- Chiffrement en transit (TLS) et au repos ; chiffrement applicatif supplémentaire des champs les plus sensibles (NIR, IBAN, numéros de pièces) via un type de colonne chiffré côté SQLAlchemy.
- Fichiers uniquement accessibles par URL signée de 5 minutes ; jamais d'URL publique.
- Purge automatique : images supprimées N jours après le passage en `complete` ou `exported` (30 par défaut, configurable par organisation), dossiers expirés purgés de la même façon ; les données extraites suivent leur propre durée de conservation.

**Accès**

- Isolation stricte entre organisations, testée automatiquement sur chaque route.
- Rôles et restriction par agence appliqués dans une couche d'autorisation centralisée de l'API (dépendances FastAPI).
- Authentification du back-office avec double facteur disponible ; clés API hashées.
- Journal d'audit de toute consultation d'une pièce, correction, export et suppression.

**Hygiène**

- Aucune donnée personnelle dans les logs, traces d'erreur et outils de monitoring (masquage systématique).
- Limitation de débit sur la page candidat et l'API ; protection contre l'énumération des tokens.
- Dépendances surveillées, secrets hors du dépôt.

**Documents à produire** : contrat de sous-traitance (DPA) type, registre des traitements, liste des sous-traitants ultérieurs, politique de conservation, mention d'information affichée au demandeur.

**Données d'entraînement** : en tant que sous-traitant, le produit ne réutilise aucune pièce client pour entraîner ou améliorer ses modèles sans base légale et clause explicite dans le contrat. Par défaut, l'entraînement se fait uniquement sur spécimens et données synthétiques ; une clause d'amélioration du service, acceptée par le client, est l'option à proposer.

**Compléments obligatoires**

- **Fichiers malveillants** : vrai type vérifié par signature binaire, PDF neutralisés (JavaScript, contenus actifs), protection contre les images piégées à la décompression, rendu des PDF dans un conteneur isolé.
- **Injection dans le modèle** : un document peut contenir du texte écrit pour tromper le modèle. La sortie du modèle est une donnée, jamais une instruction ; aucun champ critique n'est validé sur la seule foi du modèle quand un contrôle déterministe existe.
- **Purge réelle** : versioning du bucket désactivé (sinon une image « supprimée » reste stockée) ; sauvegardes à rétention courte et documentée, puisqu'elles contiennent les données purgées.
- **Webhooks** : blocage des adresses internes et privées pour empêcher les attaques SSRF.
- **Exports CSV** : échappement des cellules commençant par `=`, `+`, `-` ou `@` (injection de formules).
- **Double facteur obligatoire** pour les rôles `owner` et `admin`.
- **Procédure d'incident** : détection, qualification, notification à la CNIL sous 72 heures et information des clients.
- **Accès du support** : politique écrite d'accès aux données des clients par l'équipe produit, tracé dans le journal d'audit.
- **Analyse d'impact (AIPD)** : modèle prêt à fournir aux clients.
- **Test d'intrusion externe** avant le premier client en production.

## B14. Plan de livraison

Sept jalons, environ 13 à 14 semaines de travail à temps plein en théorie, plutôt quatre à six mois en pratique pour une personne seule ; chaque jalon se termine par une démo de bout en bout et ne démarre qu'une fois les critères du précédent remplis.

| Jalon | Semaines | Contenu | Critères d'acceptation |
| --- | --- | --- | --- |
| J1 Fondations | 1–2 | Monorepo, CI, multi-tenant, organisations, utilisateurs, rôles, agences, catalogue en base, interfaces des fournisseurs avec implémentations factices | Tests d'isolation entre organisations verts sur toutes les routes ; le catalogue des 15 types est chargé et versionné |
| J2 Parcours et dossiers | 3–4 | Modèles sectoriels, éditeur (pièces, questions, variables, conditions), versions immuables, création de dossier, envoi du lien | Un opérateur publie un parcours, crée un dossier et le demandeur reçoit le lien |
| J3 Page candidat | 5–6 | Déroulé complet, capture, envoi direct au stockage, vérification rapide, reprise | Un dossier « Intérim » complet est déposé depuis un téléphone en moins de 5 minutes ; une photo floue est refusée sur place |
| J4 Extraction | 7–8 | Service d'inférence sur GPU (prétraitement, classification, OCR, modèle multimodal), jobs d'extraction, lectures déterministes (MRZ, IBAN, NIR, SIREN), confiance, contrôles intrinsèques, benchmark des fournisseurs | Benchmark publié sur les spécimens, modèles propriétaires comparés à l'API de secours type par type ; précision par champ mesurée ; coût par pièce enregistré |
| J5 Moteur de règles | 9–10 | Évaluateur, opérandes, opérateurs, `matches_name`, conditions, bibliothèque, éditeur de règles, mode test, statuts de dossier | Les règles par défaut passent leurs suites de tests ; « revenus ≥ 3 × loyer » fonctionne de bout en bout ; une donnée incertaine produit `undetermined` |
| J6 Revue et sorties | 11–12 | Back-office de revue, corrections, relances, API publique, webhooks, CSV, PDF, documentation | Un système externe crée un dossier par API et reçoit le webhook à la complétion ; une correction recalcule les règles |
| J7 Production | 13–14 | Facturation Stripe, personnalisation, purge, audit, durcissement sécurité, tableau de bord, mise en ligne | Un dossier complet est facturé une seule fois même si le job est rejoué ; les images sont purgées à l'échéance ; premier client en production |

Si le planning glisse, l'ordre de renoncement est : mode test des règles, import CSV en masse, tableau de bord détaillé. Jamais la page candidat, les contrôles d'incertitude, la sécurité ou les sorties.

**À prévoir dès le J1, en transverse** : environnement de préproduction, supervision et alertes sans données personnelles, restaurations de sauvegarde testées, délivrabilité des e-mails (SPF, DKIM, DMARC), CGU et CGV. Le jeu de spécimens multi-types doit être prêt avant le J4, pas constitué pendant.

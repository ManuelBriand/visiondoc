# ADR 0004 — Zone visuelle, fusion et confiance

Date : 2026-10-22 · Statut : accepté

## Contexte

L'étape 3 (spec A6) extrait les champs absents de la MRZ (lieu de naissance, date de délivrance, prénoms complets, expiration de l'ancienne CNI). Elle les fusionne avec la MRZ en calculant une confiance par champ (spec A4, étapes 4 à 6) et produit la réponse du contrat d'API (spec A3).

## Décisions

### OCR de la zone visuelle
- PaddleOCR : détection `PP-OCRv5_mobile_det`, reconnaissance `latin_PP-OCRv5_mobile_rec`. Ce modèle latin garde les accents et la ponctuation des libellés (« à : ORLÉANS »), contrairement au modèle anglais utilisé pour la MRZ. L'interface est `TextEngine` ; le moteur factice des tests renvoie des lignes fixées.
- oneDNN est désactivé pour ce pipeline (`enable_mkldnn=False`) : sous Linux x86, PaddlePaddle 3.3 lève `NotImplementedError` (`ConvertPirAttribute2RuntimeAttribute`) sur le modèle de détection, ce qui concerne aussi l'image Docker. Sur Apple Silicon, oneDNN n'est pas utilisé. Le coût en temps sera mesuré à l'étape 5.
- La MRZ est lue en premier, sur le recto puis sur le verso : elle est au verso de la nouvelle CNI, et l'utilisateur peut envoyer les faces dans n'importe quel ordre. La face qui porte la MRZ est orientée par elle. L'autre face est lue à 0°, puis à 180° si moins de 3 libellés y sont reconnus.

### Repérage des champs par libellés
- Les libellés français et anglais sont comparés sous forme normalisée (majuscules, sans accents ni ponctuation). Un libellé long tolère des erreurs d'OCR (similarité ≥ 0,85) ; un libellé court (« NOM », « SEXE ») doit être exact, et un libellé doit se terminer sur une frontière de mot (« PARIS » n'est pas « PAR »).
- Deux mises en page : valeur sous son libellé (nouvelle CNI, passeport), ou « Libellé : valeur » sur une ligne (ancienne CNI ; « à : LYON » est un cas particulier).
- Tous les libellés connus, même ceux de champs non extraits (adresse, taille, autorité…), sont marqués comme libellés, pour ne jamais être pris pour une valeur.
- **Libellés fusionnés** : l'OCR regroupe parfois deux libellés voisins en une ligne (« Date de délivrance / Date of issue Date d'expiration / Date of expiry »). La ligne est découpée, et l'abscisse de chaque libellé est estimée au prorata des caractères.
- Dates : formats `JJ MM AAAA`, `JJ.MM.AAAA`, `JJ/MM/AAAA` et mois abrégés (« 12 AVR 1990 »). Les confusions de l'OCR (O→0, I→1…) sont corrigées dans les dates seulement.

### Fusion et confiance
| Cas | Confiance | Source |
|---|---|---|
| Champ d'une MRZ valide, ou confirmé par sa propre clé | 1,0 | `mrz` |
| Champ de la zone visuelle confirmé par la MRZ, ou cohérent avec une autre source | 0,9 | `ocr` |
| Champ de la zone visuelle seul | 0,7 | `ocr` |
| Champ de la MRZ dont la **propre clé est fausse** | 0,3 | `mrz` |
| Date d'expiration recalculée (ancienne CNI prolongée) | celle des dates lues | `computed` |

- **Clé fausse → 0,3**, même si la zone visuelle concorde. Le benchmark a montré un numéro « confirmé » par la zone visuelle alors que l'OCR y faisait la même confusion `O`/`0` que dans la MRZ. Une clé fausse est un signal négatif déterministe ; elle prime. Le seuil 0,3 reprend la règle « format invalide » de la spec B8.
- **Numéro ambigu → plafonné à 0,9**, avec l'avertissement `document_number_ambiguous` : c'est le cas où une ou deux confusions `O`/`0` laisseraient toutes les clés valides (ADR 0003). La spec A4 dit « la MRZ valide fait foi (1,0) » ; cette exception le nuance pour le seul cas où la MRZ ne peut pas faire foi.
- **Noms** : comparaison sans espaces ni ponctuation. La zone visuelle remplace la valeur de la MRZ (0,9, `ocr`) quand elle concorde et qu'elle est plus complète :
  - prénoms tronqués par la MRZ ;
  - découpage des prénoms composés : la MRZ écrit « JEAN<PIERRE », comme deux prénoms ; la virgule de la zone visuelle tranche.
  
  Un préfixe ne vaut accord **que si le champ de la MRZ est peut-être tronqué** (il ne finit pas par `<<`). Sinon, « MARTINI » lu à la place de « MARTIN » serait accepté.
- **Cohérence des dates** : une date de délivrance est confirmée (0,9) si l'expiration tombe 5, 10 ou 15 ans plus tard, à un jour près.
- **Ancienne CNI délivrée à un majeur entre le 2 janvier 2004 et le 31 décembre 2013** : validité prolongée de 5 ans (décret n° 2013-1188). L'expiration renvoyée est la date effective (`computed`), avec l'avertissement `validity_extended`. Sans date de délivrance, celle-ci est déduite de la date imprimée (10 ans avant).
- Une divergence entre la MRZ et la zone visuelle garde la valeur de la MRZ et produit l'avertissement `mrz_visual_mismatch` sur le champ.

### Contrôles (spec A3)
`mrz_checksums`, `mrz_matches_visual` et `document_expired` valent `pass`, `fail` ou `undetermined`. `undetermined` s'applique quand rien n'est comparable, ou quand l'expiration est inconnue (ancienne CNI sans verso) ; ce dernier cas ajoute l'avertissement `expiry_unknown`. Les statuts reprennent ceux du moteur de règles de la V1.

### Spécimens
- Faces dessinées avec de vrais libellés : nouvelle CNI (recto sans MRZ, verso avec), ancienne CNI (recto avec MRZ, verso avec les dates), page de données du passeport. Noms, prénoms et lieux sont tirés de listes de noms courants, accents compris. Ces documents factices n'ont aucun élément de sécurité.
- Police Noto Sans (SIL OFL) pour la zone visuelle, téléchargée à un commit figé et vérifiée par SHA-256, comme l'OCR-B. Un texte trop long est imprimé plus petit, comme sur un vrai document.
- Le numéro d'une ancienne CNI commence par l'année et le mois de délivrance, et la validité vaut 10 ans à partir de la délivrance.

## Résultats

Commande : `benchmarks/run.py`, condition nominale, graine 9001 jamais utilisée pendant la mise au point, 50 documents par type. La moitié des nouvelles CNI sont envoyées recto d'abord ; une sur quatre a sa face MRZ à l'envers.

| Type | Champs évalués | Exacts | Faux, signalés | **Faux non signalés** | Absents |
|---|---|---|---|---|---|
| Nouvelle CNI (8 champs) | 400 | 397 | 2 (numéro) | **0** | 1 (délivrance) |
| Ancienne CNI (8 champs) | 392 | 391 | 1 (prénoms) | **0** | 0 |
| Passeport (9 champs) | 450 | 448 | 2 (numéro) | **0** | 0 |
| **Total** | **1 242** | **1 236 (99,5 %)** | 5 | **0** | 1 |

- Un champ faux est **signalé** si sa confiance est < 0,9 ou s'il porte un avertissement. Le seul chiffre qui compte vraiment est celui des faux non signalés : 0. Une mise au point intermédiaire en avait encore 4 (prénoms composés) ; ils ont disparu avec les règles décrites plus haut.
- 1 ancienne CNI sur 50 est refusée à tort (`image_unreadable`) et n'est pas comptée dans le tableau.
- Temps par extraction : médiane 4,0 s, p95 5,6 s (CPU, Apple Silicon), deux faces comprises.

## Limites

- Libellés et mises en page sont inspirés des documents français, mais n'en sont pas des copies : la précision sur de vrais documents reste à mesurer sur des spécimens officiels.
- Une extraction prend environ 4 s sur CPU, dont l'essentiel en détection de texte. Un modèle de détection plus léger, ou une détection limitée aux zones utiles, est une piste pour le benchmark de l'étape 5.

# ADR 0006 — Benchmark, calibrage des seuils et performance

Date : 2026-10-23 · Statut : accepté

## Contexte

L'étape 5 (spec A6) mesure la précision par champ et par type, ainsi que le temps de traitement, sur l'ensemble des spécimens. Le benchmark a servi aussi d'outil de réglage : il a révélé des seuils de qualité trop sévères et un problème de performance sous Linux x86.

## Outils

- `benchmarks/run.py` produit un rapport Markdown et JSON daté dans `benchmarks/reports/`. Il couvre :
  - la précision par champ ;
  - les erreurs signalées et non signalées ;
  - les refus ;
  - 17 conditions de prise de vue dégradées ;
  - le temps par étape ;
  - les spécimens officiels annotés de `benchmarks/specimens/`, mesurés à part.
  
  Aucune valeur extraite n'est écrite dans le rapport.
- `benchmarks/calibrate.py` étudie les seuils de qualité (`quality`, `bright`, `dark`) et les réglages de vitesse (`speed`).
- `.github/workflows/benchmark.yml` lance le benchmark, sur demande, dans l'image de production, en x86 natif.
- `inference.timing` mesure le temps par étape. Il sera repris en V1 pour le coût par dossier (spec B8).

## Décisions

### 1. Qualité d'image : refuser seulement ce qui est certainement illisible
Méthode du calibrage : les contrôles sont désactivés, on extrait quand même, et on compare le résultat à la mesure de qualité.

| Mesure | Lecture fiable jusqu'à | Échec de lecture à partir de | Ancien seuil | Nouveau seuil |
|---|---|---|---|---|
| Netteté (variance du laplacien) | ≈ 15 (flou σ 1,75) | ≈ 10 (σ 3) | 60 | **20** |
| Luminosité moyenne | ≈ 50 | ≈ 25 | 60 | **25** |
| Part de pixels saturés | 93 % (surexposition × 2, lecture parfaite) | — | 25 % | **aucun refus** |

- Une surexposition uniforme sature le fond clair de la carte mais laisse le texte net : l'ancien critère refusait des photos parfaitement lisibles, dès un éclairage × 1,2. Les reflets localisés, qui effacent vraiment le texte, ne sont pas simulés ; ils se manifestent par une MRZ illisible.
- **Deux niveaux** :
  - refus immédiat : trop petit, flou ou très sombre ;
  - sinon, on tente la lecture. Si la MRZ échoue, l'erreur `image_unreadable` nomme la cause la plus probable : pénombre (< 60), surexposition (> 50 % de pixels saturés) ou léger flou (< 60). À défaut, l'erreur est `mrz_not_found`.
  
  Le demandeur garde un message utile, sans refus injustifié : chaque refus à tort coûte un dossier.

### 2. oneDNN : désactivé pour la détection seule
Chaque modèle a été testé sous x86 : seule la détection `PP-OCRv5_mobile_det` lève `NotImplementedError` avec oneDNN. La reconnaissance latine fonctionne avec, et elle est **5 fois plus rapide** (27 ms contre 130 ms par ligne). Le moteur de la zone visuelle charge donc les deux modèles séparément et découpe les lignes entre les deux. Les lignes sont triées par proportions et reconnues par lots de 8 : un lot unique complétait les lignes courtes à la largeur de la plus longue, ce qui ralentissait la lecture et faisait perdre des dates.

### 3. Rotation : tri des coins par angle
À 45°, trier les coins par somme des coordonnées hésite entre deux coins. Ils sont maintenant triés par angle autour du centre, en commençant par un grand côté : le document redressé est toujours en paysage, et le retournement de 180° est corrigé ensuite (MRZ en bas ou libellés lisibles).

### 4. Threads et taille de détection : paramétrables, défauts conservés
x86 natif, 2 processeurs, 24 documents (`benchmarks/reports/2026-10-23-speed-ci-x86.md`) :

| Réglage | Temps médian | p95 | Champs exacts | Faux non signalés |
|---|---|---|---|---|
| Défaut (10 threads, pleine résolution) | 3,14 s | 3,95 s | 100 % | 0 |
| 2 threads | 2,90 s | 3,39 s | 100 % | 0 |
| 4 threads | 3,08 s | 3,40 s | 100 % | 0 |
| 4 threads, détection 960 px | 2,93 s | 3,59 s | 100 % | 0 |
| 4 threads, détection 736 px | 2,41 s | 3,06 s | 99,5 % | 0 |
| 4 threads, détection 640 px | 2,27 s | 2,66 s | 99,5 % | 0 |

Ces réglages sont exposés par `VISIONDOC_CPU_THREADS` et `VISIONDOC_DET_MAX_SIDE`. Les défauts privilégient la précision ; le réglage se fera sur la machine de production. Avant la décision 2, les mêmes réglages donnaient 7,2 à 8,4 s : oneDNN pèse bien plus que ces paramètres.

## Résultats

### Apple Silicon (`benchmarks/reports/2026-10-23-apple-silicon.md`)
100 documents par type en conditions nominales, 15 par type et par condition dégradée.

| | Nouvelle CNI | Ancienne CNI | Passeport |
|---|---|---|---|
| Documents acceptés | 100 % | 100 % | 100 % |
| Documents aux champs tous exacts | 89 % | 98 % | 94 % |
| Temps médian | 4,5 s | 3,4 s | 4,1 s |

- **2 500 champs : 99,2 % exacts, 0 faux non signalé.** Les champs faux restants sont tous signalés. Ce sont surtout des numéros avec une ambiguïté `O`/`0` (avertissement `document_number_ambiguous`) et des dates de délivrance de la nouvelle CNI non lues (5 %).
- **0 faux non signalé dans chacune des 17 conditions dégradées.** Acceptation : 100 % jusqu'à un flou σ 1,0, à 45° d'inclinaison, à JPEG q 10 et à 900 px de large ; 73 % à σ 1,5 ; 80 % en pièce sombre (× 0,3) ; 82 % en surexposition (× 1,6) ; 24 % à 700 px (document trop petit).

### x86 natif, image de production
`benchmarks/reports/2026-10-23-ci-x86.md` : GitHub Actions, Linux x86_64, 2 processeurs, mêmes graines.

| | Nouvelle CNI | Ancienne CNI | Passeport |
|---|---|---|---|
| Temps médian (p95) | 3,6 s (4,3 s) | 2,9 s (3,4 s) | 2,7 s (3,5 s) |
| Avant la décision 2 | 10,5 s | 7,4 s | 8,3 s |

- Précision **identique au document près** à celle mesurée sur Apple Silicon (99,2 %, 0 faux non signalé, mêmes refus) : les résultats sont reproductibles d'une machine à l'autre.
- Temps par étape : OCR de la zone visuelle 2,2 à 2,9 s (deux faces pour les CNI), OCR de la MRZ 0,3 à 0,4 s, tout le reste moins de 0,2 s.

## Limites et suite

- Tous les chiffres portent sur des **spécimens synthétiques**. Aucun spécimen officiel annoté n'est encore dans `benchmarks/specimens/` : c'est la prochaine mesure à faire, avant toute communication de résultats.
- Les reflets localisés, les flous de bougé, les cartes abîmées et les fonds chargés ne sont pas simulés.
- La date de délivrance de la nouvelle CNI (verso) reste le champ le moins bien lu.

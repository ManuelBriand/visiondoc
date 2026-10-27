# ADR 0003 — Vision et lecture de la MRZ sur photo

Date : 2026-10-22 · Statut : accepté

## Contexte

L'étape 2 (spec A6) va d'un fichier reçu à une MRZ lue et validée. Critère : la MRZ est lue sur les spécimens nets, et une photo floue est refusée.

## Décisions

### Fichier
- Le type est vérifié par signature binaire (JPEG, PNG, PDF), sans dépendance. 10 Mo maximum.
- Le nombre de pixels est lu dans l'en-tête et plafonné à 40 Mpx avant décodage, contre les images piégées. L'orientation EXIF est appliquée.
- Les PDF sont rendus avec `pypdfium2` (Apache 2.0 / BSD), pas PyMuPDF (AGPL). Le rendu se fait dans un processus `spawn` tué après 15 s, sans formulaires ni annotations, et le PDF doit avoir une seule page.
- Tout reste en mémoire.

### Document et qualité
- Le contour du document est cherché avec Canny, puis enveloppe convexe et quadrilatère, avant redressement de la perspective à 1 200 px de large. Sans contour (scan pleine page), l'image entière est utilisée.
- **Document coupé** : la plus grande région claire touche 1 à 3 bords de l'image. On ne refuse (`image_unreadable`, cause `cropped`) que si la MRZ est introuvable : un document dont la MRZ est lisible reste exploitable.
- **Qualité**, mesurée sur le document redressé : largeur source < 500 px (`too_small`), luminosité moyenne < 60 (`too_dark`), plus de 25 % de pixels saturés (`overexposed`), variance du laplacien < 60 (`blurry`). Sur les spécimens synthétiques, les photos nettes mesurent ≥ 439 et les floues (σ = 3,5) ≤ 14. Les seuils sont à recalibrer sur de vraies photos.

### Localisation de la MRZ
- Filtre blackhat, gradient horizontal, fermetures morphologiques. On retient la plus basse des bandes larges (≥ 55 % du document), puis on la découpe en lignes par profil horizontal.
- Une bande trouvée dans la moitié haute signale un document à l'envers : on le retourne de 180°. Une image en portrait est d'abord tournée de 90°.

### Reconnaissance
- PaddleOCR `en_PP-OCRv5_mobile_rec`, en reconnaissance seule. Il fait mieux que `PP-OCRv5_server_rec`, qui mélange majuscules et minuscules.
- **Pas fixe** : le décodeur CTC fusionne les `<` consécutifs, donc chaque ligne est étirée à environ 1,05 fois sa hauteur par caractère. Sur 75 lignes : 55 % de lectures exactes sans étirement, 93 % avec.
- Les `<` finaux sont complétés ou tronqués à la longueur attendue (30, 36 ou 44). Pour 2 lignes, le texte lu tranche entre 36 et 44, avec une seconde lecture si les proportions trompaient.
- Le préfixe fixe `IDFRA` de l'ancienne CNI est restauré si un seul caractère diffère.

### Correction des ambiguïtés
- Les confusions `O`/`0`, `I`/`1`… dans les champs alphanumériques (numéro, données optionnelles) sont corrigées seulement si **une seule** variante rend toutes les clés valides, avec au plus 2 permutations. Toute correction est tracée dans `corrections`.
- **Rejeté : arbitrage par comparaison de glyphes.** On comparait chaque caractère ambigu à des prototypes tirés du même document (`0` d'une date, `O` d'un nom). Mesures :

  | Paire | Confusions corrigées | Faux changements |
  |---|---|---|
  | `0`/`O` | ≈ 40 % | 3,2 % |
  | `1`/`I`, `2`/`Z`, `5`/`S`, `6`/`G`, `8`/`B` | ≈ 25 à 40 % | 1,2 à 4,2 % |

  Il y a plusieurs positions ambiguës par document, donc les faux changements finissent par passer les clés : 3 erreurs silencieuses sur 50 passeports. Une MRZ signalée part en revue ; une erreur silencieuse est bien pire.

### Dépendances
- `opencv-contrib-python==4.10.0.84` (avec GUI), imposé par paddlex, qui vérifie la présence du paquet par son nom. L'image Docker devra inclure `libgl1`.
- PaddleOCR et PaddlePaddle (Apache 2.0) sont dans l'extra `ocr`. Les tests rapides utilisent un lecteur factice ; les tests marqués `slow` utilisent le vrai modèle.

### Spécimens synthétiques
- Police OCR-B de Matthew Skala (conversion versée au domaine public, à partir des fichiers Metafont de Norbert Schwarz, libérés depuis). Elle est téléchargée à une version figée et vérifiée par SHA-256. Elle n'est jamais commitée ni livrée avec le service.
- Les documents factices (fond imprimé, guilloches, faux texte, MRZ à pas fixe de 2,54 mm) sont photographiés en simulation : perspective, rotation, éclairage, bruit, JPEG, flou. Aucune image n'est écrite sur disque.

## Résultats

Commande : `benchmarks/read_mrz.py`, 3 graines jamais utilisées pendant la mise au point, 150 spécimens par type (50 par graine).

| | Nouvelle CNI | Ancienne CNI | Passeport | Total |
|---|---|---|---|---|
| Lus correctement | 145 | 144 | 142 | **431 / 450 (95,8 %)** |
| Clés invalides (signalés) | 2 | 4 | 7 | 13 |
| MRZ non trouvée ou refus à tort | 1 | 2 | 1 | 4 |
| **Erreurs silencieuses** | **2** | 0 | 0 | **2 (0,4 %)** |
| Photos floues refusées | 150 / 150 | 150 / 150 | 150 / 150 | 450 / 450 |

Temps médian : 0,7 s par image sur CPU (Apple Silicon).

## Risque résiduel et suite

Les 2 erreurs silencieuses ont la même cause : deux `0` lus `O` dans le numéro de la nouvelle CNI, à des positions de poids 3 et 7. Leurs écarts s'annulent dans la clé : 24 × 3 + 24 × 7 = 240 ≡ 0 (mod 10). Mesures prévues à l'étape 3 :
- recouper le numéro de la MRZ avec celui de la zone visuelle (`mrz_matches_visual`) ;
- ne pas donner la confiance 1,0 à un numéro qui contient des caractères ambigus et qui n'est pas confirmé par la zone visuelle.

Ces résultats portent sur des spécimens synthétiques. Il faudra les confirmer sur des spécimens officiels et de vraies conditions de prise de vue avant toute conclusion.

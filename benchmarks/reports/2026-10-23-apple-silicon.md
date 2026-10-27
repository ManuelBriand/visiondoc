# Benchmark V0 — apple-silicon

| Paramètre | Valeur |
|---|---|
| date | 2026-10-23T20:12:13 |
| commit | 2ad4180 |
| machine | Darwin arm64, 10 processeurs |
| python | 3.12.13 |
| paddlepaddle | 3.3.1 |
| paddleocr | 3.4.1 |
| det_max_side | None |
| cpu_threads | None |
| seed | 20261101 |
| nominal_per_kind | 100 |
| degraded_per_kind | 15 |

## Synthèse (conditions nominales)

- Champs évalués : 2500 ; exacts : 99.2 % ; **faux non signalés : 0**.
- Un champ faux est signalé si sa confiance est < 0,9 ou s'il porte un avertissement.
- Spécimens synthétiques : à confirmer sur des spécimens officiels.

### Par document

| Type | Documents | Acceptés | Tous champs exacts | Refus (code : nombre) | Temps médian | p95 |
|---|---|---|---|---|---|---|
| Nouvelle CNI | 100 | 100.0 % | 89.0 % | — | 4.50 s | 5.37 s |
| Ancienne CNI | 100 | 100.0 % | 98.0 % | — | 3.42 s | 3.59 s |
| Passeport | 100 | 100.0 % | 94.0 % | — | 4.09 s | 4.67 s |

### Par champ

| Type | Champ | Exacts | Faux signalés | **Faux non signalés** | Absents |
|---|---|---|---|---|---|
| Nouvelle CNI | birth_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Nouvelle CNI | birth_place | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Nouvelle CNI | document_number | 94 / 100 (94.0 %) | 6 | **0** | 0 |
| Nouvelle CNI | expiry_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Nouvelle CNI | first_names | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Nouvelle CNI | issue_date | 95 / 100 (95.0 %) | 0 | **0** | 5 |
| Nouvelle CNI | last_name | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Nouvelle CNI | sex | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | birth_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | birth_place | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | document_number | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | expiry_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | first_names | 98 / 100 (98.0 %) | 2 | **0** | 0 |
| Ancienne CNI | issue_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | last_name | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Ancienne CNI | sex | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | birth_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | birth_place | 99 / 100 (99.0 %) | 1 | **0** | 0 |
| Passeport | document_number | 95 / 100 (95.0 %) | 5 | **0** | 0 |
| Passeport | expiry_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | first_names | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | issue_date | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | last_name | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | nationality | 100 / 100 (100.0 %) | 0 | **0** | 0 |
| Passeport | sex | 100 / 100 (100.0 %) | 0 | **0** | 0 |

## Robustesse (tous types confondus)

| Condition | Acceptés | Refus | Champs exacts (acceptés) | **Faux non signalés** |
|---|---|---|---|---|
| nominal | 100.0 % | — | 99.2 % | **0** |
| flou sigma 1,0 | 100.0 % | — | 100.0 % | **0** |
| flou sigma 1,5 | 73.3 % | image_unreadable : 12 | 99.3 % | **0** |
| flou sigma 2,0 | 8.9 % | image_unreadable : 41 | 100.0 % | **0** |
| flou sigma 2,5 | 0.0 % | image_unreadable : 45 | — | **0** |
| flou sigma 3,0 | 0.0 % | image_unreadable : 45 | — | **0** |
| inclinaison 20° | 100.0 % | — | 99.7 % | **0** |
| inclinaison 30° | 100.0 % | — | 99.2 % | **0** |
| inclinaison 45° | 97.8 % | mrz_not_found : 1 | 99.7 % | **0** |
| sombre x 0,5 | 100.0 % | — | 99.5 % | **0** |
| sombre x 0,3 | 80.0 % | image_unreadable : 9 | 100.0 % | **0** |
| surexposé x 1,6 | 82.2 % | image_unreadable : 8 | 99.7 % | **0** |
| JPEG q 40 | 100.0 % | — | 99.7 % | **0** |
| JPEG q 20 | 100.0 % | — | 99.2 % | **0** |
| JPEG q 10 | 100.0 % | — | 97.9 % | **0** |
| photo 1 200 px | 97.8 % | mrz_not_found : 1 | 100.0 % | **0** |
| photo 900 px | 100.0 % | — | 98.9 % | **0** |
| photo 700 px | 24.4 % | image_unreadable : 34 | 93.6 % | **0** |

## Temps médian par étape (conditions nominales, documents acceptés)

| Étape | Nouvelle CNI | Ancienne CNI | Passeport |
|---|---|---|---|
| `file` | 21 ms | 17 ms | 8 ms |
| `document` | 11 ms | 8 ms | 5 ms |
| `mrz_locate` | 9 ms | 5 ms | 5 ms |
| `mrz_ocr` | 856 ms | 675 ms | 817 ms |
| `mrz_parse` | 0 ms | 0 ms | 0 ms |
| `visual_ocr` | 3545 ms | 2717 ms | 3210 ms |
| `fusion` | 0 ms | 0 ms | 0 ms |

## Spécimens officiels

Aucun spécimen officiel annoté dans `benchmarks/specimens/`.

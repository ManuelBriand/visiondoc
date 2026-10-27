# ADR 0002 — Lecture et validation de la MRZ

Date : 2026-10-22 · Statut : accepté

## Contexte

L'étape 1 (spec A6) exige que toute erreur d'un seul caractère dans la MRZ soit détectée. La MRZ arrive de l'OCR (étape 2) : les confusions entre lettres et chiffres (`O`/`0`, `I`/`1`, `S`/`5`, `B`/`8`) sont fréquentes.

## Décisions

1. **Limite de l'algorithme ICAO.** La clé 7-3-1 modulo 10 ne distingue pas deux caractères dont les valeurs diffèrent d'un multiple de 10 (`A`=10 et `0`, `K`=20 et `A`, `<` et `0`). Le critère de l'étape 1 est donc reformulé : toute erreur d'un caractère est détectée, hors de ces équivalences dans les champs alphanumériques. Mesure sur toutes les substitutions possibles d'un caractère dans les zones couvertes par une clé :

   | Format | Substitutions | Non détectées |
   |---|---|---|
   | TD1 (nouvelle CNI) | 1 836 | 126 (numéro, données optionnelles) |
   | TD3 (passeport) | 1 440 | 78 (numéro, données optionnelles) |
   | Ancienne CNI | 2 592 | 154 (numéro, noms : `A`/`K`/`U`…) |

   Le contrôle `mrz_matches_visual` (étape 3) est le filet de sécurité de ces cas.

2. **Correction des confusions OCR, seulement quand la nature du champ est certaine.** Dates et clés : lettres → chiffres. Noms et codes pays : chiffres → lettres. Les champs alphanumériques (numéro du document, données optionnelles) ne sont jamais corrigés. Chaque correction est tracée par sa position dans `MrzResult.corrections`. Un chiffre non corrigeable dans un nom (`3`, `4`, `7`, `9`) rend la MRZ illisible (`invalid_field`).

3. **Les dates sont toujours complètes.** Un `<` dans une date (date partiellement inconnue, admise par l'ICAO) invalide le champ. Les pièces françaises ont des dates complètes, et cette règle ferme l'équivalence `<`/`0`.

4. **Siècle des dates.** Naissance : jamais dans le futur par rapport à la date de référence. Expiration : au plus 50 ans après la date de référence. La date de référence est un paramètre, fixé dans les tests.

5. **Nommage.** Le format de l'ancienne CNI s'appelle `FR_LEGACY` ; la spec ne le nommait pas. Le générateur de MRZ synthétiques est dans `inference/mrz/generator.py` : il sert aux tests et servira aux images synthétiques.

6. **Aucune donnée dans les erreurs.** Les messages de `MrzError` ne reprennent jamais le contenu de la MRZ.

## Conséquences

- Un document dont la MRZ passe toutes les clés peut encore porter une erreur d'un caractère dans son numéro. La confiance 1,0 attribuée à la MRZ (spec A4) suppose donc la cohérence avec la zone visuelle.
- Les seuils de correction OCR seront réévalués au benchmark de l'étape 2.

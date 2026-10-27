# ADR 0001 — Structure du monorepo et du service d'inférence

Date : 2026-10-22 · Statut : accepté

## Contexte

La spécification (A5, B4) place le code de la V0 dans `/apps/inference`, qui devient le service d'inférence de la V1 sans déménagement. Elle liste les sous-dossiers `api`, `mrz`, `vision`, `ocr`, `pipeline`, `tests`.

## Décision

- `/apps/inference` est un projet uv autonome (Python 3.12), avec un layout `src/` : `src/inference/{api,mrz,vision,ocr,pipeline}` et `tests/` à côté.
- Le layout `src/` garantit que les tests importent le paquet installé et non les fichiers du répertoire courant. Il simplifie mypy et l'image Docker.
- Qualité : Ruff (lint et format), mypy strict, pytest. La CI GitHub Actions exécute les quatre à chaque push.
- `/benchmarks` contient les spécimens annotés et les scripts de mesure. `/docs` contient la spécification et les ADR.

## Conséquences

- Les sous-dossiers de la spec sont conservés à l'identique, sous `src/inference/`.
- La V1 ajoutera `/apps/api`, `/apps/web` et `/packages/types` à côté, sans toucher à `/apps/inference`.

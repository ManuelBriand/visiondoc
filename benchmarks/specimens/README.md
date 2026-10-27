# Spécimens officiels annotés

Uniquement des **spécimens officiels publiés** (ANTS, ministère de l'Intérieur, Commission européenne, PRADO…). Jamais une vraie pièce d'identité, y compris personnelle (spec A7).

Un dossier par type : `fr_id_card_2021/`, `fr_id_card_legacy/`, `fr_passport/`. Pour chaque spécimen, les images et un fichier JSON du même nom :

```json
{
  "front": "specimen_recto.jpg",
  "back": "specimen_verso.jpg",
  "source": "URL de publication du spécimen",
  "expected": {
    "last_name": "MARTIN",
    "first_names": ["CAMILLE", "MARIE"],
    "birth_date": "1990-04-12",
    "sex": "F",
    "document_number": "X4RTBPFW4",
    "expiry_date": "2031-06-30",
    "birth_place": "LYON"
  }
}
```

`back` est facultatif. Seuls les champs présents dans `expected` sont évalués. Les valeurs suivent le format de la réponse de l'API : majuscules sans accents, dates ISO 8601.

`benchmarks/run.py` les évalue à part des spécimens synthétiques.

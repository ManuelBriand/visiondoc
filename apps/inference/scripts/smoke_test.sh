#!/usr/bin/env bash
# Test de fumée du conteneur : santé, authentification, extraction d'un spécimen synthétique.
# Usage : scripts/smoke_test.sh <url> <clé API> <image du spécimen>
set -euo pipefail
url=$1 key=$2 specimen=$3

for _ in $(seq 60); do
  curl -fsS "$url/health" > /dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$url/health"
echo

status=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$url/v1/extract" -F "front=@$specimen")
[ "$status" = 401 ] || { echo "sans clé : attendu 401, obtenu $status"; exit 1; }

response=$(curl -fsS -X POST "$url/v1/extract" -H "Authorization: Bearer $key" -F "front=@$specimen")
echo "$response"
python3 -c '
import json, sys
body = json.loads(sys.argv[1])
assert body["document_type"] == "fr_passport", body
assert body["mrz"]["checksums_valid"], body
assert {"last_name", "birth_date", "document_number"} <= set(body["fields"]), body
print("OK")
' "$response"

"""Clés API : génération et vérification. Seule l'empreinte SHA-256 est conservée.

python -m inference.api.keys   # affiche une nouvelle clé et son empreinte
"""

import hashlib
import hmac
import secrets

KEY_PREFIX = "vd_"


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def is_valid(key: str, hashes: frozenset[str]) -> bool:
    """Comparaison en temps constant avec chaque empreinte, sans sortie anticipée."""
    candidate = fingerprint(key)
    matched = False
    for expected in hashes:
        matched |= hmac.compare_digest(candidate, expected)
    return matched


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


if __name__ == "__main__":
    key = new_key()
    print(f"Clé (à transmettre au client, affichée une seule fois) : {key}")
    print(f"Empreinte (à ajouter à VISIONDOC_API_KEY_HASHES)      : {fingerprint(key)}")

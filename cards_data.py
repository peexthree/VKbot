from __future__ import annotations
import json
import os

_TAROT_DB_CACHE = None

def get_tarot_db() -> dict:
    global _TAROT_DB_CACHE
    if _TAROT_DB_CACHE is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), 'tarot_db.json'), 'r', encoding='utf-8') as f:
                _TAROT_DB_CACHE = json.load(f)
        except Exception:
            _TAROT_DB_CACHE = {}
    return _TAROT_DB_CACHE

def get_card_data(card_id: str | int) -> dict:
    db = get_tarot_db()
    return db.get(str(card_id), {})

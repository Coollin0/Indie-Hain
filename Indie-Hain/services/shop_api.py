from __future__ import annotations
from typing import List, Dict, Any
import requests

from services.env import api_base

API = api_base()


def list_public_games() -> List[Dict[str, Any]]:
    """
    Holt alle freigegebenen Games aus dem Distribution-Backend.
    Wird vom Shop benutzt.
    """
    r = requests.get(f"{API}/api/public/apps")
    r.raise_for_status()
    return r.json()


def get_public_game(game_id: int) -> Dict[str, Any] | None:
    """
    Holt ein einzelnes Game nach ID vom Distribution-Backend.
    Wird z.B. von der Library benutzt, um aktuelle Metadaten nachzuladen.
    """
    url = f"{API}/api/public/apps/{int(game_id)}"
    r = requests.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()

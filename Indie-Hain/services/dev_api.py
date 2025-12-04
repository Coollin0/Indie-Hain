from __future__ import annotations
from typing import List, Dict, Any
import requests

from .uploader_client import API, _headers


def get_my_apps() -> List[Dict[str, Any]]:
    """
    Holt alle Apps des aktuellen Devs/Admins vom Distribution-Backend.
    """
    r = requests.get(f"{API}/api/dev/my-apps", headers=_headers("dev"))
    r.raise_for_status()
    return r.json()


def get_app_purchases(app_id: int) -> List[Dict[str, Any]]:
    """
    Holt die Kauf-Historie für eine App (user_id, price, purchased_at).
    """
    r = requests.get(
        f"{API}/api/dev/apps/{app_id}/purchases",
        headers=_headers("dev"),
    )
    r.raise_for_status()
    return r.json()


def update_app_meta(
    slug: str,
    *,
    title: str | None = None,
    price: float | None = None,
    description: str | None = None,
    cover_url: str | None = None,
    sale_percent: float | None = None,
) -> dict:
    """
    Aktualisiert Metadaten einer App (Titel, Preis, Beschreibung, Cover, Rabatt).
    Nur Felder, die nicht None sind, werden geändert.
    """
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if price is not None:
        payload["price"] = float(price)
    if description is not None:
        payload["description"] = description
    if cover_url is not None:
        payload["cover_url"] = cover_url
    if sale_percent is not None:
        payload["sale_percent"] = float(sale_percent)

    if not payload:
        return {"ok": True, "note": "nothing_to_update"}

    r = requests.post(
        f"{API}/api/dev/apps/{slug}/meta",
        headers=_headers("dev"),
        json=payload,
    )
    r.raise_for_status()
    return r.json()



def report_purchase(app_id: int, price: float) -> dict:
    """
    Meldet einen Kauf vom Launcher ans Distribution-Backend.
    Wird im checkout() aufgerufen.
    """
    r = requests.post(
        f"{API}/api/user/purchases/report",
        headers=_headers("user"),  # require_user()
        json={"app_id": int(app_id), "price": float(price)},
    )
    r.raise_for_status()
    return r.json()

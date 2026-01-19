from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import requests

from services.env import api_base


@dataclass
class User:
    id: int
    email: str
    role: str
    username: str
    avatar_path: Optional[str] = None
    token: Optional[str] = None


class AuthService:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or api_base()).rstrip("/")
        self._token: Optional[str] = None

    def set_token(self, token: Optional[str]):
        self._token = token

    def _auth_headers(self) -> dict:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def _user_from_payload(self, payload: dict, token: Optional[str]) -> User:
        return User(
            id=int(payload.get("id", 0)),
            email=payload.get("email", ""),
            role=(payload.get("role") or "user").lower(),
            username=payload.get("username") or "",
            avatar_path=None,
            token=token,
        )

    def register(self, email: str, password: str, username: str, avatar_src_path: Optional[str] = None) -> User:
        r = requests.post(
            f"{self.base_url}/api/auth/register",
            json={"email": email, "password": password, "username": username},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        self._token = token
        return self._user_from_payload(data.get("user", {}), token)

    def login(self, email: str, password: str) -> Optional[User]:
        r = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"email": email, "password": password},
            timeout=20,
        )
        if r.status_code == 401:
            return None
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        self._token = token
        return self._user_from_payload(data.get("user", {}), token)

    def me(self, token: str) -> Optional[User]:
        self._token = token
        r = requests.get(
            f"{self.base_url}/api/auth/me",
            headers=self._auth_headers(),
            timeout=20,
        )
        if r.status_code in (401, 403):
            return None
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}), token)

    def update_profile(self, user_id: int, username: Optional[str] = None, avatar_src_path: Optional[str] = None) -> User:
        if not self._token:
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/auth/profile",
            headers=self._auth_headers(),
            json={"username": username},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}), self._token)

    def upgrade_to_dev(self, user_id: int) -> User:
        if not self._token:
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/auth/upgrade/dev",
            headers=self._auth_headers(),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}), self._token)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        return None

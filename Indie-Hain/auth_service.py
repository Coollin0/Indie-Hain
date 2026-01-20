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
        avatar_url = payload.get("avatar_url") or payload.get("avatar_path") or None
        return User(
            id=int(payload.get("id", 0)),
            email=payload.get("email", ""),
            role=(payload.get("role") or "user").lower(),
            username=payload.get("username") or "",
            avatar_path=avatar_url,
            token=token,
        )

    def _upload_avatar(self, avatar_src_path: str) -> User | None:
        if not self._token:
            return None
        with open(avatar_src_path, "rb") as f:
            files = {"file": f}
            r = requests.post(
                f"{self.base_url}/api/auth/avatar",
                headers=self._auth_headers(),
                files=files,
                timeout=30,
            )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}), self._token)

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
        user = self._user_from_payload(data.get("user", {}), token)
        if avatar_src_path:
            updated = self._upload_avatar(avatar_src_path)
            if updated:
                user = updated
        return user

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
        user = self._user_from_payload(data.get("user", {}), self._token)
        if avatar_src_path:
            updated = self._upload_avatar(avatar_src_path)
            if updated:
                user = updated
        return user

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

    def list_users(self) -> list[User]:
        if not self._token:
            raise RuntimeError("Not authenticated")
        r = requests.get(
            f"{self.base_url}/api/admin/users",
            headers=self._auth_headers(),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or []
        return [self._user_from_payload(item, self._token) for item in items]

    def set_role(self, user_id: int, role: str) -> User:
        if not self._token:
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/admin/users/{int(user_id)}/role",
            headers=self._auth_headers(),
            json={"role": role},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}), self._token)

    def logout(self) -> None:
        if not self._token:
            return
        try:
            requests.post(
                f"{self.base_url}/api/auth/logout",
                headers=self._auth_headers(),
                timeout=10,
            )
        finally:
            self._token = None

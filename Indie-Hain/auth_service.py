from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import uuid
import requests

from services.env import api_base


@dataclass
class User:
    id: int
    email: str
    role: str
    username: str
    avatar_path: Optional[str] = None
    access_token: Optional[str] = None


class PasswordResetRequired(Exception):
    pass


class AuthService:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or api_base()).rstrip("/")
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._device_id: Optional[str] = None

    def set_session(self, refresh_token: Optional[str], device_id: Optional[str]):
        self._refresh_token = refresh_token
        self._device_id = device_id

    def session_payload(self) -> dict:
        return {
            "refresh_token": self._refresh_token,
            "device_id": self._device_id,
        }

    def access_token(self) -> Optional[str]:
        return self._access_token

    def _ensure_device_id(self, device_id: Optional[str] = None) -> str:
        if device_id:
            self._device_id = device_id
        if not self._device_id:
            self._device_id = uuid.uuid4().hex
        return self._device_id

    def _auth_headers(self) -> dict:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_access(self) -> bool:
        if self._access_token:
            return True
        if self._refresh_token:
            return bool(self.refresh())
        return False

    def _user_from_payload(self, payload: dict) -> User:
        avatar_url = payload.get("avatar_url") or payload.get("avatar_path") or None
        return User(
            id=int(payload.get("id", 0)),
            email=payload.get("email", ""),
            role=(payload.get("role") or "user").lower(),
            username=payload.get("username") or "",
            avatar_path=avatar_url,
            access_token=self._access_token,
        )

    def _set_tokens(self, access_token: Optional[str], refresh_token: Optional[str]):
        if access_token:
            self._access_token = access_token
        if refresh_token:
            self._refresh_token = refresh_token

    def _upload_avatar(self, avatar_src_path: str) -> User | None:
        if not self._access_token:
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
        return self._user_from_payload(data.get("user", {}))

    def register(self, email: str, password: str, username: str, avatar_src_path: Optional[str] = None) -> User:
        device_id = self._ensure_device_id()
        r = requests.post(
            f"{self.base_url}/api/auth/register",
            json={"email": email, "password": password, "username": username, "device_id": device_id},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        self._set_tokens(data.get("access_token"), data.get("refresh_token"))
        user = self._user_from_payload(data.get("user", {}))
        if avatar_src_path:
            updated = self._upload_avatar(avatar_src_path)
            if updated:
                user = updated
        return user

    def login(self, identity: str, password: str) -> Optional[User]:
        device_id = self._ensure_device_id()
        payload = {"password": password, "device_id": device_id}
        if "@" in (identity or ""):
            payload["email"] = identity
        else:
            payload["username"] = identity
        r = requests.post(
            f"{self.base_url}/api/auth/login",
            json=payload,
            timeout=20,
        )
        if r.status_code == 403:
            try:
                detail = r.json().get("detail")
            except Exception:
                detail = ""
            if detail == "PASSWORD_RESET_REQUIRED":
                raise PasswordResetRequired()
        if r.status_code == 401:
            return None
        if r.status_code in (400, 422) and "username" in payload:
            r = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": identity, "password": password, "device_id": device_id},
                timeout=20,
            )
            if r.status_code == 403:
                try:
                    detail = r.json().get("detail")
                except Exception:
                    detail = ""
                if detail == "PASSWORD_RESET_REQUIRED":
                    raise PasswordResetRequired()
            if r.status_code == 401:
                return None
        r.raise_for_status()
        data = r.json()
        self._set_tokens(data.get("access_token"), data.get("refresh_token"))
        return self._user_from_payload(data.get("user", {}))

    def reset_password(self, identity: str, temp_password: str, new_password: str) -> None:
        payload = {"temp_password": temp_password, "new_password": new_password}
        if "@" in (identity or ""):
            payload["email"] = identity
        else:
            payload["username"] = identity
        r = requests.post(
            f"{self.base_url}/api/auth/reset-password",
            json=payload,
            timeout=20,
        )
        r.raise_for_status()

    def refresh(self) -> Optional[User]:
        if not self._refresh_token:
            return None
        device_id = self._ensure_device_id()
        r = requests.post(
            f"{self.base_url}/api/auth/refresh",
            json={"refresh_token": self._refresh_token, "device_id": device_id},
            timeout=20,
        )
        if r.status_code in (401, 403):
            self._access_token = None
            self._refresh_token = None
            return None
        r.raise_for_status()
        data = r.json()
        self._set_tokens(data.get("access_token"), data.get("refresh_token"))
        return self._user_from_payload(data.get("user", {}))

    def me(self) -> Optional[User]:
        if not self._access_token and self._refresh_token:
            refreshed = self.refresh()
            if refreshed:
                return refreshed
        r = requests.get(
            f"{self.base_url}/api/auth/me",
            headers=self._auth_headers(),
            timeout=20,
        )
        if r.status_code in (401, 403):
            if self._refresh_token:
                return self.refresh()
            self._access_token = None
            return None
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}))

    def update_profile(self, user_id: int, username: Optional[str] = None, avatar_src_path: Optional[str] = None) -> User:
        if not self._ensure_access():
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/auth/profile",
            headers=self._auth_headers(),
            json={"username": username},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        user = self._user_from_payload(data.get("user", {}))
        if avatar_src_path:
            updated = self._upload_avatar(avatar_src_path)
            if updated:
                user = updated
        return user

    def upgrade_to_dev(self, user_id: int) -> User:
        if not self._ensure_access():
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/auth/upgrade/dev",
            headers=self._auth_headers(),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}))

    def list_users(self) -> list[User]:
        if not self._ensure_access():
            raise RuntimeError("Not authenticated")
        r = requests.get(
            f"{self.base_url}/api/admin/users",
            headers=self._auth_headers(),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or []
        return [self._user_from_payload(item) for item in items]

    def set_role(self, user_id: int, role: str) -> User:
        if not self._ensure_access():
            raise RuntimeError("Not authenticated")
        r = requests.post(
            f"{self.base_url}/api/admin/users/{int(user_id)}/role",
            headers=self._auth_headers(),
            json={"role": role},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return self._user_from_payload(data.get("user", {}))

    def logout(self) -> None:
        if not self._access_token and not self._refresh_token:
            return
        try:
            payload = {"refresh_token": self._refresh_token} if self._refresh_token else {}
            requests.post(
                f"{self.base_url}/api/auth/logout",
                headers=self._auth_headers(),
                json=payload,
                timeout=10,
            )
        finally:
            self._access_token = None
            self._refresh_token = None

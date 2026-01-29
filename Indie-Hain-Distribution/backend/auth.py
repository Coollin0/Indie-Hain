# backend/auth.py
from __future__ import annotations

import hmac
import os
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta
from fastapi import Depends, Header, HTTPException
import jwt

from .db import get_db


ACCESS_TTL_MINUTES = 15
REFRESH_TTL_DAYS = 30
JWT_ALG = "HS256"


def _require_secret(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} is required")
    return val


JWT_SECRET = _require_secret("JWT_SECRET")
REFRESH_SECRET = os.environ.get("REFRESH_SECRET") or JWT_SECRET


def _now() -> datetime:
    return datetime.utcnow()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000)
    return f"{salt.hex()}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    new = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000).hex()
    return hmac.compare_digest(new, dk_hex)


def _hash_refresh_secret(secret_part: str) -> str:
    return hmac.new(REFRESH_SECRET.encode("utf-8"), secret_part.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_refresh_token(session_id: str, secret_part: str) -> str:
    return f"{session_id}.{secret_part}"


def _parse_refresh_token(refresh_token: str) -> tuple[str, str] | None:
    if not refresh_token or "." not in refresh_token:
        return None
    session_id, secret_part = refresh_token.split(".", 1)
    if not session_id or not secret_part:
        return None
    return session_id, secret_part


def _session_row(session_id: str):
    with get_db() as db:
        return db.execute(
            """
            SELECT id, user_id, device_id, refresh_token_hash, refresh_expires_at, revoked_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()


def _session_active(session_id: str) -> bool:
    row = _session_row(session_id)
    if not row:
        return False
    if row["revoked_at"]:
        return False
    if row["refresh_expires_at"]:
        try:
            if _now() >= datetime.fromisoformat(row["refresh_expires_at"]):
                return False
        except ValueError:
            return False
    return True


def _user_by_id(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def _user_by_email(email: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT id, email, role, username, avatar_url, password_hash,
                   temp_password_hash, force_password_reset
            FROM users WHERE email = ?
            """,
            (email,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
        "password_hash": row["password_hash"],
        "temp_password_hash": row["temp_password_hash"],
        "force_password_reset": int(row["force_password_reset"] or 0),
    }


def _user_by_username(username: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT id, email, role, username, avatar_url, password_hash,
                   temp_password_hash, force_password_reset
            FROM users WHERE lower(username) = lower(?)
            """,
            (username,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
        "password_hash": row["password_hash"],
        "temp_password_hash": row["temp_password_hash"],
        "force_password_reset": int(row["force_password_reset"] or 0),
    }

def _issue_access_token(user: dict, session_id: str, device_id: str | None) -> str:
    now = _now()
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "sid": session_id,
        "device_id": device_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TTL_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid token") from exc


def session_id_from_access_token(token: str) -> str | None:
    try:
        claims = _decode_access_token(token)
    except HTTPException:
        return None
    return claims.get("sid")


def _create_session(user_id: int, device_id: str | None) -> tuple[str, str]:
    session_id = uuid.uuid4().hex
    secret_part = secrets.token_urlsafe(32)
    refresh_token_hash = _hash_refresh_secret(secret_part)
    now = _now()
    refresh_expires_at = now + timedelta(days=REFRESH_TTL_DAYS)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO sessions(id, user_id, device_id, refresh_token_hash, created_at, last_used_at, refresh_expires_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                session_id,
                int(user_id),
                device_id,
                refresh_token_hash,
                now.isoformat(),
                now.isoformat(),
                refresh_expires_at.isoformat(),
            ),
        )
        db.commit()
    return session_id, _build_refresh_token(session_id, secret_part)


def issue_tokens(user: dict, device_id: str | None) -> dict:
    session_id, refresh_token = _create_session(user["id"], device_id)
    access_token = _issue_access_token(user, session_id, device_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user,
    }


def refresh_tokens(refresh_token: str, device_id: str | None) -> dict:
    parsed = _parse_refresh_token(refresh_token)
    if not parsed:
        raise HTTPException(401, "Invalid refresh token")
    session_id, secret_part = parsed
    row = _session_row(session_id)
    if not row or row["revoked_at"]:
        raise HTTPException(401, "Invalid refresh token")
    if row["refresh_expires_at"]:
        try:
            if _now() >= datetime.fromisoformat(row["refresh_expires_at"]):
                raise HTTPException(401, "Refresh token expired")
        except ValueError as exc:
            raise HTTPException(401, "Refresh token expired") from exc
    if device_id and row["device_id"] and device_id != row["device_id"]:
        raise HTTPException(401, "Device mismatch")

    expected_hash = _hash_refresh_secret(secret_part)
    if not hmac.compare_digest(expected_hash, row["refresh_token_hash"]):
        with get_db() as db:
            db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ?",
                (_now().isoformat(), session_id),
            )
            db.commit()
        raise HTTPException(401, "Refresh reuse detected")

    user = _user_by_id(row["user_id"])
    if not user:
        raise HTTPException(401, "Invalid refresh token")

    new_secret = secrets.token_urlsafe(32)
    new_hash = _hash_refresh_secret(new_secret)
    now = _now()
    refresh_expires_at = now + timedelta(days=REFRESH_TTL_DAYS)
    with get_db() as db:
        db.execute(
            """
            UPDATE sessions
            SET refresh_token_hash = ?, last_used_at = ?, refresh_expires_at = ?
            WHERE id = ?
            """,
            (new_hash, now.isoformat(), refresh_expires_at.isoformat(), session_id),
        )
        db.commit()

    access_token = _issue_access_token(user, session_id, row["device_id"])
    return {
        "access_token": access_token,
        "refresh_token": _build_refresh_token(session_id, new_secret),
        "user": user,
    }


def revoke_session_by_id(session_id: str) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ?",
            (_now().isoformat(), session_id),
        )
        db.commit()


def revoke_sessions_for_user(user_id: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ?",
            (_now().isoformat(), int(user_id)),
        )
        db.commit()


def revoke_session_by_refresh(refresh_token: str) -> None:
    parsed = _parse_refresh_token(refresh_token)
    if not parsed:
        return
    session_id, _ = parsed
    revoke_session_by_id(session_id)


def create_user(email: str, password: str, username: str) -> dict:
    email = email.strip().lower()
    username = username.strip()
    if not email or not password or not username:
        raise HTTPException(400, "email, password, username required")
    ph = _hash_password(password)
    with get_db() as db:
        try:
            db.execute(
                """
                INSERT INTO users(email, password_hash, role, username, created_at)
                VALUES(?, ?, 'user', ?, ?)
                """,
                (email, ph, username, _now().isoformat()),
            )
            db.commit()
        except Exception as exc:
            msg = str(exc).lower()
            if "unique" in msg or "constraint" in msg:
                raise HTTPException(409, "email already exists") from exc
            raise
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def authenticate(email: str, password: str) -> dict | None:
    email = email.strip().lower()
    user = _user_by_email(email)
    if not user:
        return None
    if user.get("force_password_reset"):
        tmp_hash = user.get("temp_password_hash")
        if tmp_hash and _verify_password(password, tmp_hash):
            return {
                "id": int(user["id"]),
                "email": user["email"],
                "role": user["role"],
                "username": user["username"],
                "avatar_url": user["avatar_url"],
                "must_reset_password": True,
            }
        return None
    if _verify_password(password, user["password_hash"]):
        return {
            "id": int(user["id"]),
            "email": user["email"],
            "role": user["role"],
            "username": user["username"],
            "avatar_url": user["avatar_url"],
        }
    return None


def authenticate_username(username: str, password: str) -> dict | None:
    username = username.strip()
    user = _user_by_username(username)
    if not user:
        return None
    if user.get("force_password_reset"):
        tmp_hash = user.get("temp_password_hash")
        if tmp_hash and _verify_password(password, tmp_hash):
            return {
                "id": int(user["id"]),
                "email": user["email"],
                "role": user["role"],
                "username": user["username"],
                "avatar_url": user["avatar_url"],
                "must_reset_password": True,
            }
        return None
    if _verify_password(password, user["password_hash"]):
        return {
            "id": int(user["id"]),
            "email": user["email"],
            "role": user["role"],
            "username": user["username"],
            "avatar_url": user["avatar_url"],
        }
    return None


def update_username(user_id: int, username: str) -> dict:
    username = username.strip()
    if not username:
        raise HTTPException(400, "username required")
    with get_db() as db:
        db.execute(
            "UPDATE users SET username = ? WHERE id = ?",
            (username, int(user_id)),
        )
        db.commit()
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def set_role_by_email(email: str, role: str) -> dict:
    email = email.strip().lower()
    with get_db() as db:
        db.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
        db.commit()
    user = _user_by_id_by_email(email)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _user_by_id_by_email(email: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def set_role_by_id(user_id: int, role: str, revoke_sessions: bool = False) -> dict:
    with get_db() as db:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, int(user_id)))
        db.commit()
    if revoke_sessions:
        revoke_sessions_for_user(user_id)
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def update_avatar_url(user_id: int, avatar_url: str) -> dict:
    with get_db() as db:
        db.execute(
            "UPDATE users SET avatar_url = ? WHERE id = ?",
            (avatar_url, int(user_id)),
        )
        db.commit()
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def set_user_password(user_id: int, new_password: str) -> dict:
    if not new_password:
        raise HTTPException(400, "password required")
    ph = _hash_password(new_password)
    with get_db() as db:
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (ph, int(user_id)),
        )
        db.commit()
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def set_temp_password(user_id: int, temp_password: str) -> dict:
    if not temp_password:
        raise HTTPException(400, "temp password required")
    ph = _hash_password(temp_password)
    with get_db() as db:
        db.execute(
            """
            UPDATE users
            SET temp_password_hash = ?, temp_password_plain = NULL, force_password_reset = 1
            WHERE id = ?
            """,
            (ph, int(user_id)),
        )
        db.commit()
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def clear_temp_password(user_id: int) -> dict:
    with get_db() as db:
        db.execute(
            """
            UPDATE users
            SET temp_password_hash = NULL, temp_password_plain = NULL, force_password_reset = 0
            WHERE id = ?
            """,
            (int(user_id),),
        )
        db.commit()
    user = _user_by_id(user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


def verify_temp_password(user_id: int, temp_password: str) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT temp_password_hash, force_password_reset FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row or not row["force_password_reset"] or not row["temp_password_hash"]:
        return False
    return _verify_password(temp_password, row["temp_password_hash"])


def get_user_from_headers(
    authorization: str | None = Header(default=None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_access_token(token)
    session_id = claims.get("sid")
    if not session_id or not _session_active(session_id):
        raise HTTPException(401, "Invalid session")
    user = _user_by_id(int(claims.get("sub", 0)))
    if not user:
        raise HTTPException(401, "Invalid token")
    user["token"] = token
    user["session_id"] = session_id
    user["role"] = (user.get("role") or "user").lower()
    return user


def require_user(user: dict = Depends(get_user_from_headers)):
    if user.get("id", 0) <= 0:
        raise HTTPException(401, "Authentication required")
    return {
        "user_id": int(user["id"]),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "username": user.get("username", ""),
        "avatar_url": user.get("avatar_url", ""),
        "token": user.get("token"),
        "session_id": user.get("session_id"),
    }


def require_dev(user: dict = Depends(require_user)):
    if user.get("role") not in ("dev", "admin"):
        raise HTTPException(403, "Developer role required")
    return user


def require_admin(user: dict = Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    return user

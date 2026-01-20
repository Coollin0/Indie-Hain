# backend/auth.py
from __future__ import annotations

import hmac
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import Depends, Header, HTTPException

from .db import get_db


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


def _create_session(user_id: int, ttl_days: int = 7) -> str:
    token = secrets.token_hex(32)
    now = datetime.utcnow()
    expires = now + timedelta(days=int(ttl_days))
    with get_db() as db:
        db.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?,?,?,?)",
            (token, int(user_id), now.isoformat(), expires.isoformat()),
        )
        db.commit()
    return token


def _user_by_token(token: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT u.id, u.email, u.role, u.username, u.avatar_url, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    expires_at = row["expires_at"]
    if expires_at:
        try:
            if datetime.utcnow() >= datetime.fromisoformat(expires_at):
                return None
        except Exception:
            return None
    return {
        "user_id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def _user_by_email(email: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, email, role, username, avatar_url, password_hash FROM users WHERE email = ?",
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
    }


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
                (email, ph, username, datetime.utcnow().isoformat()),
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
    if _verify_password(password, user["password_hash"]):
        return {
            "id": int(user["id"]),
            "email": user["email"],
            "role": user["role"],
            "username": user["username"],
            "avatar_url": user["avatar_url"],
        }
    return None


def issue_token(user_id: int, ttl_days: int = 7) -> str:
    return _create_session(user_id, ttl_days=ttl_days)


def revoke_token(token: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()


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
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def set_role_by_email(email: str, role: str) -> dict:
    email = email.strip().lower()
    with get_db() as db:
        db.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
        db.commit()
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def set_role_by_id(user_id: int, role: str) -> dict:
    with get_db() as db:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, int(user_id)))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (int(user_id),))
        db.commit()
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def update_avatar_url(user_id: int, avatar_url: str) -> dict:
    with get_db() as db:
        db.execute(
            "UPDATE users SET avatar_url = ? WHERE id = ?",
            (avatar_url, int(user_id)),
        )
        db.commit()
        row = db.execute(
            "SELECT id, email, role, username, avatar_url FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "role": (row["role"] or "user").lower(),
        "username": row["username"] or "",
        "avatar_url": row["avatar_url"] or "",
    }


def get_user_from_headers(
    authorization: str | None = Header(default=None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.split(" ", 1)[1].strip()
    user = _user_by_token(token)
    if not user:
        raise HTTPException(401, "Invalid token")
    user["token"] = token
    return user


def require_user(user: dict = Depends(get_user_from_headers)):
    if user.get("user_id", 0) <= 0:
        raise HTTPException(401, "Authentication required")
    return user


def require_dev(user: dict = Depends(get_user_from_headers)):
    if user.get("user_id", 0) <= 0:
        raise HTTPException(401, "Authentication required")
    if user.get("role") not in ("dev", "admin"):
        raise HTTPException(403, "Developer role required")
    return user


def require_admin(user: dict = Depends(get_user_from_headers)):
    if user.get("user_id", 0) <= 0:
        raise HTTPException(401, "Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    return user

# backend/auth.py
from fastapi import Depends, Header, HTTPException

def get_user_from_headers(
    x_user_id: str = Header(default="0"),
    x_role: str = Header(default="user"),
):
    try:
        uid = int(x_user_id)
    except ValueError:
        uid = 0
    return {"user_id": uid, "role": (x_role or "user").lower()}

def require_user(user: dict = Depends(get_user_from_headers)):
    if user["user_id"] <= 0:
        raise HTTPException(401, "Authentication required")
    return user

def require_dev(user: dict = Depends(get_user_from_headers)):
    if user["user_id"] <= 0:
        raise HTTPException(401, "Authentication required")
    if user["role"] not in ("dev", "admin"):
        raise HTTPException(403, "Developer role required")
    return user

def require_admin(user: dict = Depends(get_user_from_headers)):
    if user["user_id"] <= 0:
        raise HTTPException(401, "Authentication required")
    if user["role"] != "admin":
        raise HTTPException(403, "Admin role required")
    return user

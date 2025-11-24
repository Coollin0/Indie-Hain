# backend/auth.py
from fastapi import Header, HTTPException
from typing import Optional

async def require_user(
    x_user_id: Optional[int] = Header(None),
    x_role: Optional[str] = Header("user"),
):
    if x_user_id is None:
        raise HTTPException(401, "Unauthorized")
    return {"user_id": int(x_user_id), "role": x_role}

async def require_dev(
    x_user_id: Optional[int] = Header(None),
    x_role: Optional[str] = Header("user"),
):
    if x_user_id is None or x_role not in ("dev", "admin"):
        raise HTTPException(403, "Developer role required")
    return {"user_id": int(x_user_id), "role": x_role}

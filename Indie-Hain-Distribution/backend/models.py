from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional


class AuthRegister(BaseModel):
    email: str
    password: str
    username: str
    device_id: Optional[str] = None


class AuthLogin(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str
    device_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_identity(self):
        if not self.email and not self.username:
            raise ValueError("email or username required")
        return self


class AuthProfileUpdate(BaseModel):
    username: Optional[str] = None


class AuthBootstrap(BaseModel):
    email: str
    secret: str


class AuthRefresh(BaseModel):
    refresh_token: str
    device_id: Optional[str] = None


class AuthLogout(BaseModel):
    refresh_token: Optional[str] = None


class AdminRoleUpdate(BaseModel):
    role: str


class AdminPasswordReset(BaseModel):
    password: Optional[str] = None


class AppCreate(BaseModel):
    slug: str
    title: str


class BuildCreate(BaseModel):
    app_id: int
    version: str
    platform: Literal["windows", "linux", "mac"]
    channel: Literal["stable", "beta"] = "stable"


class MissingChunksRequest(BaseModel):
    hashes: List[str] = Field(default_factory=list)


class ChunkInfo(BaseModel):
    offset: int
    size: int
    sha256: str


class FileEntry(BaseModel):
    path: str
    size: int
    sha256: str
    chunks: List[ChunkInfo]


class Manifest(BaseModel):
    app: str
    version: str
    platform: str
    channel: str
    total_size: int
    files: List[FileEntry]
    chunk_base: str
    signature: Optional[str] = None


class AppMetaUpdate(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    sale_percent: Optional[float] = None


class PurchaseReport(BaseModel):
    """Launcher meldet Käufe an den Backend-Server."""

    app_id: int
    price: float  # Preis, den der User gezahlt hat (nach Rabatt)

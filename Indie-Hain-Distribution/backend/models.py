from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class AppCreate(BaseModel):
    slug: str
    title: str

class BuildCreate(BaseModel):
    app_id: int
    version: str
    platform: Literal["windows","linux","mac"]
    channel: Literal["stable","beta"] = "stable"

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
"""Request models shared by API endpoints."""

from pydantic import BaseModel, Field


class NoteBody(BaseModel):
    text: str = ""


class HiddenBody(BaseModel):
    hidden: bool


class ProjectNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DismissalBody(BaseModel):
    project_id: str
    path_prefix: str


class FreezeBody(BaseModel):
    session_id: str
    from_seq: int | None = None
    to_seq: int | None = None


class CasePatch(BaseModel):
    verdict: str | None = None
    note: str | None = None

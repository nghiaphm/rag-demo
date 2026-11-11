"""Message file references are distinct from retrieval scope and citations."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.documents.models import _canonical_uuid


class AttachmentReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    version_id: str

    _ids = field_validator("document_id", "version_id")(_canonical_uuid)


class MessageAttachment(AttachmentReference):
    file_name: str = Field(min_length=1, max_length=255)

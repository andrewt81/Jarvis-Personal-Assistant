from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from jarvis.api.auth import current_user
from jarvis.auth.models import AuthenticatedUser
from jarvis.documents.models import Document
from jarvis.documents.service import (
    MAX_DOCUMENT_BYTES,
    DocumentNotFoundError,
    DocumentService,
    InvalidDocumentError,
)
from jarvis.households.service import HouseholdNotFoundError, HouseholdPermissionError

router = APIRouter(prefix="/api/v1/households/{household_id}/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: UUID
    household_id: UUID
    person_id: UUID | None
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


def _service(request: Request) -> DocumentService:
    return request.app.state.document_service


def _response(document: Document) -> DocumentResponse:
    if document.created_at is None:
        raise RuntimeError("Persisted document is missing its creation timestamp")
    return DocumentResponse(
        id=document.id,
        household_id=document.household_id,
        person_id=document.person_id,
        original_filename=document.original_filename,
        media_type=document.media_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256.hex(),
        created_at=document.created_at,
    )


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, (HouseholdNotFoundError, DocumentNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, HouseholdPermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    household_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[DocumentResponse]:
    try:
        values = await _service(request).list(user.id, household_id)
    except HouseholdNotFoundError as error:
        raise _translate(error) from error
    return [_response(value) for value in values]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    household_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    filename: Annotated[str, Header(alias="X-Filename")],
    person_id: Annotated[UUID | None, Header(alias="X-Person-Id")] = None,
) -> DocumentResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    content = await request.body()
    try:
        value = await _service(request).upload(
            user.id,
            household_id,
            filename=filename,
            media_type=request.headers.get("content-type", "application/octet-stream").split(";")[
                0
            ],
            content=content,
            person_id=person_id,
        )
    except (HouseholdNotFoundError, HouseholdPermissionError, InvalidDocumentError) as error:
        raise _translate(error) from error
    return _response(value)


@router.get("/{document_id}/content", response_class=Response)
async def download_document(
    household_id: UUID,
    document_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> Response:
    try:
        document, content = await _service(request).download(user.id, household_id, document_id)
    except (HouseholdNotFoundError, DocumentNotFoundError) as error:
        raise _translate(error) from error
    disposition = f"attachment; filename*=UTF-8''{quote(document.original_filename)}"
    return Response(
        content=content,
        media_type=document.media_type,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    household_id: UUID,
    document_id: UUID,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> Response:
    try:
        await _service(request).delete(user.id, household_id, document_id)
    except (HouseholdNotFoundError, HouseholdPermissionError, DocumentNotFoundError) as error:
        raise _translate(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

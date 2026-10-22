from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from jarvis.auth.models import AuthenticatedUser, TokenPair
from jarvis.auth.service import AuthenticationError, AuthService, InvalidSessionError

router = APIRouter(prefix="/api/v1", tags=["authentication"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class UserResponse(BaseModel):
    id: UUID
    email: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token scheme, not a credential
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: UserResponse


def _service(request: Request) -> AuthService:
    return request.app.state.auth_service


def _bearer_token(authorization: str | None) -> str:
    scheme, separator, token = (authorization or "").partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not token.strip():
        raise _unauthorized()
    return token.strip()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
        user=UserResponse(id=pair.user.id, email=pair.user.email),
    )


async def current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    token = _bearer_token(authorization)
    try:
        return await _service(request).authenticate(token)
    except InvalidSessionError as error:
        raise _unauthorized() from error


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    try:
        pair = await _service(request).login(payload.email, payload.password)
    except AuthenticationError as error:
        raise _unauthorized() from error
    return _token_response(pair)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request) -> TokenResponse:
    try:
        pair = await _service(request).refresh(payload.refresh_token)
    except InvalidSessionError as error:
        raise _unauthorized() from error
    return _token_response(pair)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    token = _bearer_token(authorization)
    await _service(request).logout(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UserResponse:
    user = await current_user(request, authorization)
    return UserResponse(id=user.id, email=user.email)

"""WebAuthn (Passkeys) маршрути: реєстрація та авторизація."""

import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import APP_ORIGIN, COOKIE_NAME, COOKIE_SECURE, JWT_TTL_SECONDS, RP_ID
from ..db import get_session
from ..deps import get_current_user
from ..models import User, UserCredential
from ..schemas import UserOut
from ..security import create_token
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

router = APIRouter(prefix="/api/webauthn", tags=["webauthn"])


def _parse_registration(body: dict) -> RegistrationCredential:
    resp = body["response"]
    return RegistrationCredential(
        id=body["id"],
        raw_id=base64url_to_bytes(body.get("rawId") or body["id"]),
        response=AuthenticatorAttestationResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            attestation_object=base64url_to_bytes(resp["attestationObject"]),
            transports=resp.get("transports"),
        ),
        type=body.get("type", "public-key"),
    )


def _parse_authentication(body: dict) -> AuthenticationCredential:
    resp = body["response"]
    user_handle = resp.get("userHandle")
    return AuthenticationCredential(
        id=body["id"],
        raw_id=base64url_to_bytes(body.get("rawId") or body["id"]),
        response=AuthenticatorAssertionResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
            signature=base64url_to_bytes(resp["signature"]),
            user_handle=base64url_to_bytes(user_handle) if user_handle else None,
        ),
        type=body.get("type", "public-key"),
    )


# In-memory challenge stores (username → (challenge, timestamp) for reg; session_id → ... for auth)
_reg_challenges: dict[str, tuple[bytes, float, str]] = {}  # username → (challenge, ts, cred_name)
_auth_challenges: dict[str, tuple[bytes, float]] = {}  # session_id → (challenge, ts)
CHALLENGE_TTL = 300  # 5 хвилин


def _clean(store: dict) -> None:
    now = time.time()
    for k in [k for k, v in store.items() if now - v[1] > CHALLENGE_TTL]:
        del store[k]


# ── Registration ──────────────────────────────────────────────────────────────


class RegisterBeginBody(BaseModel):
    name: str = "Ключ"


@router.post("/register/begin")
async def register_begin(
    body: RegisterBeginBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.username == user["username"]))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    existing = await session.execute(select(UserCredential).where(UserCredential.user_id == db_user.id))
    exclude = [PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing.scalars().all()]

    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name="JAAM Admin",
        user_id=str(db_user.id).encode(),
        user_name=db_user.username,
        user_display_name=db_user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude,
    )

    _clean(_reg_challenges)
    _reg_challenges[db_user.username] = (options.challenge, time.time(), body.name)

    return json.loads(options_to_json(options))


@router.post("/register/complete")
async def register_complete(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    entry = _reg_challenges.pop(user["username"], None)
    if not entry:
        raise HTTPException(status_code=400, detail="Немає активного запиту реєстрації")
    challenge, ts, cred_name = entry
    if time.time() - ts > CHALLENGE_TTL:
        raise HTTPException(status_code=400, detail="Час реєстрації вийшов")

    try:
        verification = verify_registration_response(
            credential=_parse_registration(body),
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=APP_ORIGIN,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Помилка верифікації: {exc}") from exc

    result = await session.execute(select(User).where(User.username == user["username"]))
    db_user = result.scalar_one()

    cred = UserCredential(
        user_id=db_user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        name=cred_name,
    )
    session.add(cred)
    await session.commit()
    await session.refresh(cred)

    return {"ok": True, "id": cred.id, "name": cred.name}


# ── Authentication ────────────────────────────────────────────────────────────


class AuthCompleteBody(BaseModel):
    session_id: str
    credential: dict


@router.post("/auth/begin")
async def auth_begin():
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    session_id = secrets.token_urlsafe(32)
    _clean(_auth_challenges)
    _auth_challenges[session_id] = (options.challenge, time.time())

    return {"session_id": session_id, "options": json.loads(options_to_json(options))}


@router.post("/auth/complete", response_model=UserOut)
async def auth_complete(
    body: AuthCompleteBody,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    entry = _auth_challenges.pop(body.session_id, None)
    if not entry:
        raise HTTPException(status_code=400, detail="Невідомий або прострочений сеанс")
    challenge, ts = entry
    if time.time() - ts > CHALLENGE_TTL:
        raise HTTPException(status_code=400, detail="Час авторизації вийшов")

    try:
        cred_id_bytes = base64url_to_bytes(body.credential.get("id") or body.credential.get("rawId", ""))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Невірний credential id") from exc

    result = await session.execute(select(UserCredential).where(UserCredential.credential_id == cred_id_bytes))
    db_cred = result.scalar_one_or_none()
    if not db_cred:
        raise HTTPException(status_code=401, detail="Ключ не знайдено")

    try:
        verification = verify_authentication_response(
            credential=_parse_authentication(body.credential),
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=APP_ORIGIN,
            credential_public_key=db_cred.public_key,
            credential_current_sign_count=db_cred.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Невірний ключ: {exc}") from exc

    db_cred.sign_count = verification.new_sign_count
    db_cred.last_used_at = datetime.now(timezone.utc)
    await session.commit()

    user_result = await session.execute(select(User).where(User.id == db_cred.user_id))
    db_user = user_result.scalar_one()

    token = create_token(db_user.username, db_user.role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )
    return UserOut(username=db_user.username, role=db_user.role)


# ── Credential management ─────────────────────────────────────────────────────


@router.get("/credentials")
async def list_credentials(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result_user = await session.execute(select(User).where(User.username == user["username"]))
    db_user = result_user.scalar_one_or_none()
    if not db_user:
        return []

    result = await session.execute(select(UserCredential).where(UserCredential.user_id == db_user.id))
    return [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at.isoformat(),
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        }
        for c in result.scalars().all()
    ]


@router.delete("/credentials/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    cred_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result_user = await session.execute(select(User).where(User.username == user["username"]))
    db_user = result_user.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    result = await session.execute(
        select(UserCredential).where(
            UserCredential.id == cred_id,
            UserCredential.user_id == db_user.id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Ключ не знайдено")

    await session.delete(cred)
    await session.commit()

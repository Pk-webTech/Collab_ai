import asyncio
import logging
import os

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("app.auth")

# How long the fetched JWKS key set is reused before being re-downloaded.
# Supabase rotates signing keys rarely, and PyJWKClient re-fetches on its own
# when it sees an unknown key id, so a long lifespan is safe and means fewer
# network calls in the middle of requests.
JWKS_CACHE_SECONDS = 3600


class CurrentUser(BaseModel):
    id: str
    email: str | None = None


_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """
    Since May 2025, new Supabase projects sign JWTs asymmetrically (ES256
    by default) rather than with the old shared HS256 secret.

    Supabase's API gateway requires an `apikey` header on this request.
    It also requires a standard `User-Agent` to avoid being blocked by
    Edge network bot detection (returning a 404).
    """
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.environ.get("SUPABASE_URL")
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not set")

        # Safely extract the base URL (removes /rest/v1/ or /auth/v1/ if present)
        base_url = supabase_url.split("/rest/v1")[0].split("/auth/v1")[0].rstrip("/")
        jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"

        anon_key = os.environ.get("SUPABASE_ANON_KEY")
        if not anon_key:
            logger.warning("SUPABASE_ANON_KEY is not set -- the JWKS fetch may be rejected.")

        # MUST include User-Agent to bypass Supabase's 404 bot detection for Python requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        if anon_key:
            headers["apikey"] = anon_key

        _jwks_client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=JWKS_CACHE_SECONDS,
            headers=headers,
        )
    return _jwks_client


def _legacy_secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET")


def _verify_with_jwks(token: str) -> dict:
    """Synchronous: may download the key set over HTTP. Always call via
    asyncio.to_thread so a key refresh can't freeze the event loop (and with
    it every other in-flight request, including streaming replies)."""
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )


async def warm_jwks() -> None:
    """Optional: call once at startup so the first request doesn't pay for
    the key download. Failures are only logged."""
    try:
        await asyncio.to_thread(lambda: _get_jwks_client().get_jwk_set())
    except Exception as e:
        logger.warning("jwks_warmup_failed error=%s: %s", type(e).__name__, e)


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """
    Verifies the Supabase-issued JWT sent by the frontend as:
      Authorization: Bearer <access_token>

    Uses the token's own header to pick the path: HS256 tokens (older
    projects) go straight to the shared-secret check, everything else is
    verified against the project's JWKS. Previously every HS256 token first
    went through a JWKS attempt that could never succeed.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]

    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    payload = None
    expired = False
    last_error: Exception | None = None

    if alg != "HS256":
        try:
            payload = await asyncio.to_thread(_verify_with_jwks, token)
        except jwt.ExpiredSignatureError as e:
            expired = True
            last_error = e
        except Exception as e:
            last_error = e
            logger.warning("jwks_verification_failed error=%s: %s", type(e).__name__, e)

    if payload is None and not expired and _legacy_secret():
        try:
            payload = jwt.decode(
                token,
                _legacy_secret(),
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError as e:
            expired = True
            last_error = e
        except Exception as e:
            last_error = e
            if alg == "HS256":
                logger.warning("legacy_hs256_verification_failed error=%s: %s", type(e).__name__, e)

    if payload is None:
        if expired:
            raise HTTPException(status_code=401, detail="Session expired, please log in again")
        logger.warning(
            "auth_failed alg=%s last_error=%s: %s",
            alg,
            type(last_error).__name__ if last_error else None,
            last_error,
        )
        raise HTTPException(status_code=401, detail="Invalid auth token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return CurrentUser(id=user_id, email=payload.get("email"))
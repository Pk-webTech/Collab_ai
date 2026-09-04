import logging
import os
import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("app.auth")


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
        base_url = supabase_url.split('/rest/v1')[0].split('/auth/v1')[0].rstrip('/')
        
        # FIX: Point to /auth/v1/ instead of /rest/v1/
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

        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, headers=headers)
    return _jwks_client


def _legacy_secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET")


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """
    Verifies the Supabase-issued JWT sent by the frontend as:
      Authorization: Bearer <access_token>

    Tries the modern asymmetric (JWKS) verification first -- this is what
    current Supabase projects use by default. Falls back to the legacy
    HS256 shared-secret check for older projects that haven't migrated.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]

    payload = None
    expired = False
    last_error: Exception | None = None

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError as e:
        expired = True
        last_error = e
    except Exception as e:
        last_error = e
        logger.warning("jwks_verification_failed error=%s: %s", type(e).__name__, e)

    if payload is None and _legacy_secret():
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
            if not expired:
                last_error = e
            logger.warning("legacy_hs256_verification_failed error=%s: %s", type(e).__name__, e)

    if payload is None:
        if expired:
            raise HTTPException(status_code=401, detail="Session expired, please log in again")
        logger.warning(
            "auth_failed both_paths_exhausted last_error=%s: %s",
            type(last_error).__name__ if last_error else None,
            last_error,
        )
        raise HTTPException(status_code=401, detail="Invalid auth token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return CurrentUser(id=user_id, email=payload.get("email"))
import os
import jwt
from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class CurrentUser(BaseModel):
    id: str
    email: str | None = None


def _jwt_secret() -> str:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET is not set")
    return secret


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """
    Verifies the Supabase-issued JWT sent by the frontend as:
      Authorization: Bearer <access_token>

    Supabase signs project JWTs with the project's JWT secret (HS256),
    so we can verify locally without an extra network call.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return CurrentUser(id=user_id, email=payload.get("email"))

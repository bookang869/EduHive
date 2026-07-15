from __future__ import annotations
import os
import jwt  # PyJWT

_secret = os.environ.get("NEXTAUTH_SECRET", "")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret, algorithms=["HS256"])

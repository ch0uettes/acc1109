"""Server entry codes, admin PINs, and the signed access tokens the API
issues once both check out.

Stateless on purpose: Vercel runs the API as short-lived serverless
functions with no shared memory, so a token carries everything needed to
verify it (HMAC-signed with SESSION_SECRET) instead of pointing at a
server-side session row. Each token also embeds a short fingerprint of the
server's current entry-code hash and the member's current PIN hash, so
changing the entry code or resetting a PIN invalidates every token issued
under the old value without needing a revocation list.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from app.config import settings
from app.utils.exceptions import AuthenticationError

_PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 30 * 24 * 3600

# Local dev/tests only - _secret() refuses to fall back to this on Vercel,
# where a guessable signing key would let anyone mint an Owner token.
_DEV_FALLBACK_SECRET = "local-dev-only-insecure-session-secret"


def hash_secret(raw: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_secret(raw: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _algo, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", raw.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


def fingerprint(stored_hash: str | None) -> str:
    """Short, non-reversible tag of a stored hash (or of "nothing set")
    - what a token pins itself to, see the module docstring."""
    return hashlib.sha256((stored_hash or "").encode()).hexdigest()[:16]


@dataclass(frozen=True)
class TokenClaims:
    server_id: int
    member_id: int
    code_fingerprint: str
    pin_fingerprint: str


def _secret() -> bytes:
    if settings.session_secret:
        return settings.session_secret.encode()
    if os.environ.get("VERCEL"):
        raise AuthenticationError("SESSION_SECRET 환경변수가 설정되지 않아 로그인할 수 없습니다 (서버 설정 오류)")
    return _DEV_FALLBACK_SECRET.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(claims: TokenClaims) -> str:
    payload = {
        "s": claims.server_id,
        "m": claims.member_id,
        "c": claims.code_fingerprint,
        "p": claims.pin_fingerprint,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def read_token(token: str) -> TokenClaims:
    try:
        body, signature = token.split(".")
    except ValueError:
        raise AuthenticationError("잘못된 접속 토큰입니다") from None
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("잘못된 접속 토큰입니다")
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        raise AuthenticationError("잘못된 접속 토큰입니다") from None
    if payload.get("exp", 0) < time.time():
        raise AuthenticationError("접속이 만료되었습니다. 다시 입장해주세요")
    return TokenClaims(
        server_id=payload["s"],
        member_id=payload["m"],
        code_fingerprint=payload["c"],
        pin_fingerprint=payload["p"],
    )

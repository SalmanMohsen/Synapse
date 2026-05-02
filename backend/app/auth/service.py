from datetime import timedelta
import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository import UserRepository
from app.auth.schemas import LoginRequest, RegisterRequest, UserRead
from app.auth.utils.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.utils.password import hash_password, verify_password
from app.config import get_settings

settings = get_settings()

class AuthService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db # Save the session reference to commit transactions
        self.repo = UserRepository(db)
        self.redis = redis

    # ------------------------------------------------------------------ #
    # Email / password                                                   #
    # ------------------------------------------------------------------ #

    async def register(self, data: RegisterRequest) -> tuple[UserRead, str, str]:
        if await self.repo.get_by_email(data.email):
            raise HTTPException(status_code=409, detail="Email already registered")

        user = await self.repo.create(
            email=data.email,
            display_name=data.display_name,
            hashed_password=hash_password(data.password),
        )
        await self.db.commit() # CRITICAL FIX: Persist the user to the DB

        access_token, _ = create_access_token(user.id)
        refresh_token, _ = create_refresh_token(user.id)
        return UserRead.model_validate(user), access_token, refresh_token

    async def login(self, data: LoginRequest) -> tuple[UserRead, str, str]:
        user = await self.repo.get_by_email(data.email)
        if not user or not user.hashed_password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token, _ = create_access_token(user.id)
        refresh_token, _ = create_refresh_token(user.id)
        return UserRead.model_validate(user), access_token, refresh_token

    # ------------------------------------------------------------------ #
    # GitHub OAuth                                                       #
    # ------------------------------------------------------------------ #

    async def github_callback(self, code: str) -> tuple[UserRead, str, str]:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            gh_token = token_resp.json().get("access_token")
            if not gh_token:
                raise HTTPException(status_code=400, detail="GitHub OAuth failed — no access token")

            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
                timeout=10,
            )
            gh_user = user_resp.json()

            email: str | None = gh_user.get("email")
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {gh_token}"},
                    timeout=10,
                )
                primary = next((e for e in emails_resp.json() if e["primary"] and e["verified"]), None)
                email = primary["email"] if primary else None

        if not email:
            raise HTTPException(status_code=400, detail="No verified email on GitHub account")

        user = await self.repo.get_by_github_id(str(gh_user["id"]))
        if not user:
            user = await self.repo.get_by_email(email)
            if user:
                user = await self.repo.update(
                    user,
                    github_user_id=str(gh_user["id"]),
                    avatar_url=gh_user.get("avatar_url"),
                )
            else:
                user = await self.repo.create(
                    email=email,
                    display_name=gh_user.get("name") or gh_user.get("login") or email,
                    github_user_id=str(gh_user["id"]),
                    avatar_url=gh_user.get("avatar_url"),
                )
        
        await self.db.commit() # CRITICAL FIX: Persist the OAuth user updates/creation

        access_token, _ = create_access_token(user.id)
        refresh_token, _ = create_refresh_token(user.id)
        return UserRead.model_validate(user), access_token, refresh_token

    # ------------------------------------------------------------------ #
    # Google OAuth                                                       #
    # ------------------------------------------------------------------ #

    async def google_callback(self, code: str) -> tuple[UserRead, str, str]:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{settings.frontend_url}/auth/google/callback",
                },
                timeout=10,
            )
            g_token = token_resp.json().get("access_token")
            if not g_token:
                raise HTTPException(status_code=400, detail="Google OAuth failed — no access token")

            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {g_token}"},
                timeout=10,
            )
            g_user = user_resp.json()

        email: str | None = g_user.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="No email from Google account")

        user = await self.repo.get_by_google_id(g_user["id"])
        if not user:
            user = await self.repo.get_by_email(email)
            if user:
                user = await self.repo.update(
                    user,
                    google_user_id=g_user["id"],
                    avatar_url=g_user.get("picture"),
                )
            else:
                user = await self.repo.create(
                    email=email,
                    display_name=g_user.get("name") or email,
                    google_user_id=g_user["id"],
                    avatar_url=g_user.get("picture"),
                )
        
        await self.db.commit() # CRITICAL FIX: Persist the OAuth user updates/creation

        access_token, _ = create_access_token(user.id)
        refresh_token, _ = create_refresh_token(user.id)
        return UserRead.model_validate(user), access_token, refresh_token

    # ------------------------------------------------------------------ #
    # Token refresh (rotation — old refresh token is immediately revoked) #
    # ------------------------------------------------------------------ #

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        if payload.type != "refresh":
            raise HTTPException(status_code=401, detail="Wrong token type")

        if await self.redis.get(f"revoked:{payload.jti}"):
            raise HTTPException(status_code=401, detail="Refresh token already revoked")

        await self.redis.setex(
            f"revoked:{payload.jti}",
            int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
            "1",
        )

        user = await self.repo.get_by_id(payload.sub)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        new_access, _ = create_access_token(user.id)
        new_refresh, _ = create_refresh_token(user.id)
        return new_access, new_refresh

    # ------------------------------------------------------------------ #
    # Logout — revoke both tokens                                        #
    # ------------------------------------------------------------------ #

    async def logout(self, access_token: str | None, refresh_token: str | None) -> None:
        for token, ttl in [
            (access_token, int(timedelta(minutes=settings.access_token_expire_minutes).total_seconds())),
            (refresh_token, int(timedelta(days=settings.refresh_token_expire_days).total_seconds())),
        ]:
            if not token:
                continue
            try:
                payload = decode_token(token)
                await self.redis.setex(f"revoked:{payload.jti}", ttl, "1")
            except ValueError:
                pass 

    # ------------------------------------------------------------------ #
    # Verify access token (used by the get_current_user dependency)       #
    # ------------------------------------------------------------------ #

    async def get_user_from_access_token(self, token: str):
        try:
            payload = decode_token(token)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid token")

        if payload.type != "access":
            raise HTTPException(status_code=401, detail="Wrong token type")

        if await self.redis.get(f"revoked:{payload.jti}"):
            raise HTTPException(status_code=401, detail="Token revoked")

        user = await self.repo.get_by_id(payload.sub)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user
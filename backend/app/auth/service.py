from datetime import timedelta

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException

from app.auth.schemas import LoginRequest, RegisterRequest, UserRead
from app.auth.uow import AbstractAuthUnitOfWork
from app.auth.utils.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.auth.utils.password import hash_password, verify_password
from app.config import get_settings

settings = get_settings()


class AuthService:
    def __init__(self, uow: AbstractAuthUnitOfWork, redis: aioredis.Redis) -> None:
        self.uow = uow
        self.redis = redis

    # ------------------------------------------------------------------ #
    # Email / password                                                     #
    # ------------------------------------------------------------------ #

    async def register(self, data: RegisterRequest) -> tuple[UserRead, str, str]:
        async with self.uow:
            if await self.uow.users.get_by_email(data.email):
                raise HTTPException(status_code=409, detail="Email already registered")

            user = await self.uow.users.create(
                email=data.email,
                display_name=data.display_name,
                hashed_password=hash_password(data.password),
            )
            await self.uow.commit()

            access_token, _ = create_access_token(user.id)
            refresh_token, _ = create_refresh_token(user.id)
            return UserRead.model_validate(user), access_token, refresh_token

    async def login(self, data: LoginRequest) -> tuple[UserRead, str, str]:
        async with self.uow:
            user = await self.uow.users.get_by_email(data.email)
            if not user or not user.hashed_password:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            if not verify_password(data.password, user.hashed_password):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            access_token, _ = create_access_token(user.id)
            refresh_token, _ = create_refresh_token(user.id)
            return UserRead.model_validate(user), access_token, refresh_token
        
    async def search_users(self, query: str, limit: int = 10) -> list[UserRead]:
        """Search for users to invite them to workspaces/projects/channels."""
        clean_query = query.strip()
        if len(clean_query) < 2:
            return []  # Return empty if the query is too short
            
        async with self.uow:
            users = await self.uow.users.search_users(clean_query, limit)
            return [UserRead.model_validate(u) for u in users]
    # ------------------------------------------------------------------ #
    # GitHub OAuth — sign in / register                                   #
    # ------------------------------------------------------------------ #

    async def _fetch_github_user(self, code: str, redirect_uri: str) -> tuple[dict, str]:
        """Exchange code for GitHub user profile + verified email. Returns (gh_user, email)."""
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
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
                primary = next(
                    (e for e in emails_resp.json() if e["primary"] and e["verified"]),
                    None,
                )
                email = primary["email"] if primary else None

        if not email:
            raise HTTPException(status_code=400, detail="No verified email on GitHub account")

        return gh_user, email

    async def github_callback(self, code: str) -> tuple[UserRead, str, str]:
        gh_user, email = await self._fetch_github_user(
            code,
            redirect_uri=f"{settings.backend_url}/api/v1/auth/github/callback",
            )

        async with self.uow:
            user = await self.uow.users.get_by_github_id(str(gh_user["id"]))
            if not user:
                existing = await self.uow.users.get_by_email(email)
                if existing:
                    # Tell the user which method they registered with
                    method = "Google" if existing.google_user_id else "email and password"
                    raise HTTPException(
                        status_code=409,
                        detail=f"This email is already registered via {method}. "
                               f"Sign in with {method}, then link GitHub from account settings.",
                    )
                user = await self.uow.users.create(
                    email=email,
                    display_name=gh_user.get("name") or gh_user.get("login") or email,
                    github_user_id=str(gh_user["id"]),
                    avatar_url=gh_user.get("avatar_url"),
                )

            await self.uow.commit()

            access_token, _ = create_access_token(user.id)
            refresh_token, _ = create_refresh_token(user.id)
            return UserRead.model_validate(user), access_token, refresh_token

    async def link_github(self, current_user_id: str, code: str) -> UserRead:
        """Attach a GitHub identity to an already-authenticated account."""
        gh_user, _ = await self._fetch_github_user(
            code,
            redirect_uri=f"{settings.backend_url}/api/v1/auth/github/callback",
        )

        async with self.uow:
            # Make sure this GitHub account isn't already linked to someone else
            existing = await self.uow.users.get_by_github_id(str(gh_user["id"]))
            if existing and existing.id != current_user_id:
                raise HTTPException(
                    status_code=409,
                    detail="This GitHub account is already linked to another Synapse account.",
                )

            user = await self.uow.users.get_by_id(current_user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if user.github_user_id:
                raise HTTPException(
                    status_code=409,
                    detail="A GitHub account is already linked. Unlink it first.",
                )

            user = await self.uow.users.update(
                user,
                github_user_id=str(gh_user["id"]),
                # Only update avatar if the user doesn't have one yet
                avatar_url=user.avatar_url or gh_user.get("avatar_url"),
            )
            await self.uow.commit()
            return UserRead.model_validate(user)

    async def unlink_github(self, current_user_id: str) -> UserRead:
        """Remove the GitHub identity from an account."""
        async with self.uow:
            user = await self.uow.users.get_by_id(current_user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Must have another sign-in method before unlinking
            if not user.google_user_id and not user.hashed_password:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot unlink GitHub — it is your only sign-in method. "
                           "Add a password or link Google first.",
                )

            user = await self.uow.users.update(user, github_user_id=None)
            await self.uow.commit()
            return UserRead.model_validate(user)

    # ------------------------------------------------------------------ #
    # Google OAuth — sign in / register                                   #
    # ------------------------------------------------------------------ #

    async def _fetch_google_user(self, code: str, redirect_uri: str) -> tuple[dict, str]:
        """Exchange code for Google user profile. Returns (g_user, email)."""
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
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

        return g_user, email

    async def google_callback(self, code: str) -> tuple[UserRead, str, str]:
        g_user, email = await self._fetch_google_user(
            code,
            redirect_uri=f"{settings.backend_url}/api/v1/auth/google/callback",
            )

        async with self.uow:
            user = await self.uow.users.get_by_google_id(g_user["id"])
            if not user:
                existing = await self.uow.users.get_by_email(email)
                if existing:
                    method = "GitHub" if existing.github_user_id else "email and password"
                    raise HTTPException(
                        status_code=409,
                        detail=f"This email is already registered via {method}. "
                               f"Sign in with {method}, then link Google from account settings.",
                    )
                user = await self.uow.users.create(
                    email=email,
                    display_name=g_user.get("name") or email,
                    google_user_id=g_user["id"],
                    avatar_url=g_user.get("picture"),
                )

            await self.uow.commit()

            access_token, _ = create_access_token(user.id)
            refresh_token, _ = create_refresh_token(user.id)
            return UserRead.model_validate(user), access_token, refresh_token

    async def link_google(self, current_user_id: str, code: str) -> UserRead:
        """Attach a Google identity to an already-authenticated account."""
        g_user, _ = await self._fetch_google_user(
            code,
            redirect_uri=f"{settings.backend_url}/api/v1/auth/link/google/callback",
            )

        async with self.uow:
            existing = await self.uow.users.get_by_google_id(g_user["id"])
            if existing and existing.id != current_user_id:
                raise HTTPException(
                    status_code=409,
                    detail="This Google account is already linked to another Synapse account.",
                )

            user = await self.uow.users.get_by_id(current_user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if user.google_user_id:
                raise HTTPException(
                    status_code=409,
                    detail="A Google account is already linked. Unlink it first.",
                )

            user = await self.uow.users.update(
                user,
                google_user_id=g_user["id"],
                avatar_url=user.avatar_url or g_user.get("picture"),
            )
            await self.uow.commit()
            return UserRead.model_validate(user)

    async def unlink_google(self, current_user_id: str) -> UserRead:
        """Remove the Google identity from an account."""
        async with self.uow:
            user = await self.uow.users.get_by_id(current_user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not user.github_user_id and not user.hashed_password:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot unlink Google — it is your only sign-in method. "
                           "Add a password or link GitHub first.",
                )

            user = await self.uow.users.update(user, google_user_id=None)
            await self.uow.commit()
            return UserRead.model_validate(user)

    # ------------------------------------------------------------------ #
    # Token refresh                                                        #
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

        async with self.uow:
            user = await self.uow.users.get_by_id(payload.sub)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")

            new_access, _ = create_access_token(user.id)
            new_refresh, _ = create_refresh_token(user.id)
            return new_access, new_refresh

    # ------------------------------------------------------------------ #
    # Logout                                                               #
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
    # Verify access token                                                  #
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

        async with self.uow:
            user = await self.uow.users.get_by_id(payload.sub)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")

            return user
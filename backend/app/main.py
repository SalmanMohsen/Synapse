from contextlib import asynccontextmanager
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth.router import router as auth_router
from app.config import get_settings
from app.project.router import projects_router, workspace_projects_router
from app.workspace.router import invite_router, router as workspace_router
from app.channel.router import channels_router, project_channels_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()

app = FastAPI(title="Synapse API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router already has /api/v1/auth prefix — do NOT add another prefix here
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(invite_router)
app.include_router(workspace_projects_router)
app.include_router(projects_router)
app.include_router(channels_router)
app.include_router(project_channels_router)
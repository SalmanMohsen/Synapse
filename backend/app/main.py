from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.channel.router import channels_router, project_channels_router
from app.config import get_settings
from app.inbox.router import (
    channel_invite_router,
    inbox_router,
    project_invite_router,
    workspace_invite_router,
)
from app.project.router import projects_router, workspace_projects_router
from app.message.router import messages_router
from app.ticket.router import channel_tickets_router, tickets_router
from app.websocket.router import ws_router
from app.workspace.router import router as workspace_router
from app.github.router import router as github_router
from app.skill.router import router as skill_router
from app.agent_run.router import router as agent_run_router
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

# Auth
app.include_router(auth_router)

# Workspace
app.include_router(workspace_router)

# Projects (workspace-scoped create/list + project-scoped CRUD)
app.include_router(workspace_projects_router)
app.include_router(projects_router)

# Channels (project-scoped create/list + channel-scoped CRUD)
app.include_router(project_channels_router)
app.include_router(channels_router)

# Inbox: personal inbox + invite-sending endpoints scoped to each entity.
# Replaces the old token-based invite_router from workspace.router.
app.include_router(inbox_router)
app.include_router(workspace_invite_router)
app.include_router(project_invite_router)
app.include_router(channel_invite_router)

# Tickets (channel-scoped create/list + ticket-scoped lifecycle)
app.include_router(channel_tickets_router)
app.include_router(tickets_router)
 
# Messages
app.include_router(messages_router)
 
# WebSocket
app.include_router(ws_router)

# GitHub Integrations
app.include_router(github_router) 

# Skill Management
app.include_router(skill_router)

# Agent Runs (Planning Agent plan review — approve/reject/edit)
app.include_router(agent_run_router)
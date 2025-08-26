from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.api.projects import router as projects_router
from app.api.repo import router as repo_router
from app.api.commits import router as commits_router
from app.api.env import router as env_router
from app.api.assets import router as assets_router
from app.api.chat import router as chat_router
from app.api.tokens import router as tokens_router
from app.api.settings import router as settings_router
from app.api.project_services import router as project_services_router
from app.api.github import router as github_router
from app.api.vercel import router as vercel_router
from app.core.logging import configure_logging
from app.core.terminal_ui import ui
from sqlalchemy import inspect
from app.db.base import Base
import app.models  # noqa: F401 ensures models are imported for metadata
from app.db.session import engine
import os

configure_logging()

app = FastAPI(title="Clovable API")

# Middleware to suppress logging for specific endpoints and debug CORS
class LogFilterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Debug CORS requests
        if os.getenv("DEBUG_CORS", "false").lower() == "true":
            origin = request.headers.get("origin")
            if origin:
                print(f"🌐 CORS Request from origin: {origin}")
                print(f"   Method: {request.method}")
                print(f"   Path: {request.url.path}")

        # Suppress logging for polling endpoints
        if "/requests/active" in request.url.path:
            import logging
            logger = logging.getLogger("uvicorn.access")
            original_disabled = logger.disabled
            logger.disabled = True
            try:
                response = await call_next(request)
            finally:
                logger.disabled = original_disabled
        else:
            response = await call_next(request)
        return response

app.add_middleware(LogFilterMiddleware)

# CORS configuration - supports both development and production
def get_cors_config():
    """Get CORS configuration based on environment"""
    cors_origins = os.getenv("CORS_ORIGINS", "")
    debug_cors = os.getenv("DEBUG_CORS", "false").lower() == "true"

    if debug_cors:
        # Debug mode: allow all origins (ONLY for debugging)
        return ["*"], "debug"
    elif cors_origins:
        # Production: use specific origins from environment
        origins = [origin.strip() for origin in cors_origins.split(",")]
        return origins, "production"
    else:
        # Development: allow common local development origins
        origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://localhost:8080",  # In case frontend calls from same port
            "http://127.0.0.1:8080"
        ]
        return origins, "development"

# Get CORS configuration
allowed_origins, cors_mode = get_cors_config()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Routers
app.include_router(projects_router, prefix="/api/projects")
app.include_router(repo_router)
app.include_router(commits_router)
app.include_router(env_router)
app.include_router(assets_router)
app.include_router(chat_router, prefix="/api/chat")  # Unified chat API (includes WebSocket and ACT)
app.include_router(tokens_router)  # Service tokens API
app.include_router(settings_router)  # Settings API
app.include_router(project_services_router)  # Project services API
app.include_router(github_router)  # GitHub integration API
app.include_router(vercel_router)  # Vercel integration API


@app.get("/health")
def health():
    # Health check (English comments only)
    return {"ok": True}


@app.get("/cors-config")
def cors_config():
    """Get current CORS configuration for debugging"""
    cors_origins = os.getenv("CORS_ORIGINS", "")
    debug_cors = os.getenv("DEBUG_CORS", "false").lower() == "true"

    return {
        "cors_origins_env": cors_origins,
        "debug_cors": debug_cors,
        "allowed_origins": allowed_origins,
        "cors_mode": cors_mode
    }


@app.on_event("startup")
def on_startup() -> None:
    # Auto create tables if not exist; production setups should use Alembic
    ui.info("Initializing database tables")
    inspector = inspect(engine)
    Base.metadata.create_all(bind=engine)
    ui.success("Database initialization complete")

    # Show CORS configuration
    if cors_mode == "debug":
        ui.warning("⚠️  DEBUG MODE: CORS allows ALL origins - DO NOT use in production!")
    elif cors_mode == "production":
        ui.info(f"🔒 CORS configured for production origins: {allowed_origins}")
    else:
        ui.info(f"🔧 CORS configured for local development: {allowed_origins}")

    # Show available endpoints
    ui.info("API server ready")
    ui.panel(
        "WebSocket: /api/chat/{project_id}\nREST API: /api/projects, /api/chat, /api/github, /api/vercel\nCORS Config: /cors-config",
        title="Available Endpoints",
        style="green"
    )

    # Display ASCII logo after all initialization is complete
    ui.ascii_logo()

    # Show environment info
    env_info = {
        "Environment": os.getenv("ENVIRONMENT", "development"),
        "Debug": os.getenv("DEBUG", "false"),
        "Port": os.getenv("PORT", "8000"),
        "CORS Mode": cors_mode
    }
    ui.status_line(env_info)

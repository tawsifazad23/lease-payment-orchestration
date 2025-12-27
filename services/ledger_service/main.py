import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.database import init_db, close_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.service_name}")
    await init_db()
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="Ledger Service",
    description="Manages immutable audit trail and event sourcing",
    version="1.0.0",
    lifespan=lifespan,
)


# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy", "service": settings.service_name}


@app.get("/ready")
async def readiness_check():
    """Readiness check - service can accept traffic."""
    return {"status": "ready", "service": settings.service_name}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Ledger Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
    )

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.database import init_db, close_db
from shared.redis_client import RedisClient
from shared.event_bus import event_bus
from services.lease_service.api import routes

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

    try:
        await event_bus.initialize()
        logger.info("Event bus initialized")
    except Exception as e:
        logger.warning(f"Event bus initialization failed (non-blocking): {e}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")
    await close_db()
    await RedisClient.close()


# Create FastAPI app
app = FastAPI(
    title="Lease Service",
    description="Manages lease lifecycle and state transitions",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(routes.router)


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
        "service": "Lease Service",
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

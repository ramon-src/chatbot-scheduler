"""
SimplificaPsi - Main Application
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.api.agent_routes import router as agent_router

# Setup logging
setup_logging()
logger = get_logger(__name__)

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================
app = FastAPI(
    title="SimplificaPsi API",
    description="Sistema de Agentes AI para Gestão de Consultórios Psicológicos",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# =============================================================================
# CORS MIDDLEWARE
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# HEALTH CHECK
# =============================================================================
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0"
    }

# =============================================================================
# ROOT ENDPOINT
# =============================================================================
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "SimplificaPsi API",
        "version": "0.1.0",
        "docs": "/docs" if settings.DEBUG else "Documentation not available in production"
    }

# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================
# =============================================================================
# ROUTERS
# =============================================================================
app.include_router(agent_router, prefix=settings.API_PREFIX)

@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("Starting SimplificaPsi API", environment=settings.ENVIRONMENT)

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info("Shutting down SimplificaPsi API")

# =============================================================================
# MAIN FUNCTION
# =============================================================================
def main():
    """Main function for running the application"""
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )

if __name__ == "__main__":
    main()


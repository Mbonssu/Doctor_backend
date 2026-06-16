from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import settings
from .core.database import engine, Base
from .api.v1.routes import (
    auth_router, users_router, doctors_router,
    appointments_router, reviews_router, favorites_router,
    notifications_router, family_router, support_router,
)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Créer les tables au démarrage (dev uniquement — utiliser Alembic en prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"✅ DoctoPing API démarrée — {settings.ENVIRONMENT}")
    yield
    await engine.dispose()
    print("👋 DoctoPing API arrêtée")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API pour l'application DoctoPing — prise de rendez-vous médicaux",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routes ───────────────────────────────────────────────────────────────────

API_PREFIX = "/api/v1"

app.include_router(auth_router,          prefix=API_PREFIX)
app.include_router(users_router,         prefix=API_PREFIX)
app.include_router(family_router,        prefix=API_PREFIX)
app.include_router(doctors_router,       prefix=API_PREFIX)
app.include_router(appointments_router,  prefix=API_PREFIX)
app.include_router(reviews_router,       prefix=API_PREFIX)
app.include_router(favorites_router,     prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(support_router,       prefix=API_PREFIX)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.ENVIRONMENT}


# ─── Global error handler ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if settings.DEBUG:
        raise exc
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})

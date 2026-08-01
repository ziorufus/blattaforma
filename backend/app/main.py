import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import models
from .auth import create_access_token, decode_access_token
from .config import settings
from .database import Base, SessionLocal, engine
from .module_loader import load_modules
from .routers import auth as auth_router
from .routers import groups as groups_router
from .routers import modules as modules_router
from .routers import users as users_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("blattaforma")

app = FastAPI(title="Blattaforma API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-New-Token"],
)

# Required by Authlib to keep the OAuth2 state/nonce across the redirect to Google.
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)


@app.middleware("http")
async def sliding_token_refresh(request: Request, call_next):
    """Renews the caller's JWT on every authenticated request so the session
    stays alive as long as the user keeps interacting with the platform."""
    response = await call_next(request)

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        payload = decode_access_token(auth_header.removeprefix("Bearer ").strip())
        if payload:
            new_token = create_access_token(int(payload["sub"]), payload["email"], payload["is_admin"])
            response.headers["X-New-Token"] = new_token

    return response


def bootstrap_database() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Only ever runs on a brand new, empty database: creates the single
        # bootstrap admin. Afterwards the platform is managed entirely
        # through the admin UI (or direct DB edits), so we never touch
        # existing accounts again on subsequent startups.
        if db.query(models.User).count() == 0:
            db.add(models.User(email=settings.admin_email, name="Administrator", is_admin=True))
            db.commit()
            logger.info("Created initial admin account: %s", settings.admin_email)
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    bootstrap_database()
    load_modules(app)


app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(groups_router.router)
app.include_router(modules_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

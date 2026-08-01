from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import crud
from ..auth import create_access_token
from ..config import settings
from ..deps import get_current_user, get_db
from ..models import User
from ..schemas import MeOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = f"{settings.base_url}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{settings.frontend_url}/login?error=oauth_failed")

    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.userinfo(token=token)

    email = (userinfo or {}).get("email")
    if not email:
        return RedirectResponse(f"{settings.frontend_url}/login?error=oauth_failed")

    user = crud.get_user_by_email(db, email)
    if user is None or not user.is_active:
        return RedirectResponse(f"{settings.frontend_url}/login?error=unauthorized")

    user.name = userinfo.get("name") or user.name
    user.picture = userinfo.get("picture") or user.picture
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    jwt_token = create_access_token(user.id, user.email, user.is_admin)
    return RedirectResponse(f"{settings.frontend_url}/login/callback#token={jwt_token}")


@router.get("/me", response_model=MeOut)
def read_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_me(user, db)


def _build_me(user: User, db: Session) -> MeOut:
    from ..schemas import GroupOut

    effective = crud.effective_permissions(db, user)
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        group_ids=[g.id for g in user.groups],
        groups=[
            GroupOut(
                id=g.id,
                name=g.name,
                description=g.description,
                created_at=g.created_at,
                member_count=len(g.users),
            )
            for g in user.groups
        ],
        effective_permissions=effective,
    )

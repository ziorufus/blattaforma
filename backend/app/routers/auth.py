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
oauth.register(
    name="microsoft",
    client_id=settings.microsoft_client_id,
    client_secret=settings.microsoft_client_secret,
    server_metadata_url=(
        f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}"
        "/v2.0/.well-known/openid-configuration"
    ),
    # Niente scope "openid" (e quindi neanche "email"/"profile", che hanno
    # senso solo insieme a "openid"): con il tenant multi-tenant "common"
    # l'id_token ha un claim "iss" col GUID del tenant reale, che non
    # corrisponde mai all'issuer "template" dichiarato dal discovery
    # document, e Authlib rifiuta il token. Usando solo lo scope Graph
    # "User.Read" niente id_token viene emesso: l'email si ottiene da
    # Graph /me nel callback, che è comunque la fonte autoritativa.
    client_kwargs={"scope": "User.Read"},
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


@router.get("/microsoft/login")
async def microsoft_login(request: Request):
    redirect_uri = f"{settings.base_url}/api/auth/microsoft/callback"
    # Senza "prompt" Microsoft riusa la sessione SSO del browser e accede
    # subito con l'ultimo account usato, senza mostrare il selettore.
    return await oauth.microsoft.authorize_redirect(request, redirect_uri, prompt="select_account")


@router.get("/microsoft/callback")
async def microsoft_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.microsoft.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{settings.frontend_url}/login?error=oauth_failed")

    userinfo = token.get("userinfo") or {}

    # Il claim "email" dell'id_token Microsoft non è affidabile su tutti i
    # tenant/tipi di account: si interroga Graph /me per l'indirizzo reale.
    profile: dict = {}
    try:
        resp = await oauth.microsoft.get("https://graph.microsoft.com/v1.0/me", token=token)
        profile = resp.json()
    except Exception:
        profile = {}

    email = profile.get("mail") or profile.get("userPrincipalName") or userinfo.get("email")
    if not email:
        return RedirectResponse(f"{settings.frontend_url}/login?error=oauth_failed")

    user = crud.get_user_by_email(db, email)
    if user is None or not user.is_active:
        return RedirectResponse(f"{settings.frontend_url}/login?error=unauthorized")

    user.name = profile.get("displayName") or userinfo.get("name") or user.name
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

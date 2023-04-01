import datetime
import json

from beanie import init_beanie
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from fief_client import FiefUserInfo
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opensensor.db import User, get_motor_mongo_connection
from opensensor.users import SESSION_COOKIE_NAME, auth, fief


class JSONTZEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return jsonable_encoder(obj)


app = FastAPI()
app.json_encoder = JSONTZEncoder
# Add TrustedHostMiddleware and XForwardedMiddleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.opensensor.com"])
app.add_middleware(ProxyHeadersMiddleware)


@app.get("/auth-callback", name="auth_callback")
async def auth_callback(request: Request, response: Response, code: str = Query(...)):
    redirect_uri = request.url_for("auth_callback")
    tokens, _ = await fief.auth_callback(code, redirect_uri)

    response = RedirectResponse(request.url_for("protected"))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        tokens["access_token"],
        max_age=tokens["expires_in"],
        httponly=True,
        secure=False,
    )

    return response


@app.get("/protected", name="protected")
async def protected(
    user: FiefUserInfo = Depends(auth.current_user()),
):
    return HTMLResponse(f"<h1>You are authenticated. Your user email is {user['email']}</h1>")


@app.get("/authenticated-route")
async def authenticated_route(user: User = Depends(auth.current_user())):
    return {"message": f"Hello {user.email}!"}


@app.on_event("startup")
async def on_startup():
    db = get_motor_mongo_connection()
    await init_beanie(
        database=db,
        document_models=[
            User,
        ],
    )

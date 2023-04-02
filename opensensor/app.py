import datetime
import json
from typing import Dict

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fief_client import FiefUserInfo
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opensensor.users import (
    SESSION_COOKIE_NAME,
    add_api_key,
    auth,
    fief,
    get_or_create_user,
    get_redirect_uri,
)

origins = [
    "https://graph.opensensor.io",
    "https://opensensor.io",
    "https://www.opensensor.io",
]


class JSONTZEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return jsonable_encoder(obj)


app = FastAPI()
app.json_encoder = JSONTZEncoder
app.add_middleware(ProxyHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "OK"}


@app.get("/auth-callback", name="auth_callback")
async def auth_callback(request: Request, response: Response, code: str = Query(...)):
    redirect_uri = get_redirect_uri(request)
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


@app.post("/generate-api-key")
async def generate_api_key(
    description: str, device_id: str, user_dict: Dict = Depends(auth.current_user())
):
    user_id = user_dict["sub"]
    user = get_or_create_user(user_id)
    new_api_key = add_api_key(user, description, device_id)
    return {"message": f"New API key generated for user {user_id}", "api_key": new_api_key}

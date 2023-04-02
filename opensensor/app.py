import datetime
import json

from beanie import init_beanie
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from fief_client import FiefUserInfo
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opensensor.db import User, get_motor_mongo_connection
from opensensor.users import SESSION_COOKIE_NAME, auth, fief, get_redirect_uri, get_or_create_user, add_api_key


class JSONTZEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return jsonable_encoder(obj)


app = FastAPI()
app.json_encoder = JSONTZEncoder
app.add_middleware(ProxyHeadersMiddleware)


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
async def generate_api_key(description: str, device_id: str, user_dict: Dict = Depends(auth.current_user())):
    user_id = user_dict["sub"]
    user = get_or_create_user(user_id)
    new_api_key = add_api_key(users_db, user, description, device_id)
    return {"message": f"New API key generated for user {user_id}", "api_key": new_api_key}


@app.on_event("startup")
async def on_startup():
    db = get_motor_mongo_connection()
    await init_beanie(
        database=db,
        document_models=[
            User,
        ],
    )

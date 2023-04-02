import base64
import os
import secrets
from typing import List
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth
from pydantic import BaseModel, Field

from opensensor.db import get_open_sensor_db


def get_redirect_uri(request):
    s = "https"
    host = request.url.hostname
    path = "/auth-callback"
    redirect_uri = f"{s}://{host}{path}"
    return redirect_uri


class CustomFiefAuth(FiefAuth):
    client: FiefAsync

    async def get_unauthorized_response(self, request: Request, response: Response):
        redirect_uri = get_redirect_uri(request)
        auth_url = await self.client.auth_url(redirect_uri, scope=["openid"])
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": auth_url},
        )


def generate_api_key(length: int = 32) -> str:
    random_bytes = secrets.token_bytes(length)
    return base64.urlsafe_b64encode(random_bytes).decode("utf-8")


class APIKey(BaseModel):
    key: str
    device_id: str
    description: str


class User(BaseModel):
    fief_user_id: UUID = Field(..., alias="_id")
    api_keys: List[APIKey]


def get_or_create_user(user_id: UUID) -> User:
    db = get_open_sensor_db()
    users_db = db["Users"]
    user_doc = users_db.find_one({"_id": user_id})

    if user_doc:
        user = User(**user_doc)
    else:
        new_user = User(fief_user_id=user_id, api_keys=[])
        users_db.insert_one(new_user.dict(by_alias=True))
        user = new_user

    return user


def add_api_key(user: User, description: str, device_id: str) -> APIKey:
    db = get_open_sensor_db()
    users_db = db["Users"]
    new_api_key = APIKey(
        key=generate_api_key(),
        device_id=device_id,
        description=description,
    )
    users_db.update_one({"_id": user.fief_user_id}, {"$push": {"api_keys": new_api_key.dict()}})

    return new_api_key


fief = FiefAsync(
    os.environ.get("FIEF_HOST"),
    os.environ.get("FIEF_CLIENT_ID"),
    os.environ.get("FIEF_CLIENT_SECRET"),
)

SESSION_COOKIE_NAME = "user_session"
scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)
auth = CustomFiefAuth(fief, scheme)

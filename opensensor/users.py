import base64
import os
import secrets
from typing import List, Optional
from uuid import UUID

from bson import Binary
from fastapi import HTTPException, Request, Response, status
from fastapi.security import OAuth2AuthorizationCodeBearer
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
    """For OAuth Redirect flows (cookie based auths--not token auths)."""

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
    fief_user_id: Optional[UUID] = Field(None, alias="_id")
    api_keys: List[APIKey]


def get_or_create_user(user_id: UUID) -> User:
    db = get_open_sensor_db()
    users_db = db["Users"]
    binary_uuid = Binary.from_uuid(user_id)
    user_doc = users_db.find_one({"_id": binary_uuid})

    if user_doc:
        user = User(**user_doc)
    else:
        new_user = User(fief_user_id=user_id, api_keys=[])
        # Explicitly set the _id field in the dictionary before inserting the document
        new_user_dict = new_user.dict(by_alias=True, exclude_none=True)
        new_user_dict["_id"] = binary_uuid
        users_db.insert_one(new_user_dict)
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
    user.api_keys.append(new_api_key)

    # Convert the ApiKey instances in the api_keys list to dictionaries
    api_keys_dict_list = [api_key.dict() for api_key in user.api_keys]

    users_db.update_one(
        {"_id": Binary.from_uuid(user.fief_user_id)}, {"$set": {"api_keys": api_keys_dict_list}}
    )

    return new_api_key


fief = FiefAsync(
    os.environ.get("FIEF_HOST"),
    os.environ.get("FIEF_CLIENT_ID"),
    os.environ.get("FIEF_CLIENT_SECRET"),
)

scheme = OAuth2AuthorizationCodeBearer(
    f"{os.environ.get('FIEF_HOST')}/authorize",
    f"{os.environ.get('FIEF_HOST')}/api/token",
    scopes={"openid": "openid", "offline_access": "offline_access"},
    auto_error=False,
)

auth = FiefAuth(fief, scheme)

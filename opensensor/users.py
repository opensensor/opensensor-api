import base64
import os
import secrets
from typing import Dict, List, Optional
from uuid import UUID

from bson import Binary
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.security import APIKeyCookie
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth, FiefUserInfo
from pydantic import BaseModel, Field

from opensensor.collections import DeviceMetadata, Environment
from opensensor.db import get_open_sensor_db


fief = FiefAsync(
    os.environ.get("FIEF_HOST"),
    os.environ.get("FIEF_CLIENT_ID"),
    os.environ.get("FIEF_CLIENT_SECRET"),
)
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    f"{os.environ.get('FIEF_HOST')}/authorize",
    f"{os.environ.get('FIEF_HOST')}/api/token",
    scopes={"openid": "openid", "offline_access": "offline_access"},
    auto_error=False,
)
oauth2_auth = FiefAuth(fief, oauth2_scheme)
SESSION_COOKIE_NAME = "grafana_session"
scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)


def get_redirect_uri(request):
    s = "https"
    host = request.url.hostname
    path = "/auth-callback"
    redirect_uri = f"{s}://{host}{path}"
    return redirect_uri


class CustomFiefOAuth2(FiefAuth):
    """For OAuth Redirect flows (cookie based auths--not token auths)."""

    client: FiefAsync

    async def get_unauthorized_response(self, request: Request, response: Response):
        redirect_uri = get_redirect_uri(request)
        auth_url = await self.client.auth_url(redirect_uri, scope=["openid"])
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": auth_url},
        )


class CustomFiefStaticAuth(FiefAuth):
    """For OAuth Redirect flows (cookie based auths--not token auths)."""

    client: FiefAsync

    async def get_unauthorized_response(self, request: Request, response: Response):
        return {"access_token": None, "id": None, "email": None}

    async def current_user(self, token: Optional[str] = Depends(oauth2_scheme)) -> Optional[FiefUserInfo]:
        if not token:
            return FiefUserInfo(access_token=None, id=None, email=None)  # Return an anonymous user

        return super().current_user(token)


def generate_api_key(length: int = 32) -> str:
    random_bytes = secrets.token_bytes(length)
    return base64.urlsafe_b64encode(random_bytes).decode("utf-8")


class APIKey(BaseModel):
    key: str
    device_id: str
    device_name: str
    description: str
    private_data: bool = False


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
        user.fief_user_id = user_id

    return user


def filter_api_keys_by_device_name(api_keys: List[APIKey], target_device_name: str) -> List[str]:
    filtered_device_ids = [
        api_key.device_id for api_key in api_keys if api_key.device_name == target_device_name
    ]
    return filtered_device_ids


def filter_api_keys_by_device_id(api_keys: List[APIKey], target_device_id: str) -> (List[str], str):
    # Find the first APIKey with the given device_id and get its device_name
    target_device_name = None
    for api_key in api_keys:
        if api_key.device_id == target_device_id:
            target_device_name = api_key.device_name
            break

    if target_device_name is None:
        return [], None

    # Filter the API keys by the device_name
    filtered_device_ids = [
        api_key.device_id for api_key in api_keys if api_key.device_name == target_device_name
    ]
    return filtered_device_ids, target_device_name


def add_api_key(
    user: User, device_id: str, device_name: str, description: str, private_data: bool
) -> APIKey:
    db = get_open_sensor_db()
    users_db = db["Users"]

    # Check if the device_id and device_name combination is already associated with an API key for any other user
    existing_key = users_db.find_one(
        {
            "_id": {"$ne": Binary.from_uuid(user.fief_user_id)},
            "$and": [{"api_keys.device_id": device_id}, {"api_keys.device_name": device_name}],
        }
    )
    if existing_key:
        raise ValueError(
            f"Device ID {device_id} with name {device_name} is already associated to another User."
        )

    new_api_key = APIKey(
        key=generate_api_key(),
        device_id=device_id,
        device_name=device_name,
        description=description,
        private_data=private_data,
    )
    user.api_keys.append(new_api_key)

    # Convert the ApiKey instances in the api_keys list to dictionaries
    api_keys_dict_list = [api_key.dict() for api_key in user.api_keys]

    users_db.update_one(
        {"_id": Binary.from_uuid(user.fief_user_id)}, {"$set": {"api_keys": api_keys_dict_list}}
    )

    return new_api_key


def get_public_devices() -> List[Dict[str, str]]:
    db = get_open_sensor_db()
    collection = db["Users"]

    # Query for all users and their API keys
    users = collection.find({}, {"_id": 0, "api_keys": 1})

    # Extract public device_ids and device_names from API keys
    public_devices = []
    for user in users:
        for api_key in user["api_keys"]:
            if not api_key.get("private_data", False):
                public_devices.append(
                    {"device_id": api_key["device_id"], "device_name": api_key["device_name"]}
                )

    return public_devices


def get_api_keys_by_device_id(device_id: str) -> List[APIKey]:
    db = get_open_sensor_db()
    users_db = db["Users"]
    user = users_db.find_one({"api_keys": {"$elemMatch": {"device_id": device_id}}})

    if user:
        api_keys = user["api_keys"]
    else:
        api_keys = []

    api_key_objects = [APIKey(**api_key) for api_key in api_keys]
    return api_key_objects


def validate_environment(environment: Environment) -> User:
    return validate_device_metadata(environment.device_metadata)


def validate_device_metadata(device_metadata: DeviceMetadata) -> User:
    return validate_api_key(
        device_metadata.api_key, device_metadata.device_id, device_metadata.name
    )


def validate_api_key(api_key: str, device_id: str, device_name: str) -> User:
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    db = get_open_sensor_db()
    users_db = db["Users"]

    # Find the user with the provided API key
    user_doc = users_db.find_one({"api_keys.key": api_key})

    if user_doc is None:
        print("Invalid API key")
        raise HTTPException(status_code=403, detail="Invalid API key")

    user = User(**user_doc)

    # Find the API key with the matching device_id and device_name
    matching_api_key = None
    for api_key_obj in user.api_keys:
        if api_key_obj.key == api_key:
            if api_key_obj.device_id == device_id and api_key_obj.device_name == device_name:
                matching_api_key = api_key_obj
                break
            else:
                raise HTTPException(
                    status_code=403, detail="Device ID and name do not match the provided API key"
                )

    if matching_api_key is None:
        print("API key not found in the user's API keys")
        raise HTTPException(status_code=403, detail="API key not found in the user's API keys")

    return user


auth = CustomFiefStaticAuth(fief, scheme)

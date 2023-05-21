import base64
import os
import secrets
from collections import defaultdict
from typing import Dict, List, Optional
from uuid import UUID

from bson import Binary
from fastapi import HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie, OAuth2AuthorizationCodeBearer
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth
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
SESSION_COOKIE_NAME = "user_session"
cookie_scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)


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


def mask_key(key: str) -> str:
    return "****-****-****-" + key[-4:]


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

    return [
        api_key for api_key in api_keys if api_key.device_name == target_device_name
    ], target_device_name


def reduce_api_keys_to_device_ids(
    api_keys: List[APIKey], device_common_name: str
) -> (List[str], str):
    device_id, _ = get_device_parts(device_common_name)
    api_keys, target_device_name = filter_api_keys_by_device_id(api_keys, device_id)
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


def list_user_devices(user_id: UUID) -> dict[str, list]:
    db = get_open_sensor_db()
    users_db = db["Users"]
    binary_uuid = Binary.from_uuid(user_id)
    user_doc = users_db.find_one({"_id": binary_uuid})

    result = defaultdict(list)
    if user_doc:
        api_keys = user_doc["api_keys"]

        for api_key in api_keys:
            device_name = api_key["device_name"]
            masked_key = mask_key(api_key["key"])

            if device_name not in result:
                result[device_name] = []

            result[device_name].append(
                {
                    "device_id": api_key["device_id"],
                    "masked_key": masked_key,
                    "private_data": api_key["private_data"],
                    "description": api_key["description"],
                }
            )

    return result


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
                    {
                        "device_id": api_key["device_id"],
                        "device_name": api_key["device_name"],
                        "combined_name": f"{api_key['device_id']}|{api_key['device_name']}",
                    }
                )

    return public_devices


def get_user_devices(user_id: UUID) -> List[Dict[str, str]]:
    db = get_open_sensor_db()
    collection = db["Users"]

    # Query for the user and their API keys
    user = collection.find_one({"_id": Binary.from_uuid(user_id)}, {"_id": 0, "api_keys": 1})

    # Extract private device_ids and device_names from API keys
    user_devices = []
    if user:
        for api_key in user.get("api_keys", []):
            if api_key.get("private_data", False):
                user_devices.append(
                    {
                        "device_id": api_key["device_id"],
                        "device_name": api_key["device_name"],
                        "combined_name": f"{api_key['device_id']}|{api_key['device_name']}",
                    }
                )

    return user_devices


def get_api_keys_by_device_id(device_id: str) -> (List[APIKey], User):
    device_id, device_name = get_device_parts(device_id)
    db = get_open_sensor_db()
    users_db = db["Users"]
    element_match = {"device_id": device_id}
    if device_name:
        element_match["device_name"] = device_name
    user = users_db.find_one({"api_keys": {"$elemMatch": element_match}})

    if user:
        user = User(**user)
        api_keys = user.api_keys
    else:
        api_keys = []

    return api_keys, user


def get_device_parts(device_common_name: str) -> (str, str):
    device_id_parts = device_common_name.split("|", 1)
    device_id = device_id_parts[0]
    device_name = None
    if len(device_id_parts) > 1:
        device_name = device_id_parts[1]
    return device_id, device_name


def device_id_is_allowed_for_user(device_common_name: str, user=None) -> bool:
    device_id, device_name = get_device_parts(device_common_name)
    api_keys, owner = get_api_keys_by_device_id(device_common_name)
    api_keys, _ = filter_api_keys_by_device_id(api_keys, device_id)
    if len(api_keys) == 0:
        return True

    for api_key in api_keys:
        if api_key.private_data:
            if user is None:
                return False
            if api_key.device_name != device_name:
                return False
            if UUID(user["sub"]) != owner.fief_user_id:
                return False

    return True


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


auth = oauth2_auth

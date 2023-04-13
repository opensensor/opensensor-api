import datetime
import json
from typing import Optional
from uuid import UUID

from fastapi import Body, Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fief_client import FiefAccessTokenInfo, FiefUserInfo
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opensensor.users import (
    add_api_key,
    auth,
    get_or_create_user,
    get_public_devices,
    get_user_devices,
    list_user_devices,
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


@app.get("/masked_devices/")
async def get_masked_devices(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    user_id = access_token_info["id"]
    result = list_user_devices(user_id=user_id)
    return result


@app.post("/generate-api-key")
async def generate_api_key(
    description: str = Body(...),
    device_id: str = Body(...),
    device_name: str = Body(...),
    private_data: bool = Body(...),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    user_id = access_token_info["id"]
    user = get_or_create_user(user_id)
    new_api_key = add_api_key(
        user=user,
        device_id=device_id,
        device_name=device_name,
        description=description,
        private_data=private_data,
    )
    return {"api_key": new_api_key, "message": f"New API key generated for user {user_id}"}


@app.get("/device-listing")
async def device_listing(user: Optional[FiefUserInfo] = Depends(auth.current_user(optional=True))):
    public_device_data = get_public_devices()
    if user:
        public_device_data += get_user_devices(user_id=UUID(user["sub"]))
    return public_device_data

import datetime
import json

from fastapi import Body, Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fief_client import FiefAccessTokenInfo
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opensensor.users import add_api_key, auth, get_or_create_user

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


@app.post("/generate-api-key")
async def generate_api_key(
    description: str = Body(...),
    device_id: str = Body(...),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    print(access_token_info)
    # user_id = user_dict["sub"]
    user_id = "TEST"
    user = get_or_create_user(user_id)
    new_api_key = add_api_key(user, description, device_id)
    print(new_api_key)
    # return {"message": f"New API key generated for user {user_id}", "api_key": new_api_key}
    return {"access_token_info": access_token_info}

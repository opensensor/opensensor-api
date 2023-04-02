import base64
import os
from typing  import List
import secrets

from fastapi import HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie
from fief_client import FiefAsync
from fief_client.integrations.fastapi import FiefAuth
from pydantic import BaseModel


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
    return base64.urlsafe_b64encode(random_bytes).decode('utf-8')


class APIKey(BaseModel):
    key: str
    device_id: str
    description: str


class User(BaseModel):
    fief_user_id: str = Field(..., alias='_id')
    api_keys: List[APIKey]


fief = FiefAsync(
    os.environ.get("FIEF_HOST"),
    os.environ.get("FIEF_CLIENT_ID"),
    os.environ.get("FIEF_CLIENT_SECRET"),
)

SESSION_COOKIE_NAME = "user_session"
scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)
auth = CustomFiefAuth(fief, scheme)

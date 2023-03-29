import json

from beanie import init_beanie
from fastapi import Depends, FastAPI

from opensensor.db import User, db
from opensensor.schemas import UserCreate, UserRead, UserUpdate
from opensensor.users import auth_backend, current_active_user, fastapi_users


class JSONTZEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return jsonable_encoder(obj)


app = FastAPI()
app.json_encoder = JSONTZEncoder

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


@app.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_user)):
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

import datetime
import json

from beanie import init_beanie
from fastapi import Depends, FastAPI
from fastapi.encoders import jsonable_encoder

from opensensor.db import User, get_motor_mongo_connection
from opensensor.users import current_active_user


class JSONTZEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return jsonable_encoder(obj)


app = FastAPI()
app.json_encoder = JSONTZEncoder


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

from bson import Binary
from fastapi import APIRouter, Body, Depends, Response, status
from fief_client import FiefAccessTokenInfo

from opensensor.db import get_open_sensor_db
from opensensor.users import (
    Command,
    User,
    auth,
    device_id_is_allowed_for_user,
    get_or_create_user,
)

# device_id -> common_name -> matching_commands


router = APIRouter()


def get_device_common_name(device_id: str, device_name: str):
    return f"{device_id}|{device_name}"


def add_command_for_user(user: User, device_id: str, device_name: str, command: str) -> Command:
    db = get_open_sensor_db()
    users_db = db["Users"]

    new_command = Command(
        device_id=device_id,
        device_name=device_name,
        command=command,
    )
    user.commands_issued.append(new_command)

    # Convert the Command instances in the commands_issued list to dictionaries
    commands_list = [command.dict() for command in user.commands_issued]

    users_db.update_one(
        {"_id": Binary.from_uuid(user.fief_user_id)}, {"$set": {"commands_issued": commands_list}}
    )

    return new_command


@router.post("/command/device")
async def issue_command(
    device_id: str = Body(...),
    device_name: str = Body(...),
    command: str = Body(...),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    user_id = access_token_info["id"]
    user = get_or_create_user(user_id)
    # Validate that the user has access to the device
    device_id_is_allowed_for_user(device_id, user)

    # TODO Validate that the command is valid for the device

    # Store the command on the User for the device
    add_command_for_user(user, device_id, device_name, command)

    return Response(status_code=status.HTTP_201_CREATED)

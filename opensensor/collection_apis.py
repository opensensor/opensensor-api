from datetime import datetime, timedelta, timezone
from typing import Generic, List, Optional, Type, TypeVar

from bson import Binary
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi_pagination.default import Page as BasePage
from fastapi_pagination.default import Params as BaseParams
from fief_client import FiefUserInfo
from pydantic import BaseModel

from opensensor.collections import (
    CO2,
    PH,
    DeviceMetadata,
    Environment,
    Humidity,
    Lux,
    Moisture,
    Pressure,
    Temperature,
)
from opensensor.db import get_open_sensor_db
from opensensor.users import (
    User,
    auth,
    device_id_is_allowed_for_user,
    get_api_keys_by_device_id,
    get_user_from_fief_user,
    migration_complete,
    reduce_api_keys_to_device_ids,
    validate_device_metadata,
    validate_environment,
)
from opensensor.utils.units import convert_temperature

T = TypeVar("T", bound=BaseModel)

old_collections = {
    "Temperature": "temp",
    "Humidity": "rh",
    "Pressure": "pressure",
    "Lux": "percent",
    "CO2": "ppm",
    "PH": "pH",
    "Moisture": "readings",
}

new_collections = {
    "Temperature": "temp",
    "Humidity": "rh",
    "Pressure": "pressure",
    "Lux": "lux",
    "CO2": "ppm_CO2",
    "PH": "pH",
    "Moisture": "moisture_readings",
}


class Params(BaseParams):
    size: int = Query(50, ge=1, le=1000, description="Page size")


class Page(BasePage[T], Generic[T]):
    __params_type__ = Params


router = APIRouter()


def _record_data_point_to_ts_collection(
    collection,
    ts_column_name: str,
    device_metadata: DeviceMetadata,
    data_point,
    user: User = None,
):
    metadata = device_metadata.dict()
    metadata.pop("api_key", None)
    if user:
        metadata["user_id"] = Binary.from_uuid(user.fief_user_id)
    if hasattr(data_point, "unit"):
        metadata["unit"] = data_point.unit
    data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata,
        ts_column_name: str(getattr(data_point, ts_column_name)),
    }
    collection.insert_one(data)


def _record_data_to_ts_collection(
    collection,
    environment: Environment,
    user: User = None,
):
    metadata = environment.device_metadata.dict()
    metadata.pop("api_key", None)
    if user:
        metadata["user_id"] = Binary.from_uuid(user.fief_user_id)

    # Start building the document to insert
    doc_to_insert = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata,
    }

    # Add each data point to the document
    env_dict = environment.dict()
    for column_name, model_instance in env_dict.items():
        if model_instance is not None and column_name != "device_metadata":
            # We go with the current time because time series collections are restricted this way
            model_instance.pop("timestamp", None)

            for key, value in model_instance.items():
                if value is not None:
                    if key == "unit":
                        doc_to_insert[column_name + "_unit"] = value
                    else:
                        doc_to_insert[column_name] = value

    # Insert the document into the collection
    collection.insert_one(doc_to_insert)


@router.post("/rh/", response_model=Humidity)
async def record_humidity(
    device_metadata: DeviceMetadata,
    rh: Humidity,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Humidity, "rh", device_metadata, rh)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/temp/", response_model=Temperature)
async def record_temperature(
    device_metadata: DeviceMetadata,
    temp: Temperature,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Temperature, "temp", device_metadata, temp)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/pressure/", response_model=Pressure)
async def record_pressure(
    device_metadata: DeviceMetadata,
    pressure: Pressure,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Pressure, "pressure", device_metadata, pressure)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/lux/", response_model=Lux)
async def record_lux(
    device_metadata: DeviceMetadata,
    lux: Lux,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Lux, "percent", device_metadata, lux)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/CO2/", response_model=CO2)
async def record_co2(
    device_metadata: DeviceMetadata,
    co2: CO2,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.CO2, "ppm", device_metadata, co2)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/moisture/", response_model=Moisture)
async def record_moisture_readings(
    device_metadata: DeviceMetadata,
    moisture: Moisture,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Moisture, "readings", device_metadata, moisture)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/pH/", response_model=PH)
async def record_ph(
    device_metadata: DeviceMetadata,
    ph: PH,
    user: User = Depends(validate_device_metadata),
):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.pH, "pH", device_metadata, ph, user)
    return Response(status_code=status.HTTP_201_CREATED)


def get_collection_name(response_model: Type[T]):
    if hasattr(response_model, "collection_name"):
        return response_model.collection_name()
    return response_model.__name__


def _get_old_project_projection(response_model: Type[T]):
    project_projection = {
        "_id": False,
    }
    for field_name, _ in response_model.__fields__.items():
        if field_name == "timestamp":
            project_projection["timestamp"] = "$timestamp"
        if field_name == "unit":
            project_projection["unit"] = "$metadata.unit"
        else:
            project_projection[field_name] = f"${field_name}"
    return project_projection


def _get_project_projection(response_model: Type[T]):
    old_name = get_collection_name(response_model)
    new_collection_name = new_collections[old_name]
    project_projection = {
        "_id": False,
    }
    for field_name, _ in response_model.__fields__.items():
        if field_name == "timestamp":
            project_projection["timestamp"] = "$timestamp"
        if field_name == "unit":
            project_projection[f"{new_collection_name}_unit"] = "$metadata.unit"
        else:
            project_projection[field_name] = f"${new_collection_name}"
    return project_projection


def get_uniform_sample_pipeline(
    response_model: Type[T],
    data_field: str,
    device_ids: List[str],  # Update the type of the device_id parameter to List[str]
    device_name: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
    old_collections: bool,
):
    sampling_interval = timedelta(minutes=resolution)
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=100)
    if end_date is None:
        end_date = datetime.utcnow()

    match_clause = {
        "timestamp": {"$gte": start_date, "$lte": end_date},
        "metadata.device_id": {
            "$in": device_ids
        },  # Use $in operator for matching any device_id in the list
        "metadata.name": device_name,
    }

    # Determine the $project
    if old_collections:
        project_projection = _get_old_project_projection(response_model)
    else:
        old_name = get_collection_name(response_model)
        new_collection_name = new_collections[old_name]
        project_projection = _get_project_projection(response_model)
        match_clause[new_collection_name] = {"$exists": True}

    # Query a uniform sample of documents within the timestamp range
    pipeline = [
        {"$match": match_clause},
        {
            "$addFields": {
                "group": {
                    "$floor": {
                        "$divide": [
                            {"$subtract": ["$timestamp", start_date]},
                            sampling_interval.total_seconds() * 1000,
                        ]
                    }
                }
            }
        },
        {"$group": {"_id": "$group", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$project": project_projection},
        {"$sort": {"timestamp": 1}},  # Sort by timestamp in ascending order
        # {"$count": "total"}
    ]
    return pipeline


model_classes = {
    "temp": Temperature,
    "rh": Humidity,
    "pressure": Pressure,
    "lux": Lux,
    "co2": CO2,
    "readings": Moisture,
    "pH": PH,
}
model_class_attributes = {v: k for k, v in model_classes.items()}


def sample_and_paginate_collection(
    response_model: Type[T],
    collection_name: str,
    data_field: str,
    device_id: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
    page: int,
    size: int,
    unit: str,
    old_collections: bool,
):
    api_keys, _ = get_api_keys_by_device_id(device_id)
    device_ids, target_device_name = reduce_api_keys_to_device_ids(api_keys, device_id)
    offset = (page - 1) * size
    pipeline = get_uniform_sample_pipeline(
        response_model,
        data_field,
        device_ids,
        target_device_name,
        start_date,
        end_date,
        resolution,
        old_collections,
    )
    pipeline.extend([{"$skip": offset}, {"$limit": size}])

    db = get_open_sensor_db()
    collection = db[collection_name]
    raw_data = list(collection.aggregate(pipeline))
    # Add UTC offset to timestamp field
    for item in raw_data:
        item_datetime = datetime.fromisoformat(item["timestamp"])
        item["timestamp"] = item_datetime.replace(tzinfo=timezone.utc).isoformat()
    model_class = model_classes[data_field]
    data = [model_class(**item) for item in raw_data]
    if data_field == "temp" and unit:
        for item in data:
            convert_temperature(item, unit)
    # Re-run for total page count
    pipeline.append({"$count": "total"})
    data_count = list(collection.aggregate(pipeline))
    total_count = data_count[0]["total"] if data else 0
    return Page(items=data, total=total_count, page=page, size=size)


def create_historical_data_route(entity: Type[T]):
    async def historical_data_route(
        fief_user: Optional[FiefUserInfo] = Depends(auth.current_user(optional=True)),
        device_id: str = Path(
            title="The ID of the device chain for which to retrieve historical data."
        ),
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        resolution: int = 30,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        size: int = Query(50, ge=1, le=1000, description="Page size"),
        unit: str | None = None,
    ) -> Page[T]:
        if not device_id_is_allowed_for_user(device_id, user=fief_user):
            raise HTTPException(
                status_code=403,
                detail=f"User {fief_user} is not authorized to access device {device_id}",
            )

        user = get_user_from_fief_user(fief_user)
        if user:
            collection_name = user.collection_name
        else:
            collection_name = "FreeTier"
        migration_finished = migration_complete(collection_name)
        if not migration_finished:
            collection_name = get_collection_name(entity)

        return sample_and_paginate_collection(
            entity,
            collection_name,
            model_class_attributes[entity],
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
            page=page,
            size=size,
            unit=unit,
            old_collections=not migration_finished,
        )

    return historical_data_route


router.add_api_route(
    "/temp/{device_id}",
    create_historical_data_route(Temperature),
    response_model=Page[Temperature],
    methods=["GET"],
)
router.add_api_route(
    "/humidity/{device_id}",
    create_historical_data_route(Humidity),
    response_model=Page[Humidity],
    methods=["GET"],
)
router.add_api_route(
    "/CO2/{device_id}", create_historical_data_route(CO2), response_model=Page[CO2], methods=["GET"]
)
router.add_api_route(
    "/moisture/{device_id}",
    create_historical_data_route(Moisture),
    response_model=Page[Moisture],
    methods=["GET"],
)
router.add_api_route(
    "/pH/{device_id}",
    create_historical_data_route(PH),
    response_model=Page[PH],
    methods=["GET"],
)


@router.post("/environment/")
async def record_environment(
    environment: Environment,
    user: User = Depends(validate_environment),
):
    db = get_open_sensor_db()
    _record_data_to_ts_collection(db.FreeTier, environment, user)
    # Legacy to be removed once everything converts over to the new collection
    if environment.temp:
        _record_data_point_to_ts_collection(
            db.Temperature, "temp", environment.device_metadata, environment.temp, user
        )
    if environment.rh:
        _record_data_point_to_ts_collection(
            db.Humidity, "rh", environment.device_metadata, environment.rh, user
        )
    if environment.pressure:
        _record_data_point_to_ts_collection(
            db.Pressure, "pressure", environment.device_metadata, environment.pressure, user
        )
    if environment.lux:
        _record_data_point_to_ts_collection(
            db.Lux, "percent", environment.device_metadata, environment.lux, user
        )
    if environment.co2:
        _record_data_point_to_ts_collection(
            db.CO2, "ppm", environment.device_metadata, environment.co2, user
        )
    if environment.moisture:
        _record_data_point_to_ts_collection(
            db.Moisture, "readings", environment.device_metadata, environment.moisture, user
        )
    if environment.pH:
        _record_data_point_to_ts_collection(
            db.pH, "pH", environment.device_metadata, environment.pH, user
        )

    return Response(status_code=status.HTTP_201_CREATED)

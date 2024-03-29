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
    VPD,
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
    "pH": "pH",
    "Moisture": "readings",
}

new_collections = {
    "Temperature": "temp",
    "Humidity": "rh",
    "Pressure": "pressure",
    "Lux": "lux",
    "CO2": "ppm_CO2",
    "pH": "pH",
    "Moisture": "moisture_readings",
}

environment_translation = {
    "temp": "temp",
    "rh": "rh",
    "pressure": "pressure",
    "lux": "lux",
    "co2": "ppm_CO2",
    "moisture": "moisture_readings",
    "pH": "pH",
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

            # Translate to the combined collection field names
            column_name = environment_translation[column_name]

            for key, value in model_instance.items():
                if value is not None:
                    if key == "unit":
                        doc_to_insert[column_name + "_unit"] = value
                    else:
                        doc_to_insert[column_name] = str(value)

    # Insert the document into the collection
    collection.insert_one(doc_to_insert)


def get_collection_name(response_model: Type[T]):
    if hasattr(response_model, "collection_name"):
        return response_model.collection_name()
    return response_model.__name__


def _get_project_projection(response_model: Type[T]):
    old_name = get_collection_name(response_model)
    new_collection_name = new_collections.get(old_name, old_name)
    project_projection = {
        "_id": False,
    }
    for field_name, _ in response_model.__fields__.items():
        if field_name == "timestamp":
            project_projection["timestamp"] = "$timestamp"
        elif field_name == "unit":
            project_projection["unit"] = f"${new_collection_name}_unit"
        else:
            project_projection[field_name] = f"${new_collection_name}"
    return project_projection


def get_initial_match_clause(
    device_ids: List[str],
    device_name: str,
    start_date: datetime,
    end_date: datetime,
):
    # Defining the match clause for the pipeline
    match_clause = {
        "timestamp": {"$gte": start_date, "$lte": end_date},
        "metadata.device_id": {
            "$in": device_ids  # Use $in operator for matching any device_id in the list
        },
        "metadata.name": device_name,
    }
    return match_clause


def get_vpd_pipeline(
    device_ids: List[str],
    device_name: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
):
    sampling_interval = timedelta(minutes=resolution)
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=100)
    if end_date is None:
        end_date = datetime.utcnow()
    match_clause = get_initial_match_clause(device_ids, device_name, start_date, end_date)
    match_clause["temp"] = {"$exists": True}
    match_clause["rh"] = {"$exists": True}

    # The MongoDB aggregation pipeline for VPD calculation
    pipeline = [
        {"$match": match_clause},
        {"$addFields": {"tempAsFloat": {"$toDouble": "$temp"}}},
        {"$addFields": {"rhAsFloat": {"$toDouble": "$rh"}}},
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
        {
            "$group": {
                "_id": "$group",
                "averageTemp": {"$avg": "$tempAsFloat"},
                "averageRH": {"$avg": "$rhAsFloat"},
                "timestamp": {"$first": "$timestamp"},
            }
        },
        {
            "$addFields": {
                "satvp": {
                    "$multiply": [
                        0.61078,
                        {
                            "$exp": {
                                "$multiply": [
                                    {"$divide": [17.27, {"$add": ["$averageTemp", 237.3]}]},
                                    "$averageTemp",
                                ]
                            }
                        },
                    ]
                }
            }
        },
        {
            "$addFields": {
                "vpd": {
                    "$multiply": [
                        "$satvp",
                        {"$subtract": [1.0, {"$divide": ["$averageRH", 100.0]}]},
                    ]
                }
            }
        },
        {
            "$project": {
                "_id": False,
                "timestamp": "$timestamp",
                "vpd": "$vpd",
            }
        },
        {"$sort": {"timestamp": 1}},
    ]
    return pipeline


def get_uniform_sample_pipeline(
    response_model: Type[T],
    device_ids: List[str],  # Update the type of the device_id parameter to List[str]
    device_name: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
):
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=100)
    if end_date is None:
        end_date = datetime.utcnow()
    sampling_interval = timedelta(minutes=resolution)
    match_clause = get_initial_match_clause(device_ids, device_name, start_date, end_date)

    # Determine the $project
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
    "VPD": VPD,
}
model_class_attributes = {v: k for k, v in model_classes.items()}


def sample_and_paginate_collection(
    response_model: Type[T],
    collection_name: str,
    device_id: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
    page: int,
    size: int,
    unit: str,
):
    api_keys, _ = get_api_keys_by_device_id(device_id)
    device_ids, target_device_name = reduce_api_keys_to_device_ids(api_keys, device_id)
    offset = (page - 1) * size

    # Determine the right pipeline to use based on the response model
    if response_model is VPD:
        pipeline = get_vpd_pipeline(
            device_ids,
            target_device_name,
            start_date,
            end_date,
            resolution,
        )
    else:
        pipeline = get_uniform_sample_pipeline(
            response_model,
            device_ids,
            target_device_name,
            start_date,
            end_date,
            resolution,
        )

    pipeline.extend([{"$skip": offset}, {"$limit": size}])

    db = get_open_sensor_db()
    collection = db[collection_name]
    raw_data = list(collection.aggregate(pipeline))

    # Add UTC offset to timestamp field
    for item in raw_data:
        item["timestamp"] = item["timestamp"].replace(tzinfo=timezone.utc).isoformat()

    if response_model is VPD:
        # If the response model is VPD, you already have VPD-related data from the pipeline.
        # So, you can directly use it to create the response model instances.
        data = [VPD(**item) for item in raw_data]
    else:
        data_field = model_class_attributes[response_model]
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

        # TODO - Refactor this after migration to FreeTier complete
        user = get_user_from_fief_user(fief_user)
        if user:
            collection_name = user.collection_name
        else:
            collection_name = "FreeTier"

        return sample_and_paginate_collection(
            entity,
            collection_name,
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
            page=page,
            size=size,
            unit=unit,
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
router.add_api_route(
    "/VPD/{device_id}",
    create_historical_data_route(VPD),
    response_model=Page[VPD],
    methods=["GET"],
)


@router.post("/environment/")
async def record_environment(
    environment: Environment,
    user: User = Depends(validate_environment),
):
    db = get_open_sensor_db()

    # Paid customers may have their own collection
    if user:
        collection_name = user.collection_name
    else:
        collection_name = "FreeTier"
    migration_finished = migration_complete(collection_name)
    if migration_finished:
        _record_data_to_ts_collection(db.FreeTier, environment, user)
        return Response(status_code=status.HTTP_201_CREATED)

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

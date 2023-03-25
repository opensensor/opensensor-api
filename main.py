from datetime import datetime, timedelta
from decimal import Decimal
from typing import Generic, Type, TypeVar

from fastapi import FastAPI, Path, Query
from fastapi_pagination import add_pagination
from fastapi_pagination.default import Page as BasePage
from fastapi_pagination.default import Params as BaseParams
from pydantic import BaseModel

from opensensor.utils import get_open_sensor_db

T = TypeVar("T", bound=BaseModel)

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Welcome to OpenSensor.io!  Navigate to /docs for current Alpha API spec."}


class Params(BaseParams):
    size: int = Query(50, ge=1, le=1000, description="Page size")


class Page(BasePage[T], Generic[T]):
    __params_type__ = Params


class TimestampModel(BaseModel):
    timestamp: datetime | None = None


class DeviceMetadata(BaseModel):
    device_id: str
    name: str | None = None


class Temperature(TimestampModel):
    temp: Decimal
    unit: str | None = None


class Humidity(TimestampModel):
    rh: Decimal


class Pressure(TimestampModel):
    pressure: Decimal
    unit: str | None = None


class Lux(TimestampModel):
    percent: Decimal


class CO2(TimestampModel):
    ppm: Decimal


class Environment(BaseModel):
    device_metadata: DeviceMetadata
    temp: Temperature | None = None
    rh: Humidity | None = None
    pressure: Pressure | None = None
    lux: Lux | None = None
    co2: CO2 | None = None


def _record_data_point_to_ts_collection(
    collection, ts_column_name: str, device_metadata: DeviceMetadata, data_point
):
    metadata = device_metadata.dict()
    if hasattr(data_point, "unit"):
        metadata["unit"] = data_point.unit
    data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata,
        ts_column_name: str(getattr(data_point, ts_column_name)),
    }
    collection.insert_one(data)


@app.post("/rh/", response_model=Humidity)
async def record_humidity(device_metadata: DeviceMetadata, rh: Humidity):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Humidity, "rh", device_metadata, rh)
    return rh.dict()


@app.post("/temp/", response_model=Temperature)
async def record_temperature(device_metadata: DeviceMetadata, temp: Temperature):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Temperature, "temp", device_metadata, temp)
    return temp.dict()


@app.post("/pressure/", response_model=Pressure)
async def record_pressure(device_metadata: DeviceMetadata, pressure: Pressure):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Pressure, "pressure", device_metadata, pressure)
    return pressure.dict()


@app.post("/lux/", response_model=Lux)
async def record_lux(device_metadata: DeviceMetadata, lux: Lux):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.Lux, "percent", device_metadata, lux)
    return lux.dict()


@app.post("/CO2/", response_model=CO2)
async def record_CO2(device_metadata: DeviceMetadata, co2: CO2):
    db = get_open_sensor_db()
    _record_data_point_to_ts_collection(db.CO2, "ppm", device_metadata, co2)
    return co2.dict()


def _get_project_projection(response_model: Type[T]):
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


def get_uniform_sample_pipeline(
    response_model: Type[T],
    device_id: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
):
    sampling_interval = timedelta(minutes=resolution)
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=100)
    if end_date is None:
        end_date = datetime.utcnow()

    # Query a uniform sample of documents within the timestamp range
    pipeline = [
        {
            "$match": {
                "timestamp": {"$gte": start_date, "$lte": end_date},
                "metadata.device_id": device_id,
            }
        },
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
        {"$project": _get_project_projection(response_model)},
        {"$sort": {"timestamp": 1}},  # Sort by timestamp in ascending order
        # {"$count": "total"}
    ]
    return pipeline


def sample_and_paginate_collection(
    response_model: Type[T],
    device_id: str,
    start_date: datetime,
    end_date: datetime,
    resolution: int,
    page: int,
    size: int,
):
    offset = (page - 1) * size
    pipeline = get_uniform_sample_pipeline(
        response_model, device_id, start_date, end_date, resolution
    )
    pipeline.extend([{"$skip": offset}, {"$limit": size}])

    db = get_open_sensor_db()
    collection = db[response_model.__name__]
    data = list(collection.aggregate(pipeline))
    # Re-run for total page count
    pipeline.append({"$count": "total"})
    data_count = list(collection.aggregate(pipeline))
    total_count = data_count[0]["total"] if data else 0
    return Page(items=data, total=total_count, page=page, size=size)


async def historical_data_route(
    entity: Type[T],
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    resolution: int = 30,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(50, ge=1, le=1000, description="Page size"),
) -> Page[T]:
    return sample_and_paginate_collection(
        entity,
        device_id=device_id,
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        page=page,
        size=size,
    )


def create_historical_data_route(entity: Type[T]):
    async def historical_data_route(
        device_id: str = Path(
            title="The ID of the device about which to retrieve historical data."
        ),
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        resolution: int = 30,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        size: int = Query(50, ge=1, le=1000, description="Page size"),
    ) -> Page[T]:
        return sample_and_paginate_collection(
            entity,
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
            page=page,
            size=size,
        )

    return historical_data_route


app.add_api_route(
    "/temp/{device_id}",
    create_historical_data_route(Temperature),
    response_model=Page[Temperature],
    methods=["GET"],
)
app.add_api_route(
    "/humidity/{device_id}",
    create_historical_data_route(Humidity),
    response_model=Page[Humidity],
    methods=["GET"],
)
app.add_api_route(
    "/CO2/{device_id}", create_historical_data_route(CO2), response_model=Page[CO2], methods=["GET"]
)


@app.post("/environment/", response_model=Environment)
async def record_environment(environment: Environment):
    db = get_open_sensor_db()
    if environment.temp:
        _record_data_point_to_ts_collection(
            db.Temperature, "temp", environment.device_metadata, environment.temp
        )
    if environment.rh:
        _record_data_point_to_ts_collection(
            db.Humidity, "rh", environment.device_metadata, environment.rh
        )
    if environment.pressure:
        _record_data_point_to_ts_collection(
            db.Pressure, "pressure", environment.device_metadata, environment.pressure
        )
    if environment.lux:
        _record_data_point_to_ts_collection(
            db.Lux, "percent", environment.device_metadata, environment.lux
        )
    if environment.co2:
        _record_data_point_to_ts_collection(
            db.CO2, "ppm", environment.device_metadata, environment.co2
        )

    return environment.dict()


add_pagination(app)

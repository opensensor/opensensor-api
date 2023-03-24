from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI, Path, Query
from fastapi_pagination import Page, Params, add_pagination
from fastapi_pagination.ext.pymongo import paginate as pymongo_paginate
from pydantic import BaseModel

from opensensor.utils import get_open_sensor_db

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Welcome to OpenSensor.io!  Navigate to /docs for current Alpha API spec."}


class DeviceMetadata(BaseModel):
    device_id: str
    name: str | None = None


class Temperature(BaseModel):
    temp: Decimal
    unit: str | None = None
    timestamp: datetime | None = None


class Humidity(BaseModel):
    rh: Decimal


class Pressure(BaseModel):
    pressure: Decimal
    unit: str | None = None


class Lux(BaseModel):
    percent: Decimal


class CO2(BaseModel):
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


@app.get("/temp/{device_id}", response_model=Page[Temperature])
async def historical_temperatures(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
):
    db = get_open_sensor_db()
    matching_data = pymongo_paginate(
        db.Temperature,
        {"metadata.device_id": device_id},
        projection={
            "_id": False,
            "unit": "$metadata.unit",
            "temp": "$temp",
            "timestamp": "$timestamp",
        },
    )
    return matching_data


def get_uniform_sample_pipeline(device_id: str, start_date: datetime, end_date: datetime):
    sampling_interval = timedelta(minutes=20)  # Adjust the sampling interval as needed

    # Query a uniform sample of documents within the timestamp range
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}, "metadata.device_id": device_id}},
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
        {
            "$project": {
                "_id": False,
                "unit": "$metadata.unit",
                "temp": "$temp",
                "timestamp": "$timestamp",  # Don't forget to include the timestamp field
            }
        },
        {"$sort": {"timestamp": 1}},  # Sort by timestamp in ascending order
        # {"$count": "total"}
    ]
    return pipeline


@app.get("/sampled-temp/{device_id}", response_model=Page[Temperature])
async def historical_temperatures_sampled(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(50, ge=1, le=100, description="Page size"),
):
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=100)
    if end_date is None:
        end_date = datetime.utcnow()
    pipeline = get_uniform_sample_pipeline(device_id, start_date, end_date)

    offset = (page - 1) * size

    # Add $skip and $limit stages for pagination
    pipeline.extend([{"$skip": offset}, {"$limit": size}])
    db = get_open_sensor_db()
    data = list(db.Temperature.aggregate(pipeline))
    pipeline.append({"$count": "total"})
    data_count = list(db.Temperature.aggregate(pipeline))
    total_count = data_count[0]["total"] if data else 0
    print(data)
    return Page(items=data, total=total_count, page=page, size=size)


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

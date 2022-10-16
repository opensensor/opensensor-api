from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, Path
from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.pymongo import paginate
from pydantic import BaseModel

from opensensor.utils import get_open_sensor_db

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


class DeviceMetadata(BaseModel):
    device_id: str
    name: str | None = None


class Temperature(BaseModel):
    temp: Decimal
    unit: str | None = None


class Humidity(BaseModel):
    rh: Decimal


class Environment(BaseModel):
    device_metadata: DeviceMetadata
    temp: Temperature | None = None
    rh: Humidity | None = None


def _record_data_point_to_ts_collection(
    collection, ts_column_name: str, device_metadata: DeviceMetadata, data_point
):
    metadata = device_metadata.dict()
    if hasattr(data_point, "unit"):
        metadata["unit"] = data_point.unit
    data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata,
        ts_column_name: getattr(data_point, ts_column_name),
    }
    collection.insert_one(data)


@app.post("/rh/", response_model=Humidity)
async def record_humidity(device_metadata: DeviceMetadata, rh: Humidity):
    db = get_open_sensor_db()
    rhs = db.Humidity
    _record_data_point_to_ts_collection(rhs, "rh", device_metadata, rh)
    return rh.dict()


@app.post("/temp/", response_model=Temperature)
async def record_temperature(device_metadata: DeviceMetadata, temp: Temperature):
    db = get_open_sensor_db()
    temps = db.Temperature
    _record_data_point_to_ts_collection(temps, "temp", device_metadata, temp)
    return temp.dict()


@app.get("/temp/{device_id}", response_model=Page[Temperature])
async def historical_temperatures(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
):
    db = get_open_sensor_db()
    matching_data = paginate(
        db.Temperature,
        {"metadata.device_id": device_id},
        projection={"_id": False, "unit": "$metadata.unit", "temp": "$temp"},
    )
    return matching_data


@app.post("/environment/", response_model=Environment)
async def record_environment(environment: Environment):
    db = get_open_sensor_db()
    if environment.temp:
        temps = db.Temperature
        _record_data_point_to_ts_collection(
            temps, "temp", environment.device_metadata, environment.temp
        )
    if environment.rh:
        rhs = db.Humidity
        _record_data_point_to_ts_collection(rhs, "rh", environment.device_metadata, environment.rh)
    return environment.dict()


add_pagination(app)

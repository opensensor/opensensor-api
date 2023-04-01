import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generic, List, Type, TypeVar

from pydantic import BaseModel, validator


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


class PH(TimestampModel):
    pH: Decimal

    @classmethod
    def collection_name(cls):
        return "pH"


class Moisture(TimestampModel):
    readings: List[float | Decimal | int] | str

    @validator("readings")
    def parse_readings(cls, value):
        if isinstance(value, str):
            value = value.replace("Decimal('", "").replace("')", "")
            return json.loads(value)
        return value


class Environment(BaseModel):
    device_metadata: DeviceMetadata
    temp: Temperature | None = None
    rh: Humidity | None = None
    pressure: Pressure | None = None
    lux: Lux | None = None
    co2: CO2 | None = None
    moisture: Moisture | None = None
    pH: PH | None = None

import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class TimestampModel(BaseModel):
    timestamp: datetime | None = None


class DeviceMetadata(BaseModel):
    device_id: str
    name: str | None = None
    api_key: str | None = None


class Temperature(TimestampModel):
    temp: Decimal
    unit: str | None = None

    @classmethod
    def collection_name(cls):
        return "temp"


class Humidity(TimestampModel):
    rh: Decimal


class Pressure(TimestampModel):
    pressure: Decimal
    unit: str | None = None


class Lux(TimestampModel):
    lux: Decimal


class CO2(TimestampModel):
    ppm: Decimal


class PH(TimestampModel):
    pH: Decimal

    @classmethod
    def collection_name(cls):
        return "pH"


class LiquidLevel(TimestampModel):
    """Liquid Level Sensor output"""

    liquid: bool

    @classmethod
    def collection_name(cls):
        return "liquid"


class RelayStatus(BaseModel):
    position: int
    enabled: bool
    seconds: int | None = None
    description: str | None = None


class RelayBoard(TimestampModel):
    """Relay Board control tracking"""

    relays: List[RelayStatus]

    @classmethod
    def collection_name(cls):
        return "relays"


class PumpStatus(BaseModel):
    position: int
    enabled: bool
    speed: float | None = None
    duration: float | None = None
    timestamp: float | None = None
    description: str | None = None


class PumpBoard(TimestampModel):
    """Pump activity tracking"""

    pumps: List[PumpStatus]

    @classmethod
    def collection_name(cls):
        return "pumps"


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
    liquid: LiquidLevel | None = None
    relays: RelayBoard | None = None
    pumps: PumpBoard | None = None


class VPD(BaseModel):
    """
    VPD is a Computed Projection from other data points.
    """

    timestamp: datetime
    vpd: Optional[float] = Field(None, description="The computed VPD value.")

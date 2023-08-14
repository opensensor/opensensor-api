from decimal import Decimal

from opensensor.collections import Temperature


def convert_temperature(temp: Temperature, desired_unit: str) -> Temperature:
    if temp.unit == desired_unit or not temp.unit:
        return temp
    elif temp.unit == "C" and desired_unit == "F":
        temp.temp = Decimal(temp.temp * 9 / 5 + 32)
    elif temp.unit == "C" and desired_unit == "K":
        temp.temp = Decimal(temp.temp + Decimal(273.15))
    elif temp.unit == "F" and desired_unit == "C":
        temp.temp = Decimal((temp.temp - 32) * 5 / 9)
    elif temp.unit == "F" and desired_unit == "K":
        temp.temp = Decimal((temp.temp + Decimal(459.67)) * 5 / 9)
    elif temp.unit == "K" and desired_unit == "C":
        temp.temp = Decimal(temp.temp - Decimal(273.15))
    elif temp.unit == "K" and desired_unit == "F":
        temp.temp = Decimal(temp.temp * 9 / 5 - Decimal(459.67))
    else:
        raise ValueError(f"Unsupported temperature unit conversion: {temp.unit} to {desired_unit}")
    temp.unit = desired_unit

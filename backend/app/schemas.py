from pydantic import BaseModel, Field, field_validator
from typing import Literal
import re

class PlantCreate(BaseModel):
    plant_id: str = Field(min_length=1, max_length=48, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=80)
    species: str = Field(default='', max_length=100)
    growth_stage: str = Field(default='', max_length=80)
    ideal_moisture_min: float = Field(default=30, ge=0, le=100)
    ideal_moisture_max: float = Field(default=65, ge=0, le=100)
    light_needs: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

class PlantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    species: str | None = Field(default=None, max_length=100)
    growth_stage: str | None = Field(default=None, max_length=80)
    ideal_moisture_min: float | None = Field(default=None, ge=0, le=100)
    ideal_moisture_max: float | None = Field(default=None, ge=0, le=100)
    light_needs: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

class ModeUpdate(BaseModel):
    mode: Literal['auto','manual']

class WaterRequest(BaseModel):
    duration_seconds: int = Field(default=5, ge=1, le=15)
    reason: str = Field(default='Manual watering', max_length=200)

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)

class TelemetryIngest(BaseModel):
    soil_surface: float | None = Field(default=None, ge=0, le=100)
    soil_mid: float | None = Field(default=None, ge=0, le=100)
    soil_root: float | None = Field(default=None, ge=0, le=100)
    temperature_c: float | None = Field(default=None, ge=-40, le=85)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    leaf_wetness_pct: float | None = Field(default=None, ge=0, le=100)
    device_status: Literal['idle', 'watering'] | None = None

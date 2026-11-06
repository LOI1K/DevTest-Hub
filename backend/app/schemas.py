from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EnvironmentTemplate(str, Enum):
    nginx = "nginx"
    fastapi_postgres = "fastapi-postgres"


class EnvironmentCreate(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=40,
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    )
    template: EnvironmentTemplate


class EnvironmentUpdate(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=40,
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    )


class EnvironmentStatus(str, Enum):
    pending = "pending"
    running = "running"
    stopped = "stopped"
    failed = "failed"


class EnvironmentResponse(EnvironmentCreate):
    id: int
    status: EnvironmentStatus

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class UserRegister(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

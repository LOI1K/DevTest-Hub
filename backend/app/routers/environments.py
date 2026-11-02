from itertools import count

from fastapi import APIRouter, status

from app.schemas import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentStatus,
)


router = APIRouter(
    prefix="/api/v1/environments",
    tags=["Environments"],
)

environments: dict[int, EnvironmentResponse] = {}
environment_ids = count(1)


@router.get("", response_model=list[EnvironmentResponse])
def get_environments():
    return list(environments.values())


@router.post(
    "",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(data: EnvironmentCreate):
    environment = EnvironmentResponse(
        id=next(environment_ids),
        name=data.name,
        template=data.template,
        status=EnvironmentStatus.pending,
    )

    environments[environment.id] = environment

    return environment

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Environment
from app.schemas import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentStatus,
    EnvironmentUpdate,
)


router = APIRouter(
    prefix="/api/v1/environments",
    tags=["Environments"],
)

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[EnvironmentResponse])
def get_environments(db: DbSession):
    statement = select(Environment).order_by(Environment.id)
    return db.scalars(statement).all()


@router.post(
    "",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(data: EnvironmentCreate, db: DbSession):
    environment = Environment(
        name=data.name,
        template=data.template.value,
        status=EnvironmentStatus.pending.value,
    )

    db.add(environment)
    db.commit()
    db.refresh(environment)

    return environment


@router.get(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
def get_environment(environment_id: int, db: DbSession):
    environment = db.get(Environment, environment_id)

    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    return environment


@router.patch(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
def update_environment(
    environment_id: int,
    data: EnvironmentUpdate,
    db: DbSession,
):
    environment = db.get(Environment, environment_id)

    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    environment.name = data.name

    db.commit()
    db.refresh(environment)

    return environment


@router.delete(
    "/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_environment(
    environment_id: int,
    db: DbSession,
):
    environment = db.get(Environment, environment_id)

    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    db.delete(environment)
    db.commit()

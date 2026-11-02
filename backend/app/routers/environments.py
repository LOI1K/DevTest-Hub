from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Environment
from app.schemas import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentStatus,
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

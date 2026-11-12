import os

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Environment, User
from app.schemas import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentStatus,
    EnvironmentUpdate,
    EnvironmentTemplate,
)


router = APIRouter(
    prefix="/api/v1/environments",
    tags=["Environments"],
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def find_owned_environment(
    environment_id: int,
    user_id: int,
    db: Session,
    *,
    for_update: bool = False,
) -> Environment:
    statement = select(Environment).where(
        Environment.id == environment_id,
        Environment.owner_id == user_id,
    )

    if for_update:
        statement = statement.with_for_update()

    environment = db.scalar(statement)

    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    return environment


@router.get("", response_model=list[EnvironmentResponse])
def get_environments(db: DbSession, current_user: CurrentUser):
    statement = (
        select(Environment)
        .where(Environment.owner_id == current_user.id)
        .order_by(Environment.id)
    )

    return db.scalars(statement).all()


@router.post(
    "",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    data: EnvironmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    if (
        data.template == EnvironmentTemplate.fastapi_postgres
        and os.getenv(
            "DEVTEST_HUB_ENABLE_FASTAPI_POSTGRES", "0"
        ) != "1"
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "FastAPI + PostgreSQL template "
                "is temporarily unavailable"
            ),
        )
    environment = Environment(
        name=data.name,
        template=data.template.value,
        status=EnvironmentStatus.pending.value,
        owner_id=current_user.id,
    )

    db.add(environment)
    db.commit()
    db.refresh(environment)

    return environment


@router.get(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
def get_environment(
    environment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    return find_owned_environment(
        environment_id,
        current_user.id,
        db,
    )


@router.patch(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
def update_environment(
    environment_id: int,
    data: EnvironmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    environment = find_owned_environment(
        environment_id,
        current_user.id,
        db,
    )

    environment.name = data.name

    db.commit()
    db.refresh(environment)

    return environment


@router.delete(
    "/{environment_id}",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)

def delete_environment(
    environment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    delete_volume: bool = Query(
        default=False,
        description=(
            "Explicitly confirm permanent deletion "
            "of the FastAPI PostgreSQL data volume"
        ),
    ),
):
    environment = find_owned_environment(
        environment_id,
        current_user.id,
        db,
        for_update=True,
    )

    if environment.status == EnvironmentStatus.deploying.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Environment deployment is in progress",
        )

    changed = False

    if environment.template == EnvironmentTemplate.fastapi_postgres.value:
        if not (
            delete_volume
            or environment.delete_volume_on_delete
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Permanent PostgreSQL data deletion "
                    "requires delete_volume=true"
                ),
            )

        if delete_volume and not environment.delete_volume_on_delete:
            environment.delete_volume_on_delete = True
            changed = True

    elif delete_volume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This template does not have a data volume",
        )

    if environment.status != EnvironmentStatus.deleting.value:
        environment.status = EnvironmentStatus.deleting.value
        changed = True

    if changed:
        db.commit()
        db.refresh(environment)

    return environment

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserRegister, UserResponse
from app.security import hash_password

from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.schemas import TokenResponse
from app.security import (
    DUMMY_HASH,
    create_access_token,
    verify_password,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(data: UserRegister, db: DbSession):
    user = User(
        username=data.username,
        email=str(data.email),
        password_hash=hash_password(data.password),
        role="developer",
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        ) from exc

    return user


@router.post("/login", response_model=TokenResponse)
def login_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    statement = select(User).where(
        User.username == form_data.username
    )

    user = db.scalar(statement)

    stored_hash = user.password_hash if user else DUMMY_HASH
    valid_password = verify_password(
        form_data.password,
        stored_hash,
    )

    if not user or not valid_password or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
    )

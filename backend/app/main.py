from fastapi import FastAPI

from app.schemas import HealthResponse
from app.routers.environments import router as environments_router
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router


app = FastAPI(
    title="DevTest Hub API",
    version="0.1.0"
)

app.include_router(environments_router)
app.include_router(auth_router)
app.include_router(users_router)

@app.get("/api/v1/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="devtest-hub-api"
    )

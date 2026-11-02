from fastapi import FastAPI

from app.schemas import HealthResponse
from app.routers.environments import router as environments_router


app = FastAPI(
    title="DevTest Hub API",
    version="0.1.0"
)

app.include_router(environments_router)


@app.get("/api/v1/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="devtest-hub-api"
    )

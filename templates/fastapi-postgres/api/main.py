import os
import time
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "appdb"),
        user=os.getenv("DB_USER", "appuser"),
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
        row_factory=dict_row,
    )


def initialize_database():
    for attempt in range(30):
        try:
            with get_connection() as connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS notes (
                        id BIGINT GENERATED ALWAYS AS IDENTITY
                            PRIMARY KEY,
                        content TEXT NOT NULL
                    )
                """)
            return

        except psycopg.OperationalError:
            if attempt == 29:
                raise

            time.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="DevTest Hub Test API",
    description="FastAPI test environment with PostgreSQL",
    version="1.0.0",
    lifespan=lifespan,
)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=200)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")

        return {
            "status": "ready",
            "database": "connected",
        }

    except psycopg.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from error


@app.get("/notes")
def list_notes():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, content
                FROM notes
                ORDER BY id
            """)

            notes = cursor.fetchall()

    return {"items": notes}


@app.post("/notes", status_code=201)
def create_note(note: NoteCreate):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notes (content)
                VALUES (%s)
                RETURNING id, content
                """,
                (note.content,),
            )

            created = cursor.fetchone()

    return created

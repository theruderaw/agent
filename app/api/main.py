from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.features.runs import router as runs_router
from app.db.database import init_db

app = FastAPI()

init_db()

app.include_router(
    router=runs_router
)
app.mount(
    "/",
    StaticFiles(directory="static", html=True),
    name="static",
)

"""FastAPI entry point and REST endpoints for task lifecycle management."""
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Task
from .schemas import TaskCreate, TaskRead, TaskUpdate


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Phase 2 bootstrap: create missing tables. Replace with Alembic migrations
    # before production deployment so schema changes are controlled and reversible.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Three-Tier Task API", version="0.2.1", lifespan=lifespan)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    # A database round-trip proves the API can reach its persistence layer.
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    # Deterministic ordering makes the UI and automated tests predictable.
    return db.scalars(select(Task).order_by(Task.id.desc())).all()


@app.post("/api/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()  # Commit before returning so subsequent requests see the task.
    db.refresh(task)
    return task


def find_task(db: Session, task_id: int) -> Task:
    # Centralize 404 behavior so GET/PATCH/DELETE behave consistently.
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    return find_task(db, task_id)


@app.patch("/api/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = find_task(db, task_id)
    # Exclude unset values to preserve fields the caller did not want to change.
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db.delete(find_task(db, task_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

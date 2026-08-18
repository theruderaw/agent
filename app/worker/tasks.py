import asyncio
import logging
from uuid import UUID

from app.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="execute_run", bind=True, max_retries=0)
def execute_run_task(self, run_id: str, user_input: str | None = None) -> dict:
    """Execute an agent run.

    This is a sync Celery task that wraps the async runtime via asyncio.run().
    The runtime creates its own DB session from async_session_factory.
    """
    try:
        asyncio.run(_execute_run(run_id, user_input))
        return {"run_id": run_id, "status": "completed"}
    except Exception:
        logger.exception("execute_run failed for run_id=%s", run_id)
        asyncio.run(_mark_failed(run_id, str(self.request.exc_info[1])))
        return {"run_id": run_id, "status": "failed"}


async def _execute_run(run_id: str, user_input: str | None) -> None:
    import httpx

    from app.core import settings
    from app.db.database import async_session_factory
    from app.llm.qwen import Qwen
    from app.runtime.runtime import execute_run
    from app.skills.loader import SkillLoader
    from app.tools.registry import build_registry

    async with async_session_factory() as session:
        llm = Qwen(
            client=httpx.AsyncClient(),
            url=settings.ollama_url,
            model=settings.ollama_base_model,
        )
        registry = build_registry()
        skill_loader = SkillLoader(skills_dir="docs")

        await execute_run(
            run_id=UUID(run_id),
            session=session,
            llm=llm,
            registry=registry,
            skill_loader=skill_loader,
            user_input=user_input,
        )


async def _mark_failed(run_id: str, error: str) -> None:
    from app.db.database import async_session_factory
    from app.db.repository import RunRepository

    async with async_session_factory() as session:
        repo = RunRepository(session)
        try:
            await repo.set_run_failed(UUID(run_id), error)
            await session.commit()
        except Exception:
            logger.exception("Failed to mark run %s as failed", run_id)

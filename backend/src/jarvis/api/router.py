from fastapi import APIRouter

from jarvis import __version__

router = APIRouter(prefix="/api/v1")


@router.get("/version", tags=["metadata"])
async def version() -> dict[str, str]:
    return {"name": "jarvis-personal-assistant", "version": __version__}

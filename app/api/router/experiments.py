import os
from hmac import compare_digest

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.schemas import RemoteExperimentRequest
from eval.langfuse.webhook.main_agent_experiment import DATASET_NAME, run_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("/langfuse/remote", status_code=status.HTTP_202_ACCEPTED)
async def trigger_langfuse_experiment(
    request: RemoteExperimentRequest,
    background_tasks: BackgroundTasks,
    secret: str | None = Query(default=None),
) -> dict[str, str]:
    expected_secret = os.getenv("LANGFUSE_REMOTE_EXPERIMENT_SECRET")
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Remote experiment trigger is not configured.",
        )
    if secret is None or not compare_digest(secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid remote experiment secret.",
        )

    if request.dataset_name != DATASET_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This endpoint only supports dataset {DATASET_NAME!r}.",
        )

    background_tasks.add_task(
        run_experiment,
        dataset_name=request.dataset_name,
        dataset_id=request.dataset_id,
        config=request.config.model_dump(exclude_none=True),
    )
    return {
        "status": "accepted",
        "datasetName": request.dataset_name,
        "datasetId": request.dataset_id,
    }

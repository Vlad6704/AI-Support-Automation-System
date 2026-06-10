from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RemoteExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    experiment_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("experimentName", "experiment_name"),
    )
    run_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("runName", "run_name"),
    )
    max_concurrency: int = Field(
        default=5,
        ge=1,
        le=50,
        validation_alias=AliasChoices("maxConcurrency", "max_concurrency"),
    )
    metadata: dict[str, str] = Field(default_factory=dict)


class RemoteExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset_id: str = Field(
        validation_alias=AliasChoices("datasetId", "dataset_id"),
    )
    dataset_name: str = Field(
        validation_alias=AliasChoices("datasetName", "dataset_name"),
    )
    config: RemoteExperimentConfig = Field(default_factory=RemoteExperimentConfig)

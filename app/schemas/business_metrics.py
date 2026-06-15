from pydantic import BaseModel


class RateMetric(BaseModel):
    count: int
    eligible_count: int
    rate: float | None


class RunDurationMetrics(BaseModel):
    sample_count: int
    p01_ms: float | None
    median_ms: float | None


class AgentBusinessMetrics(BaseModel):
    tickets_agent_involved: int
    tickets_handled_automatically: int
    tickets_handled_with_human_review: int
    tickets_accepted_without_editing: int
    potential_time_saved_minutes: float
    manual_handling_baseline_minutes: float
    total_model_cost: float
    runs_with_recorded_cost: int
    run_duration: RunDurationMetrics
    sla_compliance: RateMetric
    one_message_resolution: RateMetric
    repeat_contact: RateMetric
    measurement_notes: list[str]

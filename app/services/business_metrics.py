from datetime import datetime, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AgentRunHumanReviewResult, AgentRunOutcome, MessageSource
from app.models import AgentRun, Message, Subscription, TicketEvent, TicketHistory
from app.schemas.business_metrics import (
    AgentBusinessMetrics,
    RateMetric,
    RunDurationMetrics,
)


class AgentBusinessMetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_metrics(
        self,
        *,
        manual_handling_baseline_minutes: float,
    ) -> AgentBusinessMetrics:
        runs = list(self.db.scalars(select(AgentRun)).all())
        tickets = list(self.db.scalars(select(TicketHistory)).all())
        events = list(self.db.scalars(select(TicketEvent)).all())
        messages = list(self.db.scalars(select(Message)).all())
        subscriptions = list(
            self.db.scalars(select(Subscription).order_by(Subscription.id.desc())).all()
        )

        involved_ticket_ids = {run.ticket_id for run in runs}
        reviewed_ticket_ids = {
            run.ticket_id
            for run in runs
            if run.human_review_result is not None
        }
        automated_ticket_ids = {
            run.ticket_id
            for run in runs
            if run.outcome == AgentRunOutcome.AUTOMATED
        } - reviewed_ticket_ids
        accepted_without_editing_ticket_ids = {
            run.ticket_id
            for run in runs
            if run.human_review_result
            == AgentRunHumanReviewResult.ACCEPTED_WITHOUT_EDITING
        }

        durations_ms = sorted(
            (_utc(run.completed_at) - _utc(run.started_at)).total_seconds() * 1000
            for run in runs
            if run.completed_at is not None
        )
        costs = [float(run.model_cost) for run in runs if run.model_cost is not None]

        first_response_by_ticket = _first_response_times(events)
        user_messages_by_ticket = _user_messages_by_ticket(messages)

        response_ticket_ids = set(first_response_by_ticket)
        repeat_contact_ticket_ids = {
            ticket_id
            for ticket_id, response_at in first_response_by_ticket.items()
            if any(
                _utc(message.created_at) > response_at
                for message in user_messages_by_ticket.get(ticket_id, [])
            )
        }
        one_message_resolution_ticket_ids = {
            ticket_id
            for ticket_id in response_ticket_ids
            if len(user_messages_by_ticket.get(ticket_id, [])) == 1
            and ticket_id not in repeat_contact_ticket_ids
        }

        sla_by_customer: dict[int, int] = {}
        for subscription in subscriptions:
            sla_by_customer.setdefault(
                subscription.customer_id,
                subscription.sla_response_time_minutes,
            )
        sla_eligible = 0
        sla_compliant = 0
        for ticket in tickets:
            response_at = first_response_by_ticket.get(ticket.id)
            sla_minutes = sla_by_customer.get(ticket.customer_id)
            if response_at is None or sla_minutes is None:
                continue
            sla_eligible += 1
            response_minutes = (
                response_at - _utc(ticket.created_at)
            ).total_seconds() / 60
            if response_minutes <= sla_minutes:
                sla_compliant += 1

        return AgentBusinessMetrics(
            tickets_agent_involved=len(involved_ticket_ids),
            tickets_handled_automatically=len(automated_ticket_ids),
            tickets_handled_with_human_review=len(reviewed_ticket_ids),
            tickets_accepted_without_editing=len(
                accepted_without_editing_ticket_ids
            ),
            potential_time_saved_minutes=round(
                len(automated_ticket_ids) * manual_handling_baseline_minutes,
                2,
            ),
            manual_handling_baseline_minutes=manual_handling_baseline_minutes,
            total_model_cost=round(sum(costs), 6),
            runs_with_recorded_cost=len(costs),
            run_duration=RunDurationMetrics(
                sample_count=len(durations_ms),
                p01_ms=_percentile(durations_ms, 0.01),
                median_ms=round(median(durations_ms), 2) if durations_ms else None,
            ),
            sla_compliance=_rate_metric(sla_compliant, sla_eligible),
            one_message_resolution=_rate_metric(
                len(one_message_resolution_ticket_ids),
                len(response_ticket_ids),
            ),
            repeat_contact=_rate_metric(
                len(repeat_contact_ticket_ids),
                len(response_ticket_ids),
            ),
            measurement_notes=[
                (
                    "Potential time saved equals automatically handled tickets "
                    "multiplied by manual_handling_baseline_minutes."
                ),
                (
                    "One-message resolution is a proxy: exactly one customer message "
                    "and no customer message after the first agent response."
                ),
                (
                    "Repeat contact means a customer message was received after the "
                    "first agent response."
                ),
                (
                    "SLA compliance compares ticket creation to the first response_sent "
                    "event using the customer's latest subscription SLA."
                ),
                "Total model cost includes only runs with a recorded model_cost.",
            ],
        )


def _first_response_times(events: list[TicketEvent]) -> dict[int, datetime]:
    first_response_by_ticket: dict[int, datetime] = {}
    for event in events:
        if event.event_type != "response_sent":
            continue
        event_at = _utc(event.created_at)
        current = first_response_by_ticket.get(event.ticket_id)
        if current is None or event_at < current:
            first_response_by_ticket[event.ticket_id] = event_at
    return first_response_by_ticket


def _user_messages_by_ticket(messages: list[Message]) -> dict[int, list[Message]]:
    grouped: dict[int, list[Message]] = {}
    for message in messages:
        if message.source == MessageSource.USER:
            grouped.setdefault(message.ticket_id, []).append(message)
    return grouped


def _rate_metric(count: int, eligible_count: int) -> RateMetric:
    return RateMetric(
        count=count,
        eligible_count=eligible_count,
        rate=round(count / eligible_count, 4) if eligible_count else None,
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    position = (len(values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    value = values[lower_index] + (values[upper_index] - values[lower_index]) * weight
    return round(value, 2)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

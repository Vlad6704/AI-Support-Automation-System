import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


API_LOG_COUNT = 500
DELIVERY_LOG_COUNT = 1_500
CUSTOMER_ID = 2
WEBHOOK_ENDPOINT_ID = 2
FAILURE_RATE = 0.10
START_TIME = datetime.fromisoformat("2026-06-01T00:00:00.000000")


def next_id(rows: list[dict[str, Any]]) -> int:
    return max((row["id"] for row in rows), default=0) + 1


def generate_world(source_path: Path, output_path: Path, seed: int) -> None:
    world: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
    rng = random.Random(seed)

    api_logs: list[dict[str, Any]] = world["api_usage_logs"]
    delivery_logs: list[dict[str, Any]] = world["webhook_delivery_logs"]
    api_id = next_id(api_logs)
    delivery_id = next_id(delivery_logs)

    generated_events: list[tuple[str, datetime]] = []
    for offset in range(API_LOG_COUNT):
        event_type = rng.choice(("order.created", "payment.failed"))
        created_at = START_TIME + timedelta(minutes=offset * 20)
        sequence = api_id + offset
        payload: dict[str, Any] = {"order_id": f"ord_generated_{sequence}"}
        if event_type == "order.created":
            payload["amount"] = round(rng.uniform(10, 500), 2)
        else:
            payload.update(
                {
                    "payment_id": f"pay_generated_{sequence}",
                    "reason": rng.choice(("card_declined", "insufficient_funds")),
                }
            )

        api_logs.append(
            {
                "id": sequence,
                "customer_id": CUSTOMER_ID,
                "event_type": event_type,
                "payload": payload,
                "created_at": created_at.isoformat(timespec="microseconds"),
            }
        )
        generated_events.append((event_type, created_at))

    failure_count = int(DELIVERY_LOG_COUNT * FAILURE_RATE)
    failed_offsets = set(rng.sample(range(DELIVERY_LOG_COUNT), failure_count))
    for offset in range(DELIVERY_LOG_COUNT):
        event_type, event_created_at = generated_events[offset // 3]
        created_at = event_created_at + timedelta(seconds=(offset % 3 + 1) * 5)
        failed = offset in failed_offsets
        last_attempt_at = created_at + timedelta(minutes=8) if failed else created_at

        delivery_logs.append(
            {
                "id": delivery_id + offset,
                "customer_id": CUSTOMER_ID,
                "event_type": event_type,
                "webhook_endpoint_id": WEBHOOK_ENDPOINT_ID,
                "status_code": 500 if failed else 200,
                "delivery_status": "failed" if failed else "delivered",
                "attempt_count": 3 if failed else 1,
                "error_message": (
                    "Internal server error from customer endpoint" if failed else None
                ),
                "created_at": created_at.isoformat(timespec="microseconds"),
                "last_attempt_at": last_attempt_at.isoformat(timespec="microseconds"),
            }
        )

    output_path.write_text(
        json.dumps(world, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    scenarios_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate world_2 from world_1.")
    parser.add_argument(
        "--source",
        type=Path,
        default=scenarios_dir / "world_1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=scenarios_dir / "world_2.json",
    )
    parser.add_argument("--seed", type=int, default=2)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_world(args.source, args.output, args.seed)

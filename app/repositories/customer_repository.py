from datetime import datetime
from typing import TypedDict

from app.db import SessionLocal
from app.models import Customer


class CustomerData(TypedDict):
    id: int
    company_name: str
    contact_email: str
    region: str | None
    plan: str | None
    status: str
    created_at: datetime


def get_customer_data_by_id(customer_id: int) -> CustomerData | None:
    db = SessionLocal()
    try:
        customer = db.get(Customer, customer_id)
        if customer is None:
            return None

        return {
            "id": customer.id,
            "company_name": customer.company_name,
            "contact_email": customer.contact_email,
            "region": customer.region,
            "plan": customer.plan,
            "status": customer.status,
            "created_at": customer.created_at,
        }
    finally:
        db.close()

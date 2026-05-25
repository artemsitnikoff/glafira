from uuid import UUID


def get_billing(company_id: UUID) -> dict:
    """Get billing information for company (MVP placeholder)"""
    # TODO(post-MVP): real billing integration; см. TZ-10 §3.7
    return {
        "plan": "MVP",
        "users_limit": 10,
        "candidates_limit": 1000,
        "billing_until": None,
    }
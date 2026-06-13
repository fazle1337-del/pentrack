from datetime import date

from app.models.enums import TERMINAL_STATUSES, FindingStatus


def compute_sla_status(due_date: date | None, status: FindingStatus) -> str:
    """Return 'In' or 'Out' of SLA.

    'Out' when the finding is unresolved and past its due date.
    'In' otherwise (including resolved findings or those with no due date).
    """
    if status in TERMINAL_STATUSES:
        return "In"
    if due_date is not None and due_date < date.today():
        return "Out"
    return "In"

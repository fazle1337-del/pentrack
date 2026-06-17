import enum


class Role(str, enum.Enum):
    admin = "admin"
    member = "member"


class AuthType(str, enum.Enum):
    sso = "sso"
    local = "local"


class BauOrProject(str, enum.Enum):
    bau = "BAU"
    project = "Project"


class EngagementStatus(str, enum.Enum):
    """Shared lifecycle for a test and its schedule bookings."""
    scheduled = "Scheduled"
    booked = "Booked"
    complete = "Complete"
    cancelled = "Cancelled"


class RiskRating(str, enum.Enum):
    critical = "Critical"
    high = "High"
    medium = "Medium"
    low = "Low"
    info = "Info"


class LikelihoodImpact(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"


class FindingStatus(str, enum.Enum):
    open = "Open"
    in_progress = "In Progress"
    remediated = "Remediated"
    verified = "Verified"
    closed = "Closed"
    transferred = "Transferred"
    accepted = "Accepted"
    duplicate = "Duplicate"


# Finding statuses considered "resolved" — used for SLA computation
TERMINAL_STATUSES = {
    FindingStatus.closed,
    FindingStatus.verified,
    FindingStatus.transferred,
    FindingStatus.accepted,
    FindingStatus.duplicate,
}

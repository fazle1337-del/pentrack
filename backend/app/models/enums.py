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


class TestStatus(str, enum.Enum):
    planned = "Planned"
    in_progress = "In Progress"
    completed = "Completed"


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

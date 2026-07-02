from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import (
    AuthType,
    BauOrProject,
    EngagementStatus,
    FindingStatus,
    LikelihoodImpact,
    RiskRating,
    Role,
)


# ---- Auth ----
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Teams ----
class TeamCreate(BaseModel):
    name: str


class TeamUpdate(BaseModel):
    name: str
    # EasyVista assignee-group id (2026-07-01). Omit to leave unchanged (so
    # existing rename-only callers don't accidentally clear it); "" clears it
    # explicitly. See routers/teams_users.py for the uniqueness check.
    ev_group_id: str | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    ev_group_id: str | None = None


# ---- Users ----
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str | None = None
    auth_type: AuthType = AuthType.local
    role: Role = Role.member
    team_id: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    auth_type: AuthType
    role: Role
    team_id: int | None
    is_active: bool


# ---- Tests ----
class TestCreate(BaseModel):
    name: str
    tester_reference: str | None = None
    penetration_tester: str | None = None
    unique_test_reference: str | None = None
    bau_or_project: BauOrProject | None = None
    itsm_reference: str | None = None
    date_logged: date | None = None
    due_date: date | None = None
    scheduled_date: date | None = None
    status: EngagementStatus = EngagementStatus.scheduled


class TestUpdate(BaseModel):
    name: str | None = None
    tester_reference: str | None = None
    penetration_tester: str | None = None
    unique_test_reference: str | None = None
    bau_or_project: BauOrProject | None = None
    itsm_reference: str | None = None
    date_logged: date | None = None
    due_date: date | None = None
    scheduled_date: date | None = None
    status: EngagementStatus | None = None


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    tester_reference: str | None
    penetration_tester: str | None
    unique_test_reference: str | None
    bau_or_project: BauOrProject | None
    itsm_reference: str | None
    date_logged: date | None
    logged_by_user_id: int | None
    due_date: date | None
    scheduled_date: date | None
    status: EngagementStatus
    created_at: datetime


# ---- Findings ----
class FindingCreate(BaseModel):
    test_id: int
    asset_tested: str | None = None
    user_story: str | None = None
    vulnerability: str | None = None
    finding_description: str | None = None
    test_vendor_initial_recommendation: str | None = None
    gross_risk_rating: RiskRating | None = None
    net_likelihood: LikelihoodImpact | None = None
    net_impact: LikelihoodImpact | None = None
    net_rating: RiskRating | None = None
    net_risk_rationale: str | None = None
    remediation_owner_user_id: int | None = None
    remediation_owner_team_id: int | None = None
    status: FindingStatus = FindingStatus.open
    due_date: date | None = None
    itsm_reference: str | None = None
    additional_information: str | None = None
    resolver_reference: str | None = None
    date_logged_in_resolver: date | None = None


class FindingUpdate(BaseModel):
    asset_tested: str | None = None
    user_story: str | None = None
    vulnerability: str | None = None
    finding_description: str | None = None
    test_vendor_initial_recommendation: str | None = None
    gross_risk_rating: RiskRating | None = None
    net_likelihood: LikelihoodImpact | None = None
    net_impact: LikelihoodImpact | None = None
    net_rating: RiskRating | None = None
    net_risk_rationale: str | None = None
    remediation_owner_user_id: int | None = None
    remediation_owner_team_id: int | None = None
    status: FindingStatus | None = None
    due_date: date | None = None
    itsm_reference: str | None = None
    additional_information: str | None = None
    resolver_reference: str | None = None
    date_logged_in_resolver: date | None = None


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    test_id: int
    asset_tested: str | None
    user_story: str | None
    vulnerability: str | None
    finding_description: str | None
    test_vendor_initial_recommendation: str | None
    gross_risk_rating: RiskRating | None
    net_likelihood: LikelihoodImpact | None
    net_impact: LikelihoodImpact | None
    net_rating: RiskRating | None
    net_risk_rationale: str | None
    remediation_owner_user_id: int | None
    remediation_owner_team_id: int | None
    status: FindingStatus
    due_date: date | None
    itsm_reference: str | None
    additional_information: str | None
    resolver_reference: str | None
    date_logged_in_resolver: date | None
    # EasyVista status cache — system-managed via POST /itsm/findings/{id}/refresh,
    # not settable through FindingCreate/FindingUpdate.
    itsm_status_label: str | None = None
    itsm_closed: bool | None = None
    itsm_synced_at: datetime | None = None
    sla_status: str
    created_at: datetime
    updated_at: datetime


class ItsmCommentOut(BaseModel):
    """A cached EasyVista ticket comment (Phase B). Read-only, returned by
    GET/POST /itsm/findings/{id}/comments[/sync]."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    author: str | None
    body: str | None
    action_type: str | None
    posted_at: datetime | None
    closed: bool | None
    synced_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    uploaded_by: int | None
    uploaded_at: datetime


# ---- Bookings (BAU schedule) ----
class BookingCreate(BaseModel):
    title: str
    unique_test_reference: str | None = None
    start_at: datetime
    end_at: datetime
    status: EngagementStatus = EngagementStatus.scheduled


class BookingUpdate(BaseModel):
    title: str | None = None
    unique_test_reference: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: EngagementStatus | None = None


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    unique_test_reference: str | None
    start_at: datetime
    end_at: datetime
    status: EngagementStatus
    status_updated_at: datetime | None
    sort_order: int
    created_at: datetime


class BookingReorder(BaseModel):
    ordered_ids: list[int]


# ---- Scopes ----
class ScopeCreate(BaseModel):
    title: str
    unique_test_reference: str | None = None


class ScopeUpdate(BaseModel):
    title: str | None = None
    unique_test_reference: str | None = None


class ScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    unique_test_reference: str | None
    created_at: datetime
    attachments: list[AttachmentOut] = []

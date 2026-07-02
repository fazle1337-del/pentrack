from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    AuthType,
    BauOrProject,
    EngagementStatus,
    FindingStatus,
    LikelihoodImpact,
    RiskRating,
    Role,
)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    # EasyVista assignee-group id (2026-07-01 correction: EV groups are a
    # separate namespace from Entra groups, so ticket routing can't reuse
    # idp_role_maps — see CLAUDE.md "EasyVista (ITSM) integration"). Nullable:
    # most teams won't have one set until an admin maps it via GET /groups.
    ev_group_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="team")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    auth_type: Mapped[AuthType] = mapped_column(SAEnum(AuthType), default=AuthType.local)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(SAEnum(Role), default=Role.member)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped on logout / forced sign-out to invalidate every previously issued
    # JWT (issue #5). Tokens carry a "tv" claim that get_current_user compares
    # against this; a mismatch rejects the token. server_default keeps fresh DBs
    # at 0 — existing rows added by the additive migration read NULL and are
    # treated as 0 in code.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # EasyVista person-identity fields (see Team.ev_group_id above).
    # staff_number is the Entra-side value that EV's AM_EMPLOYEE.IDENTIFICATION
    # matches; ev_employee_id is EV's own AM_EMPLOYEE.EMPLOYEE_ID, resolved by
    # querying GET /employees against staff_number (or email <-> AM_EMPLOYEE.LOGIN
    # as a fallback). Not consumed by any code path yet — needed starting Phase C
    # (comment attribution via the action's contact_* field).
    staff_number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    ev_employee_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    team: Mapped["Team | None"] = relationship(back_populates="users")


class IdpRoleMap(Base):
    """Maps an identity-provider group to an app role (and, optionally, a team).
    Evaluated at SSO login: the user's group claims are looked up here and the
    highest-privilege match wins. Decoupling the mapping from code lets you
    re-point Entra group GUIDs without a redeploy. ``idp_group_id`` holds the
    raw claim value — an object-ID GUID in Entra, a group path in Keycloak."""

    __tablename__ = "idp_role_maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    idp_group_id: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(200))  # human note, e.g. group name
    role: Mapped[Role] = mapped_column(SAEnum(Role), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)


class OidcSettings(Base):
    """Single-row, runtime-editable OIDC/Entra connection config (issue #11).

    Lets an admin point the app at an Entra tenant from the UI instead of editing
    compose env + bind-mounting a secret file + recreating the container. There
    is at most **one** row (``id == 1``). Any column left NULL/blank falls back
    to the corresponding env var, so an empty table == current env-only behaviour
    and existing deployments are unaffected until reconfigured. Resolution lives
    in ``app/core/oidc_config.py``.

    The client secret is stored **encrypted at rest** (``client_secret_enc``,
    a Fernet token via ``app/core/crypto.py``) and is never returned to clients.
    """

    __tablename__ = "oidc_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    authority: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    groups_claim: Mapped[str | None] = mapped_column(String(200), nullable=True)
    post_login_redirect: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )


class EasyVistaSettings(Base):
    """Single-row, runtime-editable store for the EasyVista bearer token +
    background-poller settings.

    2026-07-01 correction: EV auth is a bearer token tied to a managed identity,
    not HTTP Basic (the scaffold's original assumption was wrong — see
    CLAUDE.md "EasyVista (ITSM) integration"). Mirrors OidcSettings/
    client_secret_enc: encrypted at rest via ``app/core/crypto.py`` (a distinct
    KDF context — see ``EASYVISTA_CONTEXT`` — so this key can never collide with
    the OIDC secret's), write-only, never returned by the read endpoint.
    Rotation is an admin action (request the technician rotate it in EV, then
    re-enter it here), so it never needs a host-side file handoff — same
    pattern as the OIDC client secret. Host/account/catalog/requestor stay
    env-configured for now (only the token has a rotation lifecycle).

    The poll_* columns are the "admin-tab adjustable" half of the locked
    polling decision — DB-over-env per field, resolved in
    ``app/core/easyvista_config.py``, same as the token. Not secret, so stored
    plain (unlike the token) and returned as-is by the read endpoint.
    """

    __tablename__ = "easyvista_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1
    bearer_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    poll_open_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poll_closed_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poll_closed_lookback_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    tester_reference: Mapped[str | None] = mapped_column(String(300))
    penetration_tester: Mapped[str | None] = mapped_column(String(300))
    unique_test_reference: Mapped[str | None] = mapped_column(String(200), index=True)
    bau_or_project: Mapped[BauOrProject | None] = mapped_column(SAEnum(BauOrProject))
    itsm_reference: Mapped[str | None] = mapped_column(String(200))
    date_logged: Mapped[date | None] = mapped_column(Date)
    logged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[EngagementStatus] = mapped_column(
        SAEnum(EngagementStatus), default=EngagementStatus.scheduled
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    findings: Mapped[list["Finding"]] = relationship(back_populates="test", cascade="all, delete-orphan")
    attachments: Mapped[list["TestAttachment"]] = relationship(back_populates="test", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id"), nullable=False)

    asset_tested: Mapped[str | None] = mapped_column(String(300))
    user_story: Mapped[str | None] = mapped_column(Text)
    vulnerability: Mapped[str | None] = mapped_column(String(500))
    finding_description: Mapped[str | None] = mapped_column(Text)
    test_vendor_initial_recommendation: Mapped[str | None] = mapped_column(Text)

    gross_risk_rating: Mapped[RiskRating | None] = mapped_column(SAEnum(RiskRating))
    net_likelihood: Mapped[LikelihoodImpact | None] = mapped_column(SAEnum(LikelihoodImpact))
    net_impact: Mapped[LikelihoodImpact | None] = mapped_column(SAEnum(LikelihoodImpact))
    net_rating: Mapped[RiskRating | None] = mapped_column(SAEnum(RiskRating))
    net_risk_rationale: Mapped[str | None] = mapped_column(Text)

    remediation_owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    remediation_owner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))

    status: Mapped[FindingStatus] = mapped_column(SAEnum(FindingStatus), default=FindingStatus.open)
    due_date: Mapped[date | None] = mapped_column(Date)
    itsm_reference: Mapped[str | None] = mapped_column(String(200))
    additional_information: Mapped[str | None] = mapped_column(Text)
    resolver_reference: Mapped[str | None] = mapped_column(String(200))
    date_logged_in_resolver: Mapped[date | None] = mapped_column(Date)
    # EasyVista status cache (2026-07-01, Phase A). Populated by
    # POST /itsm/findings/{id}/refresh (on-demand for now — no background
    # poller yet). itsm_closed is derived from EV's END_DATE_UT being set, not
    # a status-label match (that's the authoritative "closed" signal per the
    # wiki; itsm_status_label is just the raw STATUS_EN for display). System-
    # managed — not exposed on FindingCreate/FindingUpdate, only FindingOut.
    itsm_status_label: Mapped[str | None] = mapped_column(String(200))
    itsm_closed: Mapped[bool | None] = mapped_column(Boolean)
    itsm_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    test: Mapped["Test"] = relationship(back_populates="findings")
    attachments: Mapped[list["FindingAttachment"]] = relationship(back_populates="finding", cascade="all, delete-orphan")
    reassignments: Mapped[list["FindingReassignment"]] = relationship(back_populates="finding", cascade="all, delete-orphan")


class TestAttachment(Base):
    __tablename__ = "test_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    test: Mapped["Test"] = relationship(back_populates="attachments")


class FindingAttachment(Base):
    __tablename__ = "finding_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    finding: Mapped["Finding"] = relationship(back_populates="attachments")


class FindingReassignment(Base):
    __tablename__ = "finding_reassignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    from_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    finding: Mapped["Finding"] = relationship(back_populates="reassignments")


class Booking(Base):
    """A scheduled slot on the BAU timeline. Linked to a Test (and everything
    else) only by the shared ``unique_test_reference`` string — no hard FK, so
    a booking can exist before its test does."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    unique_test_reference: Mapped[str | None] = mapped_column(String(200), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[EngagementStatus] = mapped_column(
        SAEnum(EngagementStatus), default=EngagementStatus.scheduled
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scope(Base):
    """A scoping document for an engagement: a title plus attached files.
    Linked by the shared ``unique_test_reference`` string."""

    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    unique_test_reference: Mapped[str | None] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attachments: Mapped[list["ScopeAttachment"]] = relationship(
        back_populates="scope", cascade="all, delete-orphan"
    )


class ScopeAttachment(Base):
    __tablename__ = "scope_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_id: Mapped[int] = mapped_column(ForeignKey("scopes.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scope: Mapped["Scope"] = relationship(back_populates="attachments")

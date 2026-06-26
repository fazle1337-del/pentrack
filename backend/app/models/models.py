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

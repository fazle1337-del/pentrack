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
    FindingStatus,
    LikelihoodImpact,
    RiskRating,
    Role,
    TestStatus,
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


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    tester_reference: Mapped[str | None] = mapped_column(String(300))
    scope: Mapped[str | None] = mapped_column(Text)
    bau_or_project: Mapped[BauOrProject | None] = mapped_column(SAEnum(BauOrProject))
    itsm_reference: Mapped[str | None] = mapped_column(String(200))
    date_logged: Mapped[date | None] = mapped_column(Date)
    logged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TestStatus] = mapped_column(SAEnum(TestStatus), default=TestStatus.planned)
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

"""CSV import: parse a single CSV that contains one test plus its findings
(test columns repeated per row). Import is lenient — every row is created;
values that don't validate are left unset and reported as issues for an admin
to fix later in the UI.
"""
import csv
import io
from datetime import date, datetime

from app.models.enums import FindingStatus, LikelihoodImpact, RiskRating, BauOrProject

# Target fields the importer can map CSV columns onto.
TEST_FIELDS = [
    "name",
    "tester_reference",
    "scope",
    "bau_or_project",
    "itsm_reference",
    "date_logged",
    "due_date",
    "scheduled_date",
]
FINDING_FIELDS = [
    "asset_tested",
    "user_story",
    "vulnerability",
    "finding_description",
    "test_vendor_initial_recommendation",
    "gross_risk_rating",
    "net_likelihood",
    "net_impact",
    "net_rating",
    "net_risk_rationale",
    "status",
    "due_date",
    "itsm_reference",
    "additional_information",
    "resolver_reference",
    "date_logged_in_resolver",
]

DATE_FIELDS = {
    "date_logged",
    "due_date",
    "scheduled_date",
    "date_logged_in_resolver",
}
RATING_FIELDS = {"gross_risk_rating", "net_rating"}
LIKELIHOOD_IMPACT_FIELDS = {"net_likelihood", "net_impact"}


def decode_csv(raw: bytes) -> list[dict]:
    """Decode raw CSV bytes into a list of row dicts keyed by header."""
    text = raw.decode("utf-8-sig", errors="replace")  # tolerate BOM
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader], reader.fieldnames or []


def _norm_enum(value: str, enum_cls) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    for member in enum_cls:
        if member.value.lower() == v:
            return member.value
    # tolerate common variants e.g. "in progress"/"in-progress"
    squished = v.replace("-", " ").replace("_", " ")
    for member in enum_cls:
        if member.value.lower() == squished:
            return member.value
    return None  # unrecognized -> caller flags it


def _parse_date(value: str):
    if value is None or not value.strip():
        return None, False  # empty is fine, not an issue
    s = value.strip()
    fmts = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date(), False
        except ValueError:
            continue
    return None, True  # unparseable -> issue


def coerce_value(field: str, raw_value: str):
    """Return (value, issue_or_None) for a target field."""
    if raw_value is not None:
        raw_value = raw_value.strip()
    if field in DATE_FIELDS:
        d, bad = _parse_date(raw_value)
        if bad:
            return None, f"could not parse date '{raw_value}'"
        return d, None
    if field in RATING_FIELDS:
        if not raw_value:
            return None, None
        v = _norm_enum(raw_value, RiskRating)
        return v, (None if v else f"unknown rating '{raw_value}'")
    if field in LIKELIHOOD_IMPACT_FIELDS:
        if not raw_value:
            return None, None
        v = _norm_enum(raw_value, LikelihoodImpact)
        return v, (None if v else f"unknown value '{raw_value}'")
    if field == "status":
        if not raw_value:
            return FindingStatus.open.value, None  # default
        v = _norm_enum(raw_value, FindingStatus)
        return (v or FindingStatus.open.value), (
            None if v else f"unknown status '{raw_value}', defaulted to Open"
        )
    if field == "bau_or_project":
        if not raw_value:
            return None, None
        v = _norm_enum(raw_value, BauOrProject)
        return v, (None if v else f"unknown BAU/Project '{raw_value}'")
    # plain text
    return (raw_value or None), None


def build_import(rows: list[dict], mapping: dict[str, str]):
    """mapping: {csv_column: target_field}. Returns (test_data, findings, issues).

    test_data: dict of test fields taken from the first row.
    findings: list of dicts of finding fields.
    issues: list of {row, field, message}.
    """
    # invert: target_field -> csv_column (last wins if duplicated)
    target_to_col = {}
    for col, target in mapping.items():
        if target:
            target_to_col[target] = col

    issues = []
    findings = []
    test_data = {}

    # test-level fields from the first row
    if rows:
        first = rows[0]
        for tf in TEST_FIELDS:
            col = target_to_col.get(tf)
            if col is None:
                continue
            val, issue = coerce_value(tf, first.get(col))
            test_data[tf] = val
            if issue:
                issues.append({"row": 1, "field": tf, "message": issue})

    # finding per row
    for i, row in enumerate(rows, start=1):
        f = {}
        for ff in FINDING_FIELDS:
            col = target_to_col.get(ff)
            if col is None:
                continue
            val, issue = coerce_value(ff, row.get(col))
            f[ff] = val
            if issue:
                issues.append({"row": i, "field": ff, "message": issue})
        findings.append(f)

    return test_data, findings, issues

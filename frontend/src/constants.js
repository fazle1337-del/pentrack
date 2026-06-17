export const NET_RATINGS = ["Critical", "High", "Medium", "Low", "Info"];
export const LIKELIHOOD_IMPACT = ["Critical", "High", "Medium", "Low"];
export const FINDING_STATUSES = [
  "Open",
  "In Progress",
  "Remediated",
  "Verified",
  "Closed",
  "Transferred",
  "Accepted",
  "Duplicate",
];
// Shared engagement lifecycle used by tests and schedule bookings.
export const ENGAGEMENT_STATUSES = ["Scheduled", "Booked", "Complete", "Cancelled"];

// engagement status -> css class for the coloured bar/dot
export function engagementClass(s) {
  return (
    {
      Scheduled: "st-scheduled",
      Booked: "st-booked",
      Complete: "st-complete",
      Cancelled: "st-cancelled",
    }[s] || "st-scheduled"
  );
}

// rating -> css class for color
export function ratingClass(r) {
  return (
    { Critical: "crit", High: "high", Medium: "med", Low: "low", Info: "info" }[r] ||
    "info"
  );
}
export function ratingBg(r) {
  return "bg-" + ratingClass(r);
}
// status -> dot class (strip spaces to match CSS)
export function statusDot(s) {
  return "d-" + (s || "").replace(/\s/g, "");
}

export function fmtDate(d) {
  return d || "—";
}

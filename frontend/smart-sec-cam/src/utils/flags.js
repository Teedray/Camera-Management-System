// The reasons an incident clip can be flagged with (SR-04-02). The backend must accept the same values.
export const FLAGS = [
  { value: "theft", label: "Theft" },
  { value: "dispute", label: "Dispute or complaint" },
  { value: "safety", label: "Safety incident" },
  { value: "staff", label: "Staff matter" },
  { value: "other", label: "Other" },
];

export const flagLabel = (value) => (FLAGS.find((f) => f.value === value) || { label: value }).label;
export const ROLES = ["admin", "manager", "viewer"];

import React from "react";
import Chip from "@mui/material/Chip";

const LOOKS = {
  saving: ["Saving", "info"], queued: ["Queued", "default"], processing: ["Processing", "info"],
  saved: ["Saved", "success"], ready: ["Ready", "success"], failed: ["Failed", "error"], expired: ["Expired", "default"],
  connected: ["Connected", "success"], disconnected: ["Disconnected", "error"], enabled: ["Enabled", "success"], disabled: ["Disabled", "default"],
};

// One consistent look for every status the screens show (saving, ready, failed, connected ...).
export default function StatusChip({ status, label }) {
  const [text, color] = LOOKS[status] || [status, "default"];
  return <Chip size="small" label={label || text} color={color} />;
}

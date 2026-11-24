import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { useLocation, useNavigate } from "react-router-dom";

import { fetchSystemStatus } from "../api/systemApi";

// Warnings management should not miss (camera down, storage nearly full, failed upload or backup).
// Shown at the top of every page except the Status page itself, which lists them in full.
export default function StatusBanner({ token }) {
  const [warnings, setWarnings] = React.useState([]);
  const navigate = useNavigate();
  const location = useLocation();

  React.useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    const load = () => fetchSystemStatus(token)
      .then((data) => { if (!cancelled) setWarnings(data.warnings || []); })
      .catch(() => {});
    load();
    const timer = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [token]);

  if (!warnings.length || location.pathname === "/status") return null;
  return (
    <Box sx={{ px: { xs: 1.5, md: 3 }, pt: 1.5, maxWidth: 1400, mx: "auto" }}>
      {warnings.slice(0, 3).map((w) => (
        <Alert key={w.code} severity={w.level === "error" ? "error" : "warning"} sx={{ mb: 1 }}
               action={<Button color="inherit" size="small" onClick={() => navigate("/status")}>Details</Button>}>
          {w.message}
        </Alert>
      ))}
    </Box>
  );
}

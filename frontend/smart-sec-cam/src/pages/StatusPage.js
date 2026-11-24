import { USE_MOCK } from "../config";
import RealStatusPage from "./RealStatusPage";
import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { fetchSystemStatus } from "../api/systemApi";
import Layout from "../components/Layout";
import StatusChip from "../components/StatusChip";
import useAuth from "../hooks/useAuth";
import { formatBytes, timeAgo } from "../utils/time";

function Section({ title, children }) {
  return (
    <Paper component="section" aria-label={title} sx={{ p: 2 }}>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>{title}</Typography>
      {children}
    </Paper>
  );
}

// Is the system healthy? Cameras, disk space, cloud upload and backup, with every warning in one place.
function MockStatusPage() {
  const { token, ready } = useAuth();
  const [status, setStatus] = React.useState(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(() => (
    fetchSystemStatus(token).then((s) => { setStatus(s); setError(""); }).catch((e) => setError(e.message))
  ), [token]);

  React.useEffect(() => {
    if (!ready) return undefined;
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [ready, load]);

  if (!ready) return null;
  const storage = status && status.storage;
  const usedPercent = storage ? Math.round((storage.used_bytes / storage.total_bytes) * 100) : 0;

  return (
    <Layout token={token}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="h5" component="h1">System status</Typography>
        <Button onClick={load}>Refresh</Button>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!status && !error && <LinearProgress aria-label="Loading status" />}
      {status && (
        <Box sx={{ display: "grid", gap: 2 }}>
          {status.warnings.length === 0 ? (
            <Alert severity="success">Everything is working normally.</Alert>
          ) : (
            <Box sx={{ display: "grid", gap: 1 }}>
              {status.warnings.map((w) => (
                <Alert key={w.code} severity={w.level === "error" ? "error" : "warning"}>
                  {w.message} (since {timeAgo(w.since)})
                </Alert>
              ))}
            </Box>
          )}

          <Section title="Cameras">
            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
              {status.cameras.map((c) => (
                <Paper key={c.name} variant="outlined" sx={{ p: 1.5 }} aria-label={c.name}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
                    <Typography fontWeight={600}>{c.name}</Typography>
                    <StatusChip status={c.connection} />
                  </Box>
                  <Typography variant="body2" color="text.secondary">Last recording: {timeAgo(c.last_recording)}</Typography>
                  <Typography variant="body2" color="text.secondary">Recording gaps today: {c.gaps_today}</Typography>
                </Paper>
              ))}
            </Box>
          </Section>

          <Section title="Storage">
            <LinearProgress variant="determinate" value={Math.min(100, usedPercent)} color={storage.low ? "error" : "primary"}
                            aria-label="Storage used" sx={{ height: 10, borderRadius: 1 }} />
            <Typography variant="body2" sx={{ mt: 1 }}>
              {formatBytes(storage.used_bytes)} of {formatBytes(storage.total_bytes)} used ({usedPercent}%).
              Footage is kept for {storage.retention_days} days.
            </Typography>
            {storage.low && <Alert severity="warning" sx={{ mt: 1 }}>Storage is running low. Free up disk space.</Alert>}
          </Section>

          <Section title="Cloud upload">
            <StatusChip status={status.cloud.connected ? "connected" : "disconnected"} />
            <Typography variant="body2" sx={{ mt: 1 }}>
              Waiting to upload: {status.cloud.pending_uploads} {status.cloud.pending_uploads === 1 ? "clip" : "clips"}.
              Last upload: {timeAgo(status.cloud.last_upload)}.
            </Typography>
            {status.cloud.last_error && <Alert severity="error" sx={{ mt: 1 }}>{status.cloud.last_error}</Alert>}
          </Section>

          <Section title="Backup">
            <Typography variant="body2">Last successful backup: {timeAgo(status.backup.last_success)}.</Typography>
            {status.backup.last_error && <Alert severity="error" sx={{ mt: 1 }}>{status.backup.last_error}</Alert>}
          </Section>
        </Box>
      )}
    </Layout>
  );
}

export default function StatusPage() {
  return USE_MOCK ? <MockStatusPage /> : <RealStatusPage />;
}

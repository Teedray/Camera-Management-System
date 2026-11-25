import { USE_MOCK } from "../config";
import RealExportsPage from "./RealExportsPage";
import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { exportDownloadUrl, listExports } from "../api/exportsApi";
import { POLL_INTERVAL_MS } from "../api/polling";
import Layout from "../components/Layout";
import StatusChip from "../components/StatusChip";
import useAuth from "../hooks/useAuth";
import { DEFAULT_TZ, formatBytes, formatDateTime, formatDuration, formatTime } from "../utils/time";

const ACTIVE = ["queued", "processing"];

// F05: exported MP4 files and their status. Exports are removed after 24 hours.
function MockExportsPage() {
  const { token, ready } = useAuth();
  const [exportsList, setExportsList] = React.useState(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(() => (
    listExports(token).then((list) => { setExportsList(list); setError(""); }).catch((e) => setError(e.message))
  ), [token]);

  React.useEffect(() => { if (ready) load(); }, [ready, load]);

  // Keep refreshing while anything is still being prepared.
  const waiting = (exportsList || []).some((e) => ACTIVE.includes(e.status));
  React.useEffect(() => {
    if (!waiting) return undefined;
    const timer = setTimeout(load, POLL_INTERVAL_MS * 2);
    return () => clearTimeout(timer);
  }, [waiting, exportsList, load]);

  if (!ready) return null;
  return (
    <Layout token={token}>
      <Typography variant="h5" component="h1" sx={{ mb: 2 }}>Exports</Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {exportsList === null && !error && <LinearProgress aria-label="Loading exports" />}
      {exportsList !== null && exportsList.length === 0 && (
        <Paper sx={{ p: 3, textAlign: "center" }}>
          <Typography fontWeight={600}>No exports yet</Typography>
          <Typography variant="body2" color="text.secondary">
            Find footage on the Search page, then choose Trim and download.
          </Typography>
        </Paper>
      )}
      <Box sx={{ display: "grid", gap: 1.5 }}>
        {(exportsList || []).map((e) => {
          const expired = e.status === "expired" || (e.status === "ready" && Date.parse(e.expires_at) < Date.now());
          const status = expired ? "expired" : e.status;
          return (
            <Paper key={e.id} component="article" aria-label={`Export ${e.id}`} sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, flexWrap: "wrap" }}>
                <Typography fontWeight={600}>{e.camera}</Typography>
                <StatusChip status={status} />
              </Box>
              <Typography variant="body2" color="text.secondary">
                {formatDateTime(e.start, DEFAULT_TZ)} to {formatTime(e.end, DEFAULT_TZ)}
                {" · "}{formatDuration((Date.parse(e.end) - Date.parse(e.start)) / 1000)}
                {e.size_bytes ? ` · ${formatBytes(e.size_bytes)}` : ""}
              </Typography>
              {status === "failed" && <Alert severity="error" sx={{ mt: 1 }}>{e.error || "The export failed."}</Alert>}
              {ACTIVE.includes(status) && <LinearProgress sx={{ mt: 1 }} aria-label="Preparing export" />}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                Requested {formatDateTime(e.created_at, DEFAULT_TZ)}
                {status === "ready" ? ` · available until ${formatDateTime(e.expires_at, DEFAULT_TZ)}` : ""}
              </Typography>
              {status === "ready" && (
                <Button size="small" variant="contained" sx={{ mt: 1.5 }} component="a"
                        href={exportDownloadUrl(e.id, token)} download>
                  Download MP4
                </Button>
              )}
            </Paper>
          );
        })}
      </Box>
    </Layout>
  );
}

export default function ExportsPage() {
  return USE_MOCK ? <MockExportsPage /> : <RealExportsPage />;
}

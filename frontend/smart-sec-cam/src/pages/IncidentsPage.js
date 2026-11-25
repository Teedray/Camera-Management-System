import { USE_MOCK } from "../config";
import RealIncidentsPage from "./RealIncidentsPage";
import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { deleteIncident, incidentStreamUrl, listIncidents } from "../api/incidentsApi";
import Layout from "../components/Layout";
import StatusChip from "../components/StatusChip";
import useAuth from "../hooks/useAuth";
import useMe from "../hooks/useMe";
import { FLAGS, flagLabel } from "../utils/flags";
import { videoFormat } from "../utils/mediaFormat";
import { DEFAULT_TZ, formatDateTime, formatDuration, formatTime } from "../utils/time";

// F04: every incident clip saved in the archive. These are kept until an administrator removes them.
function MockIncidentsPage() {
  const { token, ready } = useAuth();
  const me = useMe(ready ? token : null);
  const [incidents, setIncidents] = React.useState(null);
  const [error, setError] = React.useState("");
  const [flag, setFlag] = React.useState("");
  const [playing, setPlaying] = React.useState(null);
  const [toDelete, setToDelete] = React.useState(null);

  const load = React.useCallback(() => {
    listIncidents(token).then(setIncidents).catch((e) => setError(e.message));
  }, [token]);
  React.useEffect(() => { if (ready) load(); }, [ready, load]);

  async function confirmDelete() {
    const target = toDelete;
    setToDelete(null);
    try {
      await deleteIncident(token, target.id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!ready) return null;
  const shown = (incidents || []).filter((i) => !flag || i.flag === flag);
  const isAdmin = me && me.role === "admin";

  return (
    <Layout token={token}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 2, mb: 2 }}>
        <Typography variant="h5" component="h1">Incident clips</Typography>
        <TextField select size="small" label="Flag" value={flag} onChange={(e) => setFlag(e.target.value)} sx={{ minWidth: 200 }}
                   slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}>
          <MenuItem value="">All flags</MenuItem>
          {FLAGS.map((f) => <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>)}
        </TextField>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>{error}</Alert>}
      {incidents === null && !error && <LinearProgress aria-label="Loading incidents" />}
      {incidents !== null && shown.length === 0 && (
        <Paper sx={{ p: 3, textAlign: "center" }}>
          <Typography fontWeight={600}>No incident clips found</Typography>
          <Typography variant="body2" color="text.secondary">
            Save one from the Search page: find the footage, then choose Save as incident.
          </Typography>
        </Paper>
      )}
      <Box sx={{ display: "grid", gap: 1.5 }}>
        {shown.map((i) => (
          <Paper key={i.id} component="article" aria-label={i.title} sx={{ p: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="h6" component="h2" sx={{ fontSize: "1.1rem" }}>{i.title}</Typography>
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                <Chip size="small" label={flagLabel(i.flag)} />
                <StatusChip status={i.status} />
                <Chip size="small" variant="outlined" color={i.backed_up ? "success" : "warning"}
                      label={i.backed_up ? "Backed up to cloud" : "Cloud backup pending"} />
              </Box>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {i.camera} · {formatDateTime(i.start, DEFAULT_TZ)} to {formatTime(i.end, DEFAULT_TZ)} · {formatDuration(i.duration)}
            </Typography>
            {i.description && <Typography variant="body2" sx={{ mt: 1 }}>{i.description}</Typography>}
            {i.error && <Alert severity="error" sx={{ mt: 1 }}>{i.error}</Alert>}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Saved by {i.created_by} on {formatDateTime(i.created_at, DEFAULT_TZ)}
            </Typography>
            <Box sx={{ display: "flex", gap: 1, mt: 1.5 }}>
              <Button size="small" variant="contained" disabled={i.status !== "saved"} onClick={() => setPlaying(i)}>Play</Button>
              {isAdmin && <Button size="small" color="error" onClick={() => setToDelete(i)}>Delete</Button>}
            </Box>
          </Paper>
        ))}
      </Box>

      <Dialog open={Boolean(playing)} onClose={() => setPlaying(null)} fullWidth maxWidth="md">
        <DialogTitle>{playing && playing.title}</DialogTitle>
        <DialogContent>
          {playing && (
            <video controls autoPlay muted playsInline style={{ width: "100%", background: "#000" }}
                   src={incidentStreamUrl(playing.id, token, videoFormat())} />
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setPlaying(null)}>Close</Button></DialogActions>
      </Dialog>

      <Dialog open={Boolean(toDelete)} onClose={() => setToDelete(null)}>
        <DialogTitle>Delete this incident clip?</DialogTitle>
        <DialogContent>
          <Typography>
            "{toDelete && toDelete.title}" will no longer be kept. This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setToDelete(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDelete}>Delete clip</Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
}

export default function IncidentsPage() {
  return USE_MOCK ? <MockIncidentsPage /> : <RealIncidentsPage />;
}

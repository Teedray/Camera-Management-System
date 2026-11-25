import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";

import { createExport, exportDownloadUrl, getExport } from "../api/exportsApi";
import { pollUntil } from "../api/polling";
import { defaultInterval, validateInterval } from "../utils/interval";
import IntervalFields from "./IntervalFields";
import StatusChip from "./StatusChip";

const FINISHED = ["ready", "failed", "expired"];

// F05: cut part of the searched footage and download it as one MP4 file (SR-05-01, SR-05-02).
// The export runs on the server; this shows its status (queued, processing, ready, failed).
export default function ExportDialog({ open, onClose, token, camera, rangeStartMs, rangeEndMs, posMs, tz }) {
  const context = React.useRef({});
  context.current = { rangeStartMs, rangeEndMs, posMs, tz };
  const cancelled = React.useRef(false);
  const [slot, setSlot] = React.useState({ date: "", start: "", end: "" });
  const [errors, setErrors] = React.useState({});
  const [phase, setPhase] = React.useState("form"); // form | working | finished
  const [info, setInfo] = React.useState(null);
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      cancelled.current = true;
      return;
    }
    cancelled.current = false;
    const c = context.current;
    setSlot(defaultInterval(c.rangeStartMs, c.rangeEndMs, c.posMs, c.tz));
    setErrors({});
    setPhase("form");
    setInfo(null);
    setMessage("");
  }, [open]);
  React.useEffect(() => () => { cancelled.current = true; }, []);

  const changeSlot = (name, value) => {
    setSlot((s) => ({ ...s, [name]: value }));
    setErrors({});
  };

  async function submit(event) {
    event.preventDefault();
    const check = validateInterval(slot, rangeStartMs, rangeEndMs, tz);
    setErrors(check.errors);
    if (Object.keys(check.errors).length) return;
    setPhase("working");
    setMessage("");
    try {
      let exp = await createExport(token, {
        camera, start: new Date(check.startMs).toISOString(), end: new Date(check.endMs).toISOString(),
      });
      setInfo(exp);
      const id = exp.id;
      exp = await pollUntil(async () => {
        const latest = await getExport(token, id);
        setInfo(latest);
        return latest;
      }, (e) => FINISHED.includes(e.status), { isCancelled: () => cancelled.current });
      if (exp) setPhase("finished");
    } catch (err) {
      setPhase("form");
      if (["start", "end"].includes(err.field)) setErrors({ [err.field]: err.message });
      else setMessage(err.message);
    }
  }

  const working = phase === "working";
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="export-dialog-title">
      <DialogTitle id="export-dialog-title">Trim and download</DialogTitle>
      <Box component="form" onSubmit={submit} noValidate>
        <DialogContent sx={{ display: "grid", gap: 2 }}>
          <Typography variant="body2">Camera: <strong>{camera}</strong></Typography>
          {phase === "form" && (
            <IntervalFields values={slot} errors={errors} onChange={changeSlot} posMs={posMs} tz={tz}
                            rangeStartMs={rangeStartMs} rangeEndMs={rangeEndMs} />
          )}
          {info && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="body2">Export status:</Typography>
              <StatusChip status={info.status} />
            </Box>
          )}
          {working && (
            <Box>
              <LinearProgress aria-label="Preparing export" />
              <Typography variant="caption">
                Preparing your video. You can close this window; the export carries on and appears on the Exports page.
              </Typography>
            </Box>
          )}
          {info && info.status === "ready" && (
            <Alert severity="success">Your video is ready. It stays available for 24 hours.</Alert>
          )}
          {info && info.status === "failed" && (
            <Alert severity="error">{info.error || "The export failed. Try again."}</Alert>
          )}
          {message && <Alert severity="error">{message}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{phase === "form" ? "Cancel" : "Close"}</Button>
          {phase === "form" && <Button type="submit" variant="contained">Start export</Button>}
          {info && info.status === "ready" && (
            <Button variant="contained" component="a" href={exportDownloadUrl(info.id, token)} download>
              Download MP4
            </Button>
          )}
        </DialogActions>
      </Box>
    </Dialog>
  );
}

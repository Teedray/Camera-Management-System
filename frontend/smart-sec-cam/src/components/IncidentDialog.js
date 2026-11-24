import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { createIncident, getIncident } from "../api/incidentsApi";
import { pollUntil } from "../api/polling";
import { FLAGS } from "../utils/flags";
import { defaultInterval, validateInterval } from "../utils/interval";
import IntervalFields from "./IntervalFields";

// F04: save part of the searched footage as an incident clip (SR-04-01 to SR-04-03, SAF-02).
// "Saved" is only shown once the server says the clip was verified in the archive.
export default function IncidentDialog({ open, onClose, onSaved, token, camera, rangeStartMs, rangeEndMs, posMs, tz }) {
  const context = React.useRef({});
  context.current = { rangeStartMs, rangeEndMs, posMs, tz };
  const cancelled = React.useRef(false);
  const [slot, setSlot] = React.useState({ date: "", start: "", end: "" });
  const [form, setForm] = React.useState({ title: "", description: "", flag: "" });
  const [errors, setErrors] = React.useState({});
  const [phase, setPhase] = React.useState("form"); // form | saving | done
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      cancelled.current = true;
      return;
    }
    cancelled.current = false;
    const c = context.current;
    setSlot(defaultInterval(c.rangeStartMs, c.rangeEndMs, c.posMs, c.tz));
    setForm({ title: "", description: "", flag: "" });
    setErrors({});
    setPhase("form");
    setMessage("");
  }, [open]);
  React.useEffect(() => () => { cancelled.current = true; }, []);

  const field = (name) => (e) => {
    setForm((f) => ({ ...f, [name]: e.target.value }));
    setErrors((er) => ({ ...er, [name]: undefined }));
  };
  const changeSlot = (name, value) => {
    setSlot((s) => ({ ...s, [name]: value }));
    setErrors((er) => ({ ...er, start: undefined, end: undefined }));
  };

  async function submit(event) {
    event.preventDefault();
    const check = validateInterval(slot, rangeStartMs, rangeEndMs, tz);
    const found = { ...check.errors };
    if (!form.title.trim()) found.title = "Enter a title.";
    if (!form.flag) found.flag = "Choose a flag.";
    setErrors(found);
    if (Object.keys(found).length) return;

    setPhase("saving");
    setMessage("");
    try {
      let incident = await createIncident(token, {
        camera, start: new Date(check.startMs).toISOString(), end: new Date(check.endMs).toISOString(),
        title: form.title.trim(), description: form.description.trim(), flag: form.flag,
      });
      if (incident.status === "saving") {
        const id = incident.id;
        incident = await pollUntil(() => getIncident(token, id), (i) => i.status !== "saving",
                                   { isCancelled: () => cancelled.current });
        if (!incident) return; // dialog closed while saving; the server carries on
      }
      if (incident.status === "saved") {
        setPhase("done");
        onSaved(incident);
      } else {
        setPhase("form");
        setMessage(incident.error || "The clip could not be saved. Nothing was added to the archive.");
      }
    } catch (err) {
      setPhase("form");
      // Show a server message next to its field when the dialog has one, otherwise as a general error.
      if (["title", "description", "flag", "start", "end"].includes(err.field)) {
        setErrors((er) => ({ ...er, [err.field]: err.message }));
      } else {
        setMessage(err.message);
      }
    }
  }

  const busy = phase === "saving";
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="sm" aria-labelledby="incident-dialog-title">
      <DialogTitle id="incident-dialog-title">Save incident clip</DialogTitle>
      <Box component="form" onSubmit={submit} noValidate>
        <DialogContent sx={{ display: "grid", gap: 2 }}>
          {phase === "done" ? (
            <Alert severity="success">
              Saved. This clip is kept in the incident archive after the 30-day retention period.
            </Alert>
          ) : (
            <>
              <Typography variant="body2">Camera: <strong>{camera}</strong></Typography>
              <IntervalFields values={slot} errors={errors} onChange={changeSlot} posMs={posMs} tz={tz}
                              rangeStartMs={rangeStartMs} rangeEndMs={rangeEndMs} />
              <TextField label="Title" value={form.title} onChange={field("title")} required
                         error={Boolean(errors.title)} helperText={errors.title} disabled={busy} />
              <TextField label="Description (optional)" value={form.description} onChange={field("description")}
                         multiline minRows={2} disabled={busy}
                         error={Boolean(errors.description)} helperText={errors.description} />
              <TextField select label="Flag" value={form.flag} onChange={field("flag")} required
                         error={Boolean(errors.flag)} helperText={errors.flag} disabled={busy}>
                {FLAGS.map((f) => <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>)}
              </TextField>
              {busy && (
                <Box>
                  <LinearProgress aria-label="Saving clip" />
                  <Typography variant="caption">Saving and checking the clip…</Typography>
                </Box>
              )}
              {message && <Alert severity="error">{message}</Alert>}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>{phase === "done" ? "Close" : "Cancel"}</Button>
          {phase !== "done" && <Button type="submit" variant="contained" disabled={busy}>Save clip</Button>}
        </DialogActions>
      </Box>
    </Dialog>
  );
}

import { USE_MOCK } from "../config";
import RealAdminPage from "./RealAdminPage";
import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { createCamera, deleteCamera, listAdminCameras, listUsers, updateCamera, updateUser } from "../api/adminApi";
import Layout from "../components/Layout";
import StatusChip from "../components/StatusChip";
import useAuth from "../hooks/useAuth";
import useMe from "../hooks/useMe";

const ROLES = USE_MOCK ? ["admin", "manager", "viewer"] : ["administrator", "manager", "viewer"];

const CAMERA_NAME = /^[A-Za-z0-9_-]{2,40}$/;

export function validateCamera(values) {
  const errors = {};
  if (!CAMERA_NAME.test(values.name.trim())) errors.name = "Use 2 to 40 letters, numbers, underscores or hyphens.";
  if (!values.address.trim()) errors.address = "Enter the camera address.";
  return errors;
}

function CameraDialog({ camera, onClose, onSave }) {
  const [values, setValues] = React.useState({ name: "", address: "", type: "ip", enabled: true });
  const [errors, setErrors] = React.useState({});
  const [message, setMessage] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (camera) {
      setValues({ name: camera.name || "", address: camera.address || "", type: camera.type || "ip", enabled: camera.enabled !== false });
      setErrors({});
      setMessage("");
    }
  }, [camera]);

  const set = (name) => (e) => {
    setValues((v) => ({ ...v, [name]: e.target.value }));
    setErrors((er) => ({ ...er, [name]: undefined }));
  };

  async function submit(event) {
    event.preventDefault();
    const found = validateCamera(values);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await onSave({ ...values, name: values.name.trim(), address: values.address.trim() });
    } catch (err) {
      if (err.field) setErrors((er) => ({ ...er, [err.field]: err.message }));
      else setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={Boolean(camera)} onClose={busy ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>{camera && camera.id ? "Edit camera" : "Add camera"}</DialogTitle>
      <Box component="form" onSubmit={submit} noValidate>
        <DialogContent sx={{ display: "grid", gap: 2 }}>
          <TextField label="Name" value={values.name} onChange={set("name")} required
                     error={Boolean(errors.name)} helperText={errors.name || "For example CAM_ENTRANCE"} />
          <TextField select label="Type" value={values.type} onChange={set("type")}>
            <MenuItem value="ip">Network camera (IP Webcam)</MenuItem>
            <MenuItem value="usb">USB webcam</MenuItem>
          </TextField>
          <TextField label={values.type === "usb" ? "Device number" : "Stream address"} value={values.address}
                     onChange={set("address")} required error={Boolean(errors.address)}
                     helperText={errors.address || (values.type === "usb" ? "0 for the first USB camera" : "For example http://192.168.1.21:8080/video")} />
          <FormControlLabel label="Enabled" control={
            <Switch checked={values.enabled} onChange={(e) => setValues((v) => ({ ...v, enabled: e.target.checked }))} />} />
          {message && <Alert severity="error">{message}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={busy}>Save camera</Button>
        </DialogActions>
      </Box>
    </Dialog>
  );
}

function UserRow({ user, cameraNames, onSave }) {
  const [role, setRole] = React.useState(user.role);
  const [cameras, setCameras] = React.useState(user.cameras || []);
  const [busy, setBusy] = React.useState(false);
  const changed = role !== user.role || (role !== "admin" && [...cameras].sort().join() !== [...(user.cameras || [])].sort().join());
  const toggle = (name) => setCameras((c) => (c.includes(name) ? c.filter((x) => x !== name) : [...c, name]));

  return (
    <Paper component="article" aria-label={user.username} sx={{ p: 2 }}>
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
        <Typography fontWeight={600} sx={{ minWidth: 120 }}>{user.username}</Typography>
        <TextField select size="small" label="Role" value={role} onChange={(e) => setRole(e.target.value)} sx={{ minWidth: 140 }}>
          {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
        </TextField>
      </Box>
      <Box sx={{ mt: 1.5 }}>
        {role === "admin" ? (
          <Typography variant="body2" color="text.secondary">Administrators can see every camera.</Typography>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>Cameras this user can see:</Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              {cameraNames.map((name) => (
                <Chip key={name} label={name} clickable onClick={() => toggle(name)}
                      color={cameras.includes(name) ? "primary" : "default"}
                      variant={cameras.includes(name) ? "filled" : "outlined"}
                      aria-pressed={cameras.includes(name)} />
              ))}
            </Box>
          </>
        )}
      </Box>
      <Button size="small" variant="contained" sx={{ mt: 1.5 }} disabled={!changed || busy}
              onClick={async () => {
                setBusy(true);
                // Send the camera choice too; administrators see every camera.
                try { await onSave(user, { role, cameras: role === "admin" ? [] : cameras }); } finally { setBusy(false); }
              }}>
        Save changes
      </Button>
    </Paper>
  );
}

// Administrators only: cameras (add, edit, remove) and who may see which camera.
function MockAdminPage() {
  const { token, ready } = useAuth();
  const me = useMe(ready ? token : null);
  const [tab, setTab] = React.useState(0);
  const [cameras, setCameras] = React.useState(null);
  const [users, setUsers] = React.useState(null);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState(null); // a camera object, or {} for a new one
  const [toDelete, setToDelete] = React.useState(null);
  const [notice, setNotice] = React.useState("");
  const isAdmin = Boolean(me && ["administrator", "admin"].includes(me.role));

  const load = React.useCallback(() => {
    listAdminCameras(token).then(setCameras).catch((e) => setError(e.message));
    listUsers(token).then(setUsers).catch((e) => setError(e.message));
  }, [token]);
  React.useEffect(() => { if (ready && isAdmin) load(); }, [ready, isAdmin, load]);

  async function saveCamera(values) {
    if (editing && editing.id) await updateCamera(token, editing.id, values);
    else await createCamera(token, values);
    setEditing(null);
    setNotice("Camera saved.");
    load();
  }

  async function confirmDelete() {
    const target = toDelete;
    setToDelete(null);
    try {
      await deleteCamera(token, target.id);
      setNotice("Camera removed.");
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function saveUser(user, body) {
    try {
      await updateUser(token, user.id, body);
      setNotice(`Saved ${user.username}.`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!ready) return null;
  return (
    <Layout token={token}>
      <Typography variant="h5" component="h1" sx={{ mb: 2 }}>Administration</Typography>
      {me && !isAdmin && <Alert severity="info">Only administrators can open this page.</Alert>}
      {!me && <LinearProgress aria-label="Checking access" />}
      {isAdmin && (
        <>
          {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>{error}</Alert>}
          <Tabs value={tab} onChange={(e, v) => setTab(v)} sx={{ mb: 2 }}>
            <Tab label="Cameras" />
            <Tab label="Users" />
          </Tabs>

          {tab === 0 && (
            <Box sx={{ display: "grid", gap: 1.5 }}>
              <Box><Button variant="contained" onClick={() => setEditing({})}>Add camera</Button></Box>
              {cameras === null && <LinearProgress aria-label="Loading cameras" />}
              {(cameras || []).map((c) => (
                <Paper key={c.id} component="article" aria-label={c.name} sx={{ p: 2 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, flexWrap: "wrap" }}>
                    <Typography fontWeight={600}>{c.name}</Typography>
                    <Box sx={{ display: "flex", gap: 1 }}>
                      <StatusChip status={c.enabled ? "enabled" : "disabled"} />
                      <StatusChip status={c.connection} />
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {c.type === "usb" ? `USB device ${c.address}` : c.address}
                  </Typography>
                  <Box sx={{ display: "flex", gap: 1, mt: 1.5 }}>
                    <Button size="small" onClick={() => setEditing(c)}>Edit</Button>
                    <Button size="small" color="error" onClick={() => setToDelete(c)}>Remove</Button>
                  </Box>
                </Paper>
              ))}
            </Box>
          )}

          {tab === 1 && (
            <Box sx={{ display: "grid", gap: 1.5 }}>
              {users === null && <LinearProgress aria-label="Loading users" />}
              {(users || []).map((u) => (
                <UserRow key={`${u.id}-${u.role}-${(u.cameras || []).join()}`} user={u}
                         cameraNames={(cameras || []).map((c) => c.name)} onSave={saveUser} />
              ))}
            </Box>
          )}
        </>
      )}

      <CameraDialog camera={editing} onClose={() => setEditing(null)} onSave={saveCamera} />
      <Dialog open={Boolean(toDelete)} onClose={() => setToDelete(null)}>
        <DialogTitle>Remove this camera?</DialogTitle>
        <DialogContent>
          <Typography>
            {toDelete && toDelete.name} will stop recording. Footage already recorded is kept.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setToDelete(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDelete}>Remove camera</Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice("")} message={notice} />
    </Layout>
  );
}

export default function AdminPage() {
  return USE_MOCK ? <MockAdminPage /> : <RealAdminPage />;
}

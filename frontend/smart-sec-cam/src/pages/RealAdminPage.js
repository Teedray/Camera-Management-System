import React from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, LinearProgress, MenuItem, Paper, Tab, Tabs, TextField, Typography } from "@mui/material";
import { assignCamera, createCamera, createUser, listAdminCameras,
  listCameraAssignments, listUsers, revokeCamera, updateUser } from "../api/adminApi";
import Layout from "../components/Layout";
import { patchCamera, explainUnsupported } from "../api/managementApi";
import useAuth from "../hooks/useAuth";
import useMe from "../hooks/useMe";

const ROLES = ["administrator", "manager", "viewer"];
const EMPTY_CAMERA = { id: "", name: "", location: "", channel_name: "" };
const EMPTY_USER = { username: "", password: "", role: "viewer" };

function RoleRow({ user, save, preventDemotion }) {
  const [role, setRole] = React.useState(user.role);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => setRole(user.role), [user.role]);
  return <Paper sx={{ p: 2 }}>
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
      <Box sx={{ flex: 1, minWidth: 145 }}><Typography fontWeight={600}>{user.username}</Typography>
        <Typography variant="caption" color="text.secondary">{user.id} · Account status: {user.status || (user.enabled === true ? "Enabled" : user.enabled === false ? "Disabled" : "Not reported")}</Typography></Box>
      <TextField select size="small" label="Role" value={role} onChange={e => setRole(e.target.value)} sx={{ minWidth: 155 }}>
        {ROLES.map(r => <MenuItem value={r} key={r}>{r}</MenuItem>)}
      </TextField>
      <Button variant="contained" disabled={busy || role === user.role || (preventDemotion && role !== "administrator")} onClick={async () => {
        setBusy(true); setError("");
        try { await save(user.id, role); } catch (e) { setError(e.message); }
        finally { setBusy(false); }
      }}>Save role</Button>
    </Box>
    {preventDemotion && <Typography variant="caption" color="warning.main">The final administrator cannot be demoted.</Typography>}
    {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
  </Paper>;
}

export default function RealAdminPage() {
  const { token, ready } = useAuth();
  const me = useMe(ready ? token : null);
  const [tab, setTab] = React.useState(0);
  const [cameras, setCameras] = React.useState([]);
  const [users, setUsers] = React.useState([]);
  const [assignments, setAssignments] = React.useState([]);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [dialog, setDialog] = React.useState("");
  const [newCamera, setNewCamera] = React.useState(EMPTY_CAMERA);
  const [newUser, setNewUser] = React.useState(EMPTY_USER);
  const [editingCamera, setEditingCamera] = React.useState(null);
  const [streamAddress, setStreamAddress] = React.useState("");
  const [targetUser, setTargetUser] = React.useState("");
  const [targetCamera, setTargetCamera] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const isAdmin = me?.role === "administrator";

  const load = React.useCallback(async () => {
    setError("");
    try {
      const [cs, us, as] = await Promise.all([
        listAdminCameras(token), listUsers(token), listCameraAssignments(token)
      ]);
      setCameras(cs); setUsers(us); setAssignments(as);
    } catch (err) { setError(err.message); }
    finally { setLoaded(true); }
  }, [token]);
  React.useEffect(() => { if (ready && isAdmin) load(); }, [ready, isAdmin, load]);

  async function saveCameraEdit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (!editingCamera.name.trim() || !editingCamera.channel_name.trim() || !editingCamera.location.trim()) throw new Error("Complete required fields.");
      if (editingCamera.stream_address && !/^(rtsp|rtsps|http|https):\/\/[^\s]+$/i.test(editingCamera.stream_address)) throw new Error("Use an RTSP or HTTP(S) stream address.");
      await patchCamera(token, editingCamera.id, {
        name: editingCamera.name.trim(), location: editingCamera.location.trim(),
        channel_name: editingCamera.channel_name.trim(), enabled: Boolean(editingCamera.enabled),
        stream_address: editingCamera.stream_address || null,
      });
      setDialog(""); setEditingCamera(null); setNotice("Camera settings saved by backend."); await load();
    } catch (err) { setError(explainUnsupported(err, "Editing a camera")); }
    finally { setBusy(false); }
  }
  async function createCameraAction(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const data = Object.fromEntries(Object.entries(newCamera).map(([k,v]) => [k, v.trim()]));
      if (Object.values(data).some(v => !v)) throw new Error("All camera fields are required.");
      if (streamAddress.trim() && !/^(rtsp|rtsps|http|https):\/\/[^\s]+$/i.test(streamAddress.trim())) throw new Error("Stream address must start with rtsp:// or http(s)://.");
      await createCamera(token, data);
      // Camera registration succeeds independently of camera assignment.
      let result = "Camera registered.";
      if (me?.id) {
        try {
          await assignCamera(token, me.id, data.id);
          result = "Camera registered and assigned to your account.";
        } catch (assignmentError) {
          result = `Camera registered, but assigning it to your account failed: ${assignmentError.message}`;
        }
      }
      if (streamAddress.trim()) {
        try { await patchCamera(token, data.id, {stream_address:streamAddress.trim()}); }
        catch (err) { result += " Stream address was NOT saved: " + explainUnsupported(err, "Stream configuration"); }
      }
      setDialog(""); setNewCamera(EMPTY_CAMERA); setStreamAddress(""); await load(); setNotice(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function createUserAction(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (!newUser.username.trim() || !newUser.password) throw new Error("Username and password are required.");
      await createUser(token, { ...newUser, username: newUser.username.trim() });
      setDialog(""); setNewUser(EMPTY_USER); setNotice("User created."); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function saveRole(userId, role) {
    const target=users.find(u=>u.id===userId);
    if(target?.role==="administrator" && role!=="administrator" && users.filter(u=>u.role==="administrator").length<=1) throw new Error("The last administrator cannot be demoted.");
    await updateUser(token, userId, { role });
    setNotice("Role updated."); await load();
  }
  async function setCameraAccess(grant) {
    if (!targetUser || !targetCamera) return;
    setBusy(true); setError("");
    try {
      if (grant) await assignCamera(token, targetUser, targetCamera);
      else await revokeCamera(token, targetUser, targetCamera);
      setNotice(grant ? "Access granted." : "Access revoked."); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  const currentlyAssigned = assignments.some(a => a.user_id === targetUser && a.camera_id === targetCamera);
  if (!ready) return null;
  return <Layout token={token}>
    <Typography variant="h5" component="h1" sx={{ mb: 1 }}>Administration</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Users, cameras and access permissions</Typography>
    {!me && <LinearProgress aria-label="Checking administrator access" />}
    {me && !isAdmin && <Alert severity="warning">Administrator access required.</Alert>}
    {isAdmin && <>
      {error && <Alert severity="error" onClose={() => setError("")} sx={{ mb: 2 }}>{error}</Alert>}
      {notice && <Alert severity="success" onClose={() => setNotice("")} sx={{ mb: 2 }}>{notice}</Alert>}
      {!loaded && <LinearProgress />}
      <Tabs value={tab} onChange={(e,v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" scrollButtons="auto">
        <Tab label="Cameras"/><Tab label="Users"/><Tab label="Assignments"/>
      </Tabs>
      {tab === 0 && <Box sx={{ display: "grid", gap: 1.5 }}>
        <Box><Button variant="contained" onClick={() => setDialog("camera")}>Add camera</Button></Box>
        {cameras.length === 0 && loaded && <Alert severity="info">No registered cameras.</Alert>}
        {cameras.map(c => <Paper key={c.id} sx={{ p: 2 }}>
          <Box sx={{ display:"flex", justifyContent:"space-between", gap: 1 }}>
            <Typography fontWeight={600}>{c.name}</Typography>
            <Box sx={{display:"flex",gap:1}}><Chip size="small" label={c.enabled ? "Enabled" : "Disabled"}/><Button size="small" variant="outlined" onClick={()=>{setEditingCamera({...c,stream_address:c.stream_address||""});setDialog("edit-camera");}}>Edit / enable</Button></Box>
          </Box>
          <Typography variant="body2" color="text.secondary">{c.location} · Channel: {c.channel_name} · ID: {c.id}</Typography>
        </Paper>)}
        <Typography variant="caption" color="text.secondary">Editing and stream configuration forms require the PATCH camera endpoint. The running backend currently lacks it.</Typography>
      </Box>}
      {tab === 1 && <Box sx={{ display: "grid", gap: 1.5 }}>
        <Box><Button variant="contained" onClick={() => setDialog("user")}>Add user</Button></Box>
        {users.length === 0 && loaded && <Alert severity="info">No users returned.</Alert>}
        {users.map(u => <RoleRow key={u.id} user={u} save={saveRole}
          preventDemotion={u.role==="administrator" && users.filter(a=>a.role==="administrator").length<=1}/>)}
      </Box>}
      {tab === 2 && <Paper sx={{ p: 2, display:"grid", gap:2, maxWidth:560 }}>
        <Typography variant="body2" color="text.secondary">Choose a user and camera. Assigned access is shown below; it is not assumed from the user's role.</Typography>
        <TextField select label="User" fullWidth value={targetUser} onChange={e => setTargetUser(e.target.value)}>
          {users.map(u => <MenuItem key={u.id} value={u.id}>{u.username} ({u.role})</MenuItem>)}
        </TextField>
        <TextField select label="Camera" fullWidth value={targetCamera} onChange={e => setTargetCamera(e.target.value)}>
          {cameras.map(c => <MenuItem key={c.id} value={c.id}>{c.name} ({c.id})</MenuItem>)}
        </TextField>
        {targetUser && targetCamera && <Chip label={currentlyAssigned ? "Currently assigned" : "Not assigned"}
          color={currentlyAssigned ? "success" : "default"} sx={{ width:"fit-content" }} />}
        <Box sx={{ display:"flex", gap:1 }}>
          <Button variant="contained" disabled={busy || !targetUser || !targetCamera || currentlyAssigned}
            onClick={() => setCameraAccess(true)}>Grant access</Button>
          <Button variant="outlined" color="error" disabled={busy || !targetUser || !targetCamera || !currentlyAssigned}
            onClick={() => setCameraAccess(false)}>Revoke access</Button>
        </Box>
      </Paper>}
    </>}
    <Dialog open={dialog === "camera"} onClose={busy ? undefined : () => setDialog("")} fullWidth maxWidth="sm">
      <DialogTitle>Register camera</DialogTitle>
      <Box component="form" onSubmit={createCameraAction}><DialogContent sx={{ display:"grid",gap:2 }}>
        {[["id","Camera ID"],["name","Display name"],["location","Location"],["channel_name","Recording channel name"]].map(([key,label]) =>
          <TextField key={key} label={label} required value={newCamera[key]} onChange={e => setNewCamera(p => ({...p,[key]:e.target.value}))}/>)}
        <TextField label="Stream address (optional)" placeholder="rtsp://host/stream" value={streamAddress} onChange={e=>setStreamAddress(e.target.value)} helperText="The server must support camera address configuration to persist this field."/>
        <Alert severity="info">Registration is separate from stream configuration. If the backend lacks camera PATCH, an entered address will not be saved.</Alert>
      </DialogContent><DialogActions><Button disabled={busy} onClick={() => setDialog("")}>Cancel</Button>
        <Button disabled={busy} variant="contained" type="submit">Register</Button></DialogActions></Box>
    </Dialog>
    <Dialog open={dialog === "edit-camera" && Boolean(editingCamera)} onClose={busy?undefined:()=>setDialog("")} fullWidth maxWidth="sm">
      <DialogTitle>Edit camera settings</DialogTitle>
      {editingCamera && <Box component="form" onSubmit={saveCameraEdit}><DialogContent sx={{display:"grid",gap:2}}>
        <Typography variant="caption" color="text.secondary">Camera ID: {editingCamera.id}</Typography>
        {[["name","Camera name"],["location","Location"],["channel_name","Recording channel"]].map(([key,label])=><TextField key={key} required label={label} value={editingCamera[key]||""} onChange={e=>setEditingCamera(c=>({...c,[key]:e.target.value}))}/>)}
        <TextField label="Stream address" value={editingCamera.stream_address||""} onChange={e=>setEditingCamera(c=>({...c,stream_address:e.target.value}))} placeholder="rtsp://host/stream"/>
        <TextField select label="Camera status" value={editingCamera.enabled?"enabled":"disabled"} onChange={e=>setEditingCamera(c=>({...c,enabled:e.target.value==="enabled"}))}><MenuItem value="enabled">Enabled</MenuItem><MenuItem value="disabled">Disabled</MenuItem></TextField>
        <Alert severity="info">Saving requires backend PATCH /api/v1/cameras/:id. No local-only changes will be shown as persisted.</Alert>
      </DialogContent><DialogActions><Button disabled={busy} onClick={()=>setDialog("")}>Cancel</Button><Button type="submit" variant="contained" disabled={busy}>Save changes</Button></DialogActions></Box>}
    </Dialog>
    <Dialog open={dialog === "user"} onClose={busy ? undefined : () => setDialog("")} fullWidth maxWidth="sm">
      <DialogTitle>Create user</DialogTitle>
      <Box component="form" onSubmit={createUserAction}><DialogContent sx={{ display:"grid",gap:2 }}>
        <TextField label="Username" required value={newUser.username} onChange={e=>setNewUser(p=>({...p,username:e.target.value}))}/>
        <TextField label="Password" type="password" required value={newUser.password} onChange={e=>setNewUser(p=>({...p,password:e.target.value}))}/>
        <TextField select label="Role" value={newUser.role} onChange={e=>setNewUser(p=>({...p,role:e.target.value}))}>
          {ROLES.map(r=><MenuItem key={r} value={r}>{r}</MenuItem>)}
        </TextField>
      </DialogContent><DialogActions><Button disabled={busy} onClick={() => setDialog("")}>Cancel</Button>
        <Button disabled={busy} variant="contained" type="submit">Create user</Button></DialogActions></Box>
    </Dialog>
  </Layout>;
}

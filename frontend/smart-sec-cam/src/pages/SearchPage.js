import { USE_MOCK } from "../config";
import RealSearchPage from "./RealSearchPage";
import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import BookmarkAddOutlinedIcon from "@mui/icons-material/BookmarkAddOutlined";
import ContentCutIcon from "@mui/icons-material/ContentCut";
import { useNavigate } from "react-router-dom";

import { ApiError, fetchCameras, searchRecordings } from "../api/recordingsApi";
import ExportDialog from "../components/ExportDialog";
import IncidentDialog from "../components/IncidentDialog";
import Layout from "../components/Layout";
import ResultsList from "../components/ResultsList";
import SearchForm from "../components/SearchForm";
import SegmentPlayer from "../components/SegmentPlayer";
import TimelineBar from "../components/TimelineBar";
import useAuth from "../hooks/useAuth";
import { toGaps, toSegments } from "../utils/playbackPlan";
import { DEFAULT_TZ, formatDate, formatDuration } from "../utils/time";

// F03 Search and Review: pick a camera and a time range, see what footage exists
// (and where it is missing or expired), and play it back continuously.
function MockSearchPage() {
  const { token, ready } = useAuth();
  const [cameras, setCameras] = React.useState(null);
  const [cameraError, setCameraError] = React.useState("");
  const [status, setStatus] = React.useState("idle"); // idle | loading | done | error
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [posMs, setPosMs] = React.useState(null);
  const [seekRequest, setSeekRequest] = React.useState(null);
  const [dialog, setDialog] = React.useState(null); // "incident" | "export" | null
  const [savedNotice, setSavedNotice] = React.useState("");
  const navigate = useNavigate();
  const latestSearch = React.useRef(0);
  const nonce = React.useRef(0);

  React.useEffect(() => {
    if (!ready) return;
    fetchCameras(token).then(setCameras).catch((e) => {
      setCameras([]);
      setCameraError(e.message);
    });
  }, [ready, token]);

  const segments = React.useMemo(() => (result ? toSegments(result.segments) : []), [result]);
  const gaps = React.useMemo(() => (result ? toGaps(result.gaps) : []), [result]);
  const tz = (result && result.timezone) || DEFAULT_TZ;

  function seek(ms, play) {
    nonce.current += 1;
    setSeekRequest({ ms, play, nonce: nonce.current });
  }

  async function handleSearch(values) {
    const mine = latestSearch.current + 1;
    latestSearch.current = mine;
    setStatus("loading");
    setError(null);
    try {
      const data = await searchRecordings(values, token);
      if (mine !== latestSearch.current) return; // a newer search replaced this one
      setResult(data);
      setPosMs(null);
      setStatus("done");
      const first = toSegments(data.segments)[0];
      if (first) seek(first.startMs, false); // show the first frame, ready to play
    } catch (err) {
      if (mine !== latestSearch.current) return;
      setResult(null);
      setError(err instanceof ApiError ? err : new ApiError("Something went wrong. Please try again."));
      setStatus("error");
    }
  }

  if (!ready) return null;

  const rangeStart = result ? Date.parse(result.range.start) : 0;
  const rangeEnd = result ? Date.parse(result.range.end) : 0;

  return (
    <Layout token={token}>
      <Typography variant="h5" component="h1" sx={{ mb: 2 }}>Search and review footage</Typography>
      {cameraError && <Alert severity="error" sx={{ mb: 2 }}>{cameraError}</Alert>}
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "minmax(300px, 380px) 1fr" }, alignItems: "start" }}>
        <Paper sx={{ p: 2, order: { xs: 1, md: 1 } }}>
          <SearchForm cameras={cameras} loading={status === "loading"}
                      serverError={error} onSearch={handleSearch} onEdit={() => setError(null)} />
          {error && !error.field && <Alert severity="error" sx={{ mt: 2 }}>{error.message}</Alert>}
        </Paper>

        <Paper sx={{ p: 2, order: { xs: 2, md: 2 }, gridRow: { md: "span 2" } }}>
          <Box sx={{ display: "flex", gap: 1, mb: 1.5, flexWrap: "wrap" }}>
            <Button variant="outlined" startIcon={<BookmarkAddOutlinedIcon />}
                    disabled={segments.length === 0} onClick={() => setDialog("incident")}>
              Save as incident
            </Button>
            <Button variant="outlined" startIcon={<ContentCutIcon />}
                    disabled={segments.length === 0} onClick={() => setDialog("export")}>
              Trim and download
            </Button>
          </Box>
          <SegmentPlayer segments={segments} token={token} tz={tz} seekRequest={seekRequest} onPosition={setPosMs} />
          {result && rangeEnd > rangeStart && (
            <Box sx={{ mt: 2 }}>
              <TimelineBar rangeStartMs={rangeStart} rangeEndMs={rangeEnd} segments={segments} gaps={gaps}
                           posMs={posMs} tz={tz} onSeek={(ms) => seek(ms, true)} />
            </Box>
          )}
        </Paper>

        <Paper sx={{ p: 2, order: { xs: 3, md: 3 } }}>
          {status === "loading" && <LinearProgress aria-label="Searching" />}
          {status === "idle" && (
            <Typography variant="body2" color="text.secondary">
              Choose a camera, a date and a time range, then press Search.
            </Typography>
          )}
          {status === "done" && result && (
            <>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {result.camera} · {formatDate(rangeStart, tz)}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {formatDuration(result.summary.available_seconds)} of footage
                {result.summary.missing_seconds > 0 && ` · ${formatDuration(result.summary.missing_seconds)} missing`}
                {result.summary.expired_seconds > 0 && ` · ${formatDuration(result.summary.expired_seconds)} expired`}
              </Typography>
              <ResultsList segments={segments} gaps={gaps} tz={tz} activeMs={posMs}
                           onPlay={(run) => seek(run.startMs, true)}
                           onGap={(gap) => seek(gap.startMs, true)} />
            </>
          )}
        </Paper>
      </Box>
      {result && (
        <>
          <IncidentDialog open={dialog === "incident"} onClose={() => setDialog(null)} token={token}
                          camera={result.camera} rangeStartMs={rangeStart} rangeEndMs={rangeEnd} posMs={posMs} tz={tz}
                          onSaved={() => setSavedNotice("Incident clip saved.")} />
          <ExportDialog open={dialog === "export"} onClose={() => setDialog(null)} token={token}
                        camera={result.camera} rangeStartMs={rangeStart} rangeEndMs={rangeEnd} posMs={posMs} tz={tz} />
        </>
      )}
      <Snackbar open={Boolean(savedNotice)} autoHideDuration={6000} onClose={() => setSavedNotice("")}
                message={savedNotice}
                action={<Button color="inherit" size="small" onClick={() => navigate("/incidents")}>View</Button>} />
    </Layout>
  );
}

export default function SearchPage() {
  return USE_MOCK ? <MockSearchPage /> : <RealSearchPage />;
}

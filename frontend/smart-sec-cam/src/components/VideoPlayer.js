import { useEffect, useRef, useState } from 'react';
import ReactPlayer from 'react-player'

const SERVER_URL = "https://localhost:8443"
const VIDEO_ENDPOINT = "/api/video/"

export default function VideoPlayer(props) {
    const player = useRef(null);
    const pendingDownload = useRef(null);
    const [start, setStart] = useState("0");
    const [end, setEnd] = useState("");
    const [duration, setDuration] = useState(null);
    const [processing, setProcessing] = useState(false);
    const [status, setStatus] = useState("");

    useEffect(() => () => pendingDownload.current?.abort(), []);

    if (!props.videoFileName) return null;

    const videoUrl = SERVER_URL + VIDEO_ENDPOINT + encodeURIComponent(props.videoFileName)
        + "?token=" + encodeURIComponent(props.token);

    async function downloadClip(event) {
        event.preventDefault();
        if (pendingDownload.current) return;
        if (start === "" || end === "" || Number(start) >= Number(end)) {
            setStatus("Enter an end time greater than the start time.");
            return;
        }
        setProcessing(true);
        setStatus("Processing clip…");
        const controller = new AbortController();
        pendingDownload.current = controller;
        try {
            const response = await fetch(SERVER_URL + "/api/v1/exports", {
                method: "POST",
                signal: controller.signal,
                headers: { "Content-Type": "application/json", "x-access-token": props.token },
                body: JSON.stringify({
                    filename: props.videoFileName,
                    start_time: Number(start),
                    end_time: Number(end)
                })
            });
            if (!response.ok) {
                const { error } = await response.json().catch(() => ({}));
                throw new Error(error || "The clip could not be exported.");
            }
            const clip = await response.blob();
            if (controller.signal.aborted) return;
            const url = URL.createObjectURL(clip);
            const link = document.createElement("a");
            link.href = url;
            link.download = "clip.mp4";
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            setStatus("MP4 download started.");
        } catch (error) {
            if (!controller.signal.aborted) setStatus(error.message);
        } finally {
            pendingDownload.current = null;
            if (!controller.signal.aborted) setProcessing(false);
        }
    }

    function usePlaybackTime(setTime) {
        const time = player.current?.getCurrentTime();
        if (Number.isFinite(time)) setTime(String(time));
    }

    return (
        <>
            <form onSubmit={downloadClip} aria-label="Trim and download recording">
                <fieldset disabled={processing}>
                    <legend>Trim and download</legend>
                    <label>
                        Start (seconds)
                        <input type="number" min="0" max={duration ?? undefined} step="any"
                            required value={start} onChange={event => setStart(event.target.value)} />
                    </label>
                    <button type="button" onClick={() => usePlaybackTime(setStart)}>Use current time for start</button>
                    <label>
                        End (seconds)
                        <input type="number" min="0" max={duration ?? undefined} step="any"
                            required value={end} onChange={event => setEnd(event.target.value)} />
                    </label>
                    <button type="button" onClick={() => usePlaybackTime(setEnd)}>Use current time for end</button>
                    <button type="submit">Download MP4</button>
                </fieldset>
                <p role="status">{status}</p>
            </form>
            <ReactPlayer ref={player} url={videoUrl} width="100%" height="90vh" controls
                onDuration={seconds => { if (Number.isFinite(seconds)) setDuration(seconds); }} />
        </>
    );
}

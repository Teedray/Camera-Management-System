"""Browser-playable, real-time MP4 and WebM encoding.

OpenCV's pip wheels cannot encode H.264, and their ``mp4v`` codec (MPEG-4
Part 2) does not play in Chrome, Edge or Firefox. OpenCV's VP9 encoder uses
libvpx's slowest settings: about 140 s of CPU per 30 s segment, so continuous
recording falls further behind with every segment. Both encodings are
therefore made by piping raw frames into ffmpeg: H.264 (libx264) for MP4 and
real-time VP9 (libvpx-vp9) for WebM. The ffmpeg binary comes
from the ``imageio-ffmpeg`` package (or ``ffmpeg`` on PATH), so no system
package is required in the Docker images.
"""
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple

import cv2


def ffmpeg_executable() -> Optional[str]:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


H264_ARGS = (
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
    # Put the index first so playback can start before the whole file loads.
    "-movflags", "+faststart",
)
VP9_REALTIME_ARGS = (
    "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
    "-row-mt", "1", "-b:v", "0", "-crf", "35",
)


class FFmpegWriter:
    """A ``cv2.VideoWriter``-like object that encodes through an ffmpeg pipe."""

    def __init__(self, path: str, fps: float, size: Tuple[int, int], executable: str,
                 codec_args=H264_ARGS):
        self.path = path
        self.size = tuple(size)
        self.failed = False
        width, height = self.size
        command = [
            executable, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
            "-framerate", f"{fps:.6f}", "-i", "-",
            "-an", *codec_args,
            # yuv420p needs even dimensions; it is what browsers decode.
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", path,
        ]
        # A file rather than a pipe, so error output can never block the encoder.
        self.errors = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                            stdout=subprocess.DEVNULL, stderr=self.errors)
        except OSError:
            self.errors.close()
            self.process = None
            self.failed = True

    def isOpened(self) -> bool:
        return self.process is not None and not self.failed

    def write(self, frame) -> None:
        if not self.isOpened():
            return
        if (frame.shape[1], frame.shape[0]) != self.size:
            frame = cv2.resize(frame, self.size)
        try:
            self.process.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            self.failed = True

    def release(self) -> bool:
        """Finish the file; returns False if ffmpeg reported a failure."""
        if self.process is None:
            return False
        try:
            self.process.stdin.close()
        except OSError:
            self.failed = True
        if self.process.wait() != 0:
            self.failed = True
        self.errors.seek(0)
        error = self.errors.read().decode(errors="replace").strip()
        self.errors.close()
        if self.failed and error:
            print(f"Video encoding failed: {error}")
        self.process = None
        return not self.failed


# Kept for callers and tests that name the MP4 writer.
H264Writer = FFmpegWriter


def open_mp4_writer(path: str, fps: float, size: Tuple[int, int]):
    """Return an H.264 writer, or OpenCV's ``mp4v`` writer if ffmpeg is unavailable."""
    executable = ffmpeg_executable()
    if executable:
        return FFmpegWriter(path, fps, size, executable, H264_ARGS)
    print("ffmpeg not found; writing mp4v MP4, which most desktop browsers cannot play")
    return cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, tuple(size))


def open_webm_writer(path: str, fps: float, size: Tuple[int, int]):
    """Return a real-time VP9 writer, or OpenCV's (much slower) VP9 writer without ffmpeg."""
    executable = ffmpeg_executable()
    if executable:
        return FFmpegWriter(path, fps, size, executable, VP9_REALTIME_ARGS)
    print("ffmpeg not found; OpenCV VP9 encoding is slower than real time")
    return cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"VP90"), fps, tuple(size))

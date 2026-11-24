"""Browser-playable MP4 encoding.

OpenCV's pip wheels cannot encode H.264, and their ``mp4v`` codec (MPEG-4
Part 2) does not play in Chrome, Edge or Firefox. MP4 recordings are therefore
encoded by piping raw frames into ffmpeg with libx264. The ffmpeg binary comes
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


class H264Writer:
    """A ``cv2.VideoWriter``-like object that writes H.264 MP4 through ffmpeg."""

    def __init__(self, path: str, fps: float, size: Tuple[int, int], executable: str):
        self.path = path
        self.size = tuple(size)
        self.failed = False
        width, height = self.size
        command = [
            executable, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
            "-framerate", f"{fps:.6f}", "-i", "-",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            # yuv420p needs even dimensions; it is what browsers decode.
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
            # Put the index first so playback can start before the whole file loads.
            "-movflags", "+faststart", path,
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
            print(f"H.264 encoding failed: {error}")
        self.process = None
        return not self.failed


def open_mp4_writer(path: str, fps: float, size: Tuple[int, int]):
    """Return an H.264 writer, or OpenCV's ``mp4v`` writer if ffmpeg is unavailable."""
    executable = ffmpeg_executable()
    if executable:
        return H264Writer(path, fps, size, executable)
    print("ffmpeg not found; writing mp4v MP4, which most desktop browsers cannot play")
    return cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, tuple(size))

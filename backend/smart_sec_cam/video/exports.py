from math import isfinite

import cv2


class InvalidClipRange(ValueError):
    pass


def export_clip(source, destination, start, end):
    """Write the requested part of a recording to a separate MP4 file."""
    video = cv2.VideoCapture(str(source))
    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not video.isOpened() or not isfinite(fps) or min(fps, frame_count, width, height) <= 0:
            raise OSError("Recording could not be opened")
        if not 0 <= start < end <= frame_count / fps:
            raise InvalidClipRange("Select a range within the recording")

        first_frame = round(start * fps)
        last_frame = min(round(end * fps), int(frame_count))
        if first_frame >= last_frame:
            raise InvalidClipRange("Select an interval of at least one frame")
        if first_frame and not video.set(cv2.CAP_PROP_POS_FRAMES, first_frame):
            raise OSError("Could not seek to the selected frame")

        writer = cv2.VideoWriter(
            str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
        )
        try:
            if not writer.isOpened():
                raise OSError("MP4 encoder could not be opened")
            for _ in range(first_frame, last_frame):
                success, frame = video.read()
                if not success:
                    raise OSError("Recording ended before the selected end time")
                writer.write(frame)
        finally:
            writer.release()
    finally:
        video.release()

    result = cv2.VideoCapture(str(destination))
    try:
        if not result.isOpened() or result.get(cv2.CAP_PROP_FRAME_COUNT) != last_frame - first_frame:
            raise OSError("The exported clip could not be verified")
    finally:
        result.release()

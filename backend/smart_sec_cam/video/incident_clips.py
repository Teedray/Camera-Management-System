import cv2
from pathlib import Path
from uuid import uuid4

from smart_sec_cam.video.incident_database import IncidentDatabase

class IncidentClipManager:
    def __init__(
        self,
        video_dir="data/videos/",
        archive_dir="data/incident_archive/",
        authorization_check=None
    ):
        self.video_dir = Path(video_dir)
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.incident_db = IncidentDatabase()
        self.authorization_check = authorization_check 

    def validate_video(self, filename: str) -> bool:
        video_path = self.video_dir / filename

        # Only allow filenames within the recording directory
        if Path(filename).name != filename:
            print("Invalid video filename")
            return False

        if video_path.is_file():
            print(f"Video found: {filename}")
            return True
        else:
            print(f"Video not found: {filename}")
            return False

    def validate_time_range(self, start_time, end_time, video_duration):
        if (
            0 <= start_time < end_time <= video_duration
        ):
            print("Valid time range")
            return True
        else:
            print("Invalid time range")
            return False

    def get_video_duration(self, filename):
        if not self.validate_video(filename):
            return None

        video_path = self.video_dir / filename
        video = cv2.VideoCapture(str(video_path))

        if not video.isOpened():
            print("Unable to open video")
            video.release()
            return None

        try:
            fps = video.get(cv2.CAP_PROP_FPS)
            frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        finally:
            video.release()

        if fps <= 0 or frame_count <= 0:
            print("Invalid video frame rate or frame count")
            return None

        duration = frame_count / fps
        return duration

    def save_incident_clip(self, filename, start_time, end_time, user_id):

        if not self.is_authorized(user_id):
            print("Access denied: management authorization required")
            return False
            
        # Retrieve the video's duration
        video_duration = self.get_video_duration(filename)

        if video_duration is None:
            print("Cannot save clip: invalid video")
            return False

        # Validate the selected time range
        if not self.validate_time_range(
            start_time, end_time, video_duration
        ):
            print("Cannot save clip: invalid time range")
            return False

        # Open the original video
        video_path = self.video_dir / filename
        video = cv2.VideoCapture(str(video_path))

        if not video.isOpened():
            print("Cannot open source video")
            video.release()
            return False

        fps = video.get(cv2.CAP_PROP_FPS)
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if fps <= 0 or width <= 0 or height <= 0:
            video.release()
            print("Invalid source video properties")
            return False

        # Convert seconds into frame positions
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps)

        if end_frame <= start_frame:
            video.release()
            print("Selected interval contains no complete frames")
            return False

        video.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Generate a unique archive filename
        output_path = self.archive_dir / (
            f"incident_{Path(filename).stem}_"
            f"{start_frame}_{end_frame}_{uuid4().hex}.mp4"
        )

        # Prepare the output video
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height)
        )

        if not writer.isOpened():
            video.release()
            writer.release()
            print("Cannot create incident clip")
            return False

        # Extract the selected frames
        frames_written = 0

        try:
            for _ in range(start_frame, end_frame):
                success, frame = video.read()

                if not success:
                    break

                writer.write(frame)
                frames_written += 1
        finally:
            video.release()
            writer.release()

        # Verify the extracted footage
        if frames_written != end_frame - start_frame:
            output_path.unlink(missing_ok=True)
            print("Failed to extract the complete incident clip")
            return False

        saved_video = cv2.VideoCapture(str(output_path))
        saved_ok = (
            saved_video.isOpened()
            and saved_video.get(cv2.CAP_PROP_FRAME_COUNT)
            >= frames_written
        )
        saved_video.release()

        if not saved_ok:
            output_path.unlink(missing_ok=True)
            print("Saved incident clip could not be verified")
            return False

        # Save the incident information in SQLite
        clip_id = uuid4().hex

        try:
            self.incident_db.add_incident(
                clip_id,
                output_path.name,
                Path(filename).stem.split("__")[0],
                start_time,
                end_time
            )

        except Exception as error:
            output_path.unlink(missing_ok=True)
            print(f"Failed to save incident record: {error}")
            return False

        print(f"Incident clip saved: {output_path}")
        print(f"Incident ID: {clip_id}")
        return True

    def is_authorized(self, user_id):
        if self.authorization_check is None:
            return False

        return self.authorization_check(user_id) is True

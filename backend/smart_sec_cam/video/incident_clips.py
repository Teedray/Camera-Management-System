from pathlib import Path

class IncidentClipManager:
    def __init__(self, video_dir="data/videos/", archive_dir="data/incident_archive/"):
        self.video_dir = Path(video_dir)
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def validate_video(self, filename: str) -> bool:
        video_path = self.video_dir / filename

        if video_path.is_file():
            print(f"Video found: {filename}")
            return True
        else:
            print(f"Video not found: {filename}")
            return False

    def validate_time_range(self, start_time, end_time, video_duration):
        if start_time >= 0 and start_time < end_time and end_time <= video_duration:
            print("Valid time range")
            return True
        else:
            print("Invalid time range")
            return False
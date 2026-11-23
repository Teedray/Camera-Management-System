import sqlite3
from pathlib import Path 

class IncidentDatabase:
	def __init__(self, db_path="data/incidents.db"):
		self.db_path = Path(db_path)
		self.db_path.parent.mkdir(parents=True, exist_ok=True)

		self.conn = sqlite3.connect(self.db_path)
		self.setup()

	def setup(self):
		cursor = self.conn.cursor()
		
		cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_clips (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                camera TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                incident_flag INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            )
        """)

        # Check existing columns
		cursor.execute("PRAGMA table_info(incident_clips)")
		columns = [row[1] for row in cursor.fetchall()]

        # Add missing columns to existing databases
		if "title" not in columns:
			cursor.execute(
                "ALTER TABLE incident_clips "
                "ADD COLUMN title TEXT NOT NULL DEFAULT ''"
            )
			
		if "notes" not in columns:
			cursor.execute(
                "ALTER TABLE incident_clips "
                "ADD COLUMN notes TEXT NOT NULL DEFAULT ''"
            )
			
		self.conn.commit()

	def add_incident(self, clip_id, filename, camera, start_time, end_time, title="", notes=""):
		cursor = self.conn.cursor()

		cursor.execute("""
			INSERT INTO incident_clips
			(id, filename, camera, start_time, end_time, incident_flag, title, notes)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""", (
			clip_id,
			filename,
			camera,
			start_time,
			end_time,
			1,
			title,
			notes
		))

		self.conn.commit()
		print(f"Incident recorded: {clip_id}")

	def get_incident(self, clip_id):
		cursor = self.conn.cursor()
		
		cursor.execute(
            "SELECT * FROM incident_clips WHERE id = ?",
            (clip_id,)
        )
		
		incident = cursor.fetchone()
		
		if incident is None:
			print(f"Incident not found: {clip_id}")
			return None
		
		return incident

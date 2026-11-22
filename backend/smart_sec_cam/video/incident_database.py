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
				incident_flag INTEGER NOT NULL DEFAULT 1 
			)
		""")

		self.conn.commit()

	def add_incident(self, clip_id, filename, camera, start_time, end_time):
		cursor = self.conn.cursor()

		cursor.execute("""
			INSERT INTO incident_clips
			(id, filename, camera, start_time, end_time, incident_flag)
			VALUES (?, ?, ?, ?, ?, ?)
		""", (
			clip_id,
			filename,
			camera,
			start_time,
			end_time,
			1
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

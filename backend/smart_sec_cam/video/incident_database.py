import re
import sqlite3
from pathlib import Path

class IncidentDatabase:
	"""IncidentRepository (SDS 3.1): incident records, flags and archive references.

	Pass ``conn`` to store incidents in the shared SQL database alongside
	accounts, cameras and the recording catalogue (SDS 2.3.1, Data Storage
	Layer). Without it, a standalone database file is opened at ``db_path``.
	"""

	def __init__(self, db_path="data/incidents.db", conn=None):
		if conn is not None:
			self.db_path = None
			self.conn = conn
		else:
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

        # Accountability fields (who saved the clip and when, in UTC)
		if "created_by" not in columns:
			cursor.execute(
                "ALTER TABLE incident_clips "
                "ADD COLUMN created_by TEXT"
            )

		if "created_at" not in columns:
			cursor.execute(
                "ALTER TABLE incident_clips "
                "ADD COLUMN created_at TEXT"
            )

		# The recording an incident was cut from. ``filename`` is the archived
		# clip's own name, so retention cleanup needs this to keep the source.
		if "source_filename" not in columns:
			cursor.execute(
                "ALTER TABLE incident_clips "
                "ADD COLUMN source_filename TEXT"
            )
			self._backfill_source_filenames(cursor)

		self.conn.commit()

	def _backfill_source_filenames(self, cursor):
		"""Recover the source of incidents saved before ``source_filename`` existed.

		Catalogued recordings carry their 32-hex recording ID in the name, and the
		archive name keeps it: incident_<channel>__<time>-<id>_<start>_<end>_<uuid>.mp4.
		"""
		if not cursor.execute(
			"SELECT 1 FROM sqlite_master WHERE type='table' AND name='recording_variants'"
		).fetchone():
			return
		rows = cursor.execute(
			"SELECT id, filename FROM incident_clips WHERE source_filename IS NULL"
		).fetchall()
		for incident_id, archive_name in rows:
			match = re.search(r"-([0-9a-f]{32})_\d+_\d+_[0-9a-f]{32}\.\w+$", archive_name)
			if not match:
				continue
			source = cursor.execute(
				"SELECT filename FROM recording_variants WHERE recording_id = ? "
				"ORDER BY format = 'mp4' DESC LIMIT 1",
				(match.group(1),)
			).fetchone()
			if source:
				cursor.execute(
					"UPDATE incident_clips SET source_filename = ? WHERE id = ?",
					(source[0], incident_id)
				)

	def add_incident(self, clip_id, filename, camera, start_time, end_time, title="", notes="",
			created_by=None, created_at=None, source_filename=None):
		cursor = self.conn.cursor()

		cursor.execute("""
			INSERT INTO incident_clips
			(id, filename, camera, start_time, end_time, incident_flag, title, notes,
			 created_by, created_at, source_filename)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""", (
			clip_id,
			filename,
			camera,
			start_time,
			end_time,
			1,
			title,
			notes,
			created_by,
			created_at,
			source_filename
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

	def list_incidents(self, cameras=None):
		"""Return incident records as dictionaries, newest first.

		``cameras`` limits the result to the given camera (channel) names, so
		callers can apply per-camera permissions (SR-06-02).
		"""
		query = (
			"SELECT id, filename, camera, start_time, end_time, incident_flag, "
			"title, notes, created_by, created_at FROM incident_clips"
		)
		params = []

		if cameras is not None:
			cameras = list(cameras)
			if not cameras:
				return []
			query += " WHERE camera IN (" + ", ".join("?" for _ in cameras) + ")"
			params.extend(cameras)

		query += " ORDER BY created_at DESC, id"
		keys = (
			"id", "filename", "camera", "start_time", "end_time", "incident_flag",
			"title", "notes", "created_by", "created_at"
		)
		return [
			dict(zip(keys, row))
			for row in self.conn.execute(query, params).fetchall()
		]

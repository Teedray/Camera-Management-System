"""Private Google Drive blob storage with durable, retry-safe file IDs."""
import re
import sqlite3
import tempfile
from pathlib import Path

from smart_sec_cam.video.cloud_storage import digest

SCOPE = 'https://www.googleapis.com/auth/drive.file'


def drive_service(token_file):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from googleapiclient.http import build_http
    credentials = Credentials.from_authorized_user_file(token_file, [SCOPE])
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError('Run drive_auth to authorize the dedicated Drive account')
        credentials.refresh(Request())
    # Drive uses HTTP 308 to acknowledge an intermediate upload chunk.
    transport = build_http()
    transport.timeout = 30
    return build('drive', 'v3', http=AuthorizedHttp(credentials, http=transport),
                 cache_discovery=False)


class DriveStore:
    def __init__(self, service, folder_id, index_path):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', folder_id):
            raise ValueError('Set DRIVE_FOLDER_ID to the application-created private folder')
        self.service, self.folder_id = service, folder_id
        self.identity = 'drive:' + folder_id
        index = Path(index_path)
        index.parent.mkdir(parents=True, exist_ok=True)
        self.index = sqlite3.connect(str(index), timeout=30)
        self.index.execute('''CREATE TABLE IF NOT EXISTS drive_objects (
            folder TEXT NOT NULL, object_key TEXT NOT NULL, file_id TEXT NOT NULL,
            PRIMARY KEY(folder,object_key))''')
        self.index.commit()

    @staticmethod
    def _status(exc):
        return getattr(getattr(exc, 'resp', None), 'status', None)

    def check_folder(self):
        folder = self.service.files().get(fileId=self.folder_id,
            fields='id,mimeType,trashed,permissions(type,role)').execute(num_retries=2)
        if folder.get('trashed') or folder.get('mimeType') != 'application/vnd.google-apps.folder':
            raise ValueError('Drive folder is unavailable')
        if not folder.get('permissions') or any(p.get('role') != 'owner'
                                               for p in folder['permissions']):
            raise ValueError('Use a private folder owned only by the dedicated account')

    def _id(self, key, reserve=False):
        if not re.fullmatch(r'(routine/[0-9a-f]{32}/clip\.mp4|health-check/[0-9a-f]{32}\.txt)', key):
            raise ValueError('Unsupported Drive object key')
        row = self.index.execute('SELECT file_id FROM drive_objects WHERE folder=? AND object_key=?',
                                 (self.folder_id, key)).fetchone()
        if row:
            return row[0]
        # Recover mappings if an index was restored without its latest entries.
        query = ("'{}' in parents and trashed=false and appProperties has "
                 "{{ key='cms_key' and value='{}' }}").format(self.folder_id, key)
        found = self.service.files().list(q=query, spaces='drive', pageSize=2,
            fields='files(id),nextPageToken').execute(num_retries=2)
        matches = found.get('files', [])
        if len(matches) > 1 or found.get('nextPageToken'):
            raise ValueError('Duplicate Drive object keys require manual recovery')
        if matches:
            file_id = matches[0]['id']
        elif reserve:
            file_id = self.service.files().generateIds(count=1, space='drive').execute(
                num_retries=2)['ids'][0]
        else:
            return None
        # Commit before network upload: a lost response must reuse the same ID.
        with self.index:
            self.index.execute('INSERT INTO drive_objects VALUES (?,?,?)',
                               (self.folder_id, key, file_id))
        return file_id

    def _metadata(self, file_id, key):
        try:
            item = self.service.files().get(fileId=file_id,
                fields='id,parents,trashed,appProperties').execute(num_retries=2)
        except Exception as exc:
            if self._status(exc) == 404:
                return None
            raise
        if (item.get('trashed') or self.folder_id not in item.get('parents', [])
                or item.get('appProperties', {}).get('cms_key') != key):
            raise ValueError('Drive object identity or parent does not match')
        return item

    def upload(self, key, source, size, fmt):
        from googleapiclient.http import MediaIoBaseUpload
        file_id = self._id(key, reserve=True)
        media = MediaIoBaseUpload(source, mimetype='video/mp4' if fmt == 'mp4' else 'text/plain',
                                 chunksize=2 * 1024 * 1024, resumable=True)
        if self._metadata(file_id, key):
            request = self.service.files().update(fileId=file_id, media_body=media, fields='id')
        else:
            name = key.split('/')[1] + ('.mp4' if fmt == 'mp4' else '')
            request = self.service.files().create(body={
                'id': file_id, 'name': name, 'parents': [self.folder_id],
                'appProperties': {'cms_key': key}}, media_body=media, fields='id')
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=2)

    def download(self, key, target):
        from googleapiclient.http import MediaIoBaseDownload
        file_id = self._id(key)
        if not file_id or not self._metadata(file_id, key):
            raise FileNotFoundError('Drive object is unavailable')
        transfer = MediaIoBaseDownload(target, self.service.files().get_media(fileId=file_id),
                                      chunksize=2 * 1024 * 1024)
        done = False
        while not done:
            _, done = transfer.next_chunk(num_retries=2)

    def sha256(self, key):
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as target:
            self.download(key, target)
            target.seek(0)
            return digest(target)

    def delete(self, key):
        file_id = self._id(key)
        if not file_id:
            return
        # Do not delete an unrelated file if an index is stale or was changed.
        if self._metadata(file_id, key):
            try:
                self.service.files().delete(fileId=file_id).execute(num_retries=2)
            except Exception as exc:
                if self._status(exc) != 404:
                    raise
        with self.index:
            self.index.execute('DELETE FROM drive_objects WHERE folder=? AND object_key=?',
                               (self.folder_id, key))

    def close(self):
        self.index.close()
        self.service.close()

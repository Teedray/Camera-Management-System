"""Interactive setup only; the worker and API never start a browser login."""
import argparse
import os
from pathlib import Path

from smart_sec_cam.video.drive_storage import SCOPE, drive_service


def main():
    parser = argparse.ArgumentParser(description='Authorize the dedicated Google Drive account')
    parser.add_argument('--client-secrets', required=True, help='Downloaded Desktop OAuth client JSON')
    parser.add_argument('--token-file', default='data/drive-token.json')
    parser.add_argument('--folder-name', default='Camera Management Recordings')
    args = parser.parse_args()
    from google_auth_oauthlib.flow import InstalledAppFlow
    destination = Path(args.token_file)
    if destination.exists():
        parser.error('Token already exists; use the existing folder or a new token path')
    credentials = InstalledAppFlow.from_client_secrets_file(args.client_secrets, [SCOPE]).run_local_server(
        host='localhost', port=0, access_type='offline', prompt='consent')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as token:
        token.write(credentials.to_json())
    service = drive_service(str(destination))
    try:
        folder = service.files().create(body={
            'name': args.folder_name, 'mimeType': 'application/vnd.google-apps.folder'},
            fields='id').execute(num_retries=2)
        print('DRIVE_FOLDER_ID=' + folder['id'])
        print('Token saved locally. Keep this file private and out of Git.')
    finally:
        service.close()


if __name__ == '__main__':
    main()

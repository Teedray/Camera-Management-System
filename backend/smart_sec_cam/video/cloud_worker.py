"""Run with python -m smart_sec_cam.video.cloud_worker --once."""
import argparse
import logging
import os
import time
from urllib.parse import urlparse

from smart_sec_cam.auth.database import AuthDatabase
from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.cloud_storage import CloudQueue, S3Store


def main():
    parser = argparse.ArgumentParser(description='Sync completed footage to private cloud storage')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--enable-cleanup', action='store_true',
                        help='Delete expired routine cloud objects; keeps local and incident files')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    endpoint = os.environ['CLOUD_ENDPOINT_URL']
    if urlparse(endpoint).scheme != 'https':
        parser.error('CLOUD_ENDPOINT_URL must use HTTPS')
    # Optional dependency: ordinary local recording still works without boto3.
    import boto3
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=endpoint,
                          region_name=os.getenv('AWS_DEFAULT_REGION', 'auto'),
                          config=Config(connect_timeout=5, read_timeout=30,
                                        retries={'max_attempts': 2}))
    db = AuthDatabase()
    root = os.getenv('VIDEO_DIR', 'data/videos')
    queue = CloudQueue(db.conn, root, S3Store(client, os.environ['CLOUD_BUCKET']),
                       cleanup=args.enable_cleanup)
    try:
        while True:
            import_completed(db, root)
            queue.tick()
            if args.once:
                break
            time.sleep(60)
    finally:
        db.conn.close()


if __name__ == '__main__':
    main()

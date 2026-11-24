"""Continuous recording service: records every camera channel in 30-second segments."""
import logging

from smart_sec_cam.recording.manager import RecordingManager
from smart_sec_cam.recording.segmenter import SEGMENT_SECONDS, STALL_SECONDS
from smart_sec_cam.redis import RedisImageReceiver


def main(redis_url: str, redis_port: int, video_dir: str, segment_seconds: int, stall_seconds: float):
    receiver = RedisImageReceiver(redis_url, redis_port)
    manager = RecordingManager(receiver, video_dir, segment_seconds=segment_seconds,
                               stall_seconds=stall_seconds)
    try:
        manager.run_forever()
    finally:
        manager.stop()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--redis-url', help='Redis server that carries camera frames', type=str, default='localhost')
    parser.add_argument('--redis-port', help='Redis server port', type=int, default=6379)
    parser.add_argument('--video-dir', help='Directory in which recordings are stored', type=str,
                        default="data/videos")
    parser.add_argument('--segment-seconds', help='Length of each recording segment', type=int,
                        default=SEGMENT_SECONDS)
    parser.add_argument('--stall-seconds', help='Seconds without frames before a camera counts as disconnected',
                        type=float, default=STALL_SECONDS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    main(args.redis_url, args.redis_port, args.video_dir, args.segment_seconds, args.stall_seconds)

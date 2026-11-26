"""Console checks against a temporary application database and real MP4 files."""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from smart_sec_cam.video.catalogue import import_completed
from smart_sec_cam.video.writer import VideoWriter
from test_admin_camera_api import AdminApiTestCase


class ManagementTest(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.admin=self.headers['administrator']
        self.manager=self.headers['manager']
        self.db.add_camera('front','Front','Entrance','Cam1')
        self.db.assign_camera('manager-id','front')
        self.root=Path(self.server.VIDEO_DIR)

    def test_console_metrics_and_audit(self):
        url='/api/v1/users/viewer-id/cameras/front'
        self.client.put(url,headers=self.admin)
        self.client.delete(url,headers=self.admin)
        rows=self.client.get('/api/v1/audit?type=permission_change&user=administrator',headers=self.admin).json['data']['items']
        self.assertEqual([r['action'] for r in rows],['revoke_camera','grant_camera'])
        self.assertIn('front',rows[0]['description'])
        for path in ('audit','cloud/status','storage'):
            self.assertEqual(self.client.get('/api/v1/'+path,headers=self.manager).status_code,403)
        self.db.mark_camera_seen('Cam1',datetime.now(timezone.utc).isoformat())
        self.assertEqual(self.client.get('/api/v1/system/status',headers=self.manager).json['data']['cameras'][0]['connection'],'connected')
        self.assertEqual(self.client.get('/api/v1/system/status',headers=self.admin).json['data']['cameras'],[])
        storage=self.client.get('/api/v1/storage',headers=self.admin).json['data']
        self.assertGreater(storage['total_bytes'],0)
        self.assertEqual((storage['local_hours'],storage['retention_days']),(1,30))
        self.assertEqual(self.client.patch('/api/v1/storage/retention',headers=self.admin,json={'retention_days':0}).status_code,400)
        self.assertEqual(self.client.patch('/api/v1/storage/retention',headers=self.admin,json={'retention_days':45}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/storage',headers=self.admin).json['data']['retention_days'],45)
        self.assertEqual(self.client.delete('/api/v1/cloud/connection',headers=self.admin).status_code,200)
        self.assertEqual(self.client.get('/api/v1/cloud/status',headers=self.admin).json['data']['connection_status'],'Paused')

    def test_merge_sorted_sources_and_authorized_download(self):
        names=[]
        start=datetime.now(timezone.utc)-timedelta(minutes=2)
        for offset,pixel in [(0,20),(5,220)]:
            writer=VideoWriter('Cam1',self.root,resolution=(64,48))
            for _ in range(20):
                writer.add_frame(np.full((48,64,3),pixel,dtype=np.uint8))
            with patch.object(writer,'_calculate_fps',return_value=10):
                writer.write()
            import_completed(self.db,self.root)
            rid,name=self.db.conn.execute("SELECT recording_id,filename FROM recording_variants WHERE format='mp4' ORDER BY rowid DESC LIMIT 1").fetchone()
            with self.db.conn:
                self.db.conn.execute('UPDATE recordings SET capture_start_utc=?,capture_end_utc=? WHERE id=?',
                    ((start+timedelta(seconds=offset)).isoformat(),(start+timedelta(seconds=offset+2)).isoformat(),rid))
            names.append(name)
        payload={'filenames':names[::-1],'title':'Two segments'}
        for role,status in [('viewer',403),('administrator',404)]:
            self.assertEqual(self.client.post('/api/v1/merges',headers=self.headers[role],json=payload).status_code,status)
        result=self.client.post('/api/v1/merges',headers=self.manager,json=payload)
        self.assertEqual(result.status_code,201,result.data)
        job=self.client.get('/api/v1/merges',headers=self.manager).json['data']['items'][0]
        with self.client.get(job['download_url'],headers=self.manager) as download, tempfile.NamedTemporaryFile(suffix='.mp4') as f:
            f.write(download.data); f.flush()
            movie=cv2.VideoCapture(f.name)
            try:
                self.assertAlmostEqual(movie.get(cv2.CAP_PROP_FRAME_COUNT)/movie.get(cv2.CAP_PROP_FPS),4,delta=.2)
                self.assertLess(movie.read()[1].mean(),50)
                movie.set(cv2.CAP_PROP_POS_MSEC,3000)
                self.assertGreater(movie.read()[1].mean(),180)
            finally:
                movie.release()
        self.db.revoke_camera('manager-id','front')
        self.assertEqual(self.client.get(job['download_url'],headers=self.manager).status_code,404)
        self.assertEqual(self.client.get('/api/v1/merges',headers=self.manager).json['data']['items'],[])

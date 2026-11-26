"""Management endpoints for the real console."""
import os
import shutil
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from flask import g, jsonify, request, send_file
from eventlet import tpool

from smart_sec_cam.video import operations
from smart_sec_cam.video.cloud_storage import queue_status, recording_protected
from smart_sec_cam.video.cloud_playback import acquire_local_job_hold, release_job_hold


def register(server):
    app = server.app
    admin = server.require_administrator
    auth = server.require_token

    def conn():
        return server.auth_db.conn

    def body():
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}

    def ok(**fields):
        return jsonify(success=True, data=fields)

    def error(message, status):
        return jsonify(success=False, error=message), status

    def now():
        return datetime.now(timezone.utc)

    actions = {
        'authenticate': 'login', 'create_user': 'permission_change',
        'change_user_role': 'permission_change', 'update_camera_assignment': 'permission_change',
        'register_camera': 'camera_change', 'update_camera': 'camera_change',
        'save_incident': 'incident_saved', 'delete_incident': 'delete',
        'download_export': 'export', 'create_merge': 'merge',
        'update_retention': 'retention', 'connect_cloud': 'cloud',
        'disconnect_cloud': 'cloud', 'retry_upload': 'cloud', 'extend_preservation': 'preservation',
    }

    @app.after_request
    def audit_response(response):
        endpoint = request.endpoint
        if endpoint not in actions:
            return response
        actor = getattr(g, 'current_user', None)
        if endpoint == 'authenticate' and response.status_code == 200:
            actor = server.auth_db.get_user_by_username(body().get('username'))
        # Route parameters identify the target. Never store tokens or request bodies.
        detail = ' '.join(f'{k}={v}' for k,v in (request.view_args or {}).items())[:500]
        action = ('grant_camera' if request.method == 'PUT' else 'revoke_camera'
                  ) if endpoint == 'update_camera_assignment' else endpoint
        with conn():
            conn().execute("INSERT INTO audit_events(created_at,user_id,username,type,action,description) "
                           "VALUES(?,?,?,?,?,?)", (now().isoformat(), getattr(actor,'user_id',None),
                           getattr(actor,'username',None), 'error' if response.status_code>=400
                           else actions[endpoint], action, f'HTTP {response.status_code} {detail}'.strip()))
        return response

    @app.get('/api/v1/audit')
    @admin
    def audit_events():
        clauses, values = [], []
        for key, condition in [('type','type=?'),('user','(username=? OR user_id=?)')]:
            v = request.args.get(key)
            if v:
                clauses.append(condition)
                values.extend([v]*condition.count('?'))
        if request.args.get('date'):
            try:
                start = datetime.strptime(request.args['date'],'%Y-%m-%d').replace(tzinfo=ZoneInfo('America/Jamaica'))
            except ValueError:
                return error('Choose a valid date',400)
            clauses.append('created_at>=? AND created_at<?')
            values.extend(d.astimezone(timezone.utc).isoformat() for d in (start,start+timedelta(days=1)))
        where = ' WHERE '+' AND '.join(clauses) if clauses else ''
        cursor = conn().execute('SELECT * FROM audit_events'+where+' ORDER BY id DESC LIMIT 500',values)
        return ok(items=[dict(zip([c[0] for c in cursor.description],row)) for row in cursor])

    @app.get('/api/v1/system/status')
    @auth
    def system_status():
        cameras, warnings = [], []
        for camera in server.auth_db.get_user_camera_details(g.current_user.user_id):
            latest, = conn().execute('SELECT MAX(capture_end_utc) FROM recordings WHERE camera_id=?',
                                      (camera['id'],)).fetchone()
            connection = server.camera_status(camera)
            recent = latest and (now()-datetime.fromisoformat(latest)).total_seconds()<90
            cameras.append(dict(id=camera['id'],name=camera['name'],connection=connection,
                                last_seen=camera['last_seen_utc'], last_recording=latest,
                                recording_state='Recent segment' if recent else 'No recent segment'))
            if connection!='connected':
                warnings.append(dict(code=camera['id'],level='warning',message=camera['name']+': no recent frames'))
        return ok(cameras=cameras,warnings=warnings)

    @app.get('/api/v1/storage')
    @admin
    def storage_status():
        path = Path(server.VIDEO_DIR).resolve()
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        protected = len(server.incident_repository().list_incidents())
        q = queue_status(conn())
        days, local_cleanup, cloud_cleanup = conn().execute(
            'SELECT cloud_days,local_cleanup,cloud_cleanup FROM operation_settings').fetchone()
        items = []
        if q['queue_ready']:
            for rid,name,expiry in conn().execute("""SELECT u.recording_id,v.filename,u.expires_at
                FROM cloud_uploads u JOIN recording_variants v USING(recording_id,format)
                ORDER BY u.expires_at LIMIT 100"""):
                active, = conn().execute('SELECT COUNT(*) FROM cloud_holds WHERE recording_id=?',(rid,)).fetchone()
                items.append(dict(id=name,filename=name,expires_at=expiry,protected=bool(recording_protected(conn(),rid)),active_jobs=active))
        return ok(total_bytes=usage.total,used_bytes=usage.used,free_bytes=usage.free,items=items,
                  protected_incidents=protected,retention_days=days,local_hours=q['local_retention_hours'],
                  local_removed=q['local_removed'],cloud_removed=q['states']['deleted'],
                  local_cleanup=local_cleanup,cloud_cleanup=cloud_cleanup)

    @app.patch('/api/v1/storage/retention')
    @admin
    def update_retention():
        days = body().get('retention_days')
        if type(days) is not int or not 1<=days<=3650:
            return error('Choose a whole number from 1 to 3650 days',400)
        with conn():
            conn().execute('UPDATE operation_settings SET cloud_days=? WHERE id=1',(days,))
            if queue_status(conn())['queue_ready']:
                for rid, end in conn().execute('SELECT id,capture_end_utc FROM recordings').fetchall():
                    expiry=(datetime.fromisoformat(end)+timedelta(days=days)).isoformat()
                    conn().execute("UPDATE cloud_uploads SET expires_at=?,next_attempt=MIN(next_attempt,?) "
                                   "WHERE recording_id=? AND state!='deleted'",(expiry,expiry,rid))
        return ok(retention_days=days)

    @app.get('/api/v1/cloud/status')
    @admin
    def cloud_status():
        q = queue_status(conn())
        paused, seen = conn().execute('SELECT paused,worker_seen FROM operation_settings').fetchone()
        state = 'Paused' if paused else 'Worker has not reported'
        if seen and not paused:
            state = 'Worker active' if now()-datetime.fromisoformat(seen)<timedelta(minutes=3) else 'Worker heartbeat overdue'
        jobs, buffer_bytes, last_verified = [], 0, None
        if q['queue_ready']:
            buffer_bytes, = conn().execute("""SELECT COALESCE(SUM(v.size_bytes),0) FROM cloud_uploads u
                JOIN recording_variants v USING(recording_id,format) WHERE u.state='pending'""").fetchone()
            for rid,fmt,name,phase,attempts,issue,relative in conn().execute("""SELECT u.recording_id,u.format,
                v.filename,u.state,u.attempts,u.last_error,v.path FROM cloud_uploads u
                JOIN recording_variants v USING(recording_id,format) ORDER BY u.expires_at DESC LIMIT 100"""):
                jobs.append(dict(id=rid+'-'+fmt,filename=name,status='failed' if issue else
                    ('verified' if phase=='uploaded' else phase),retries=attempts,error=issue,
                    local_available=server.media_file(server.VIDEO_DIR,relative) is not None,cloud_available=phase=='uploaded'))
            if 'verified_at' in {r[1] for r in conn().execute('PRAGMA table_info(cloud_uploads)')}:
                last_verified,=conn().execute('SELECT MAX(verified_at) FROM cloud_uploads').fetchone()
        configured = bool(os.getenv('DRIVE_FOLDER_ID') or os.getenv('CLOUD_BUCKET'))
        if not configured and not seen and not paused:
            state='Cloud destination not configured'
        return ok(connection_status=state,jobs=jobs,pending_uploads=q['states']['pending'],
                  failed_uploads=q['failed'],buffer_used_bytes=buffer_bytes,last_upload=last_verified,
                  last_verified=last_verified,worker_seen=seen,configured=configured)

    @app.post('/api/v1/cloud/connect')
    @admin
    def connect_cloud():
        provider = os.getenv('CLOUD_PROVIDER','drive')
        folder = body().get('folder')
        if folder and folder!=os.getenv('DRIVE_FOLDER_ID'):
            return error('Choose the destination provisioned on the server.',400)
        if body().get('provider')!=('google_drive' if provider=='drive' else 'other'):
            return error('Choose the provider configured on the server.',400)
        def verify():
            store = server.configured_store(os.environ)
            try:
                if provider=='s3':
                    store.client.head_bucket(Bucket=store.bucket)
                return store.identity
            finally:
                if hasattr(store,'close'):
                    store.close()
        try:
            identity=tpool.execute(verify)
        except Exception:
            return error('Configure the cloud worker and authorize the destination on the server first.',409)
        if queue_status(conn())['queue_ready']:
            binding=conn().execute('SELECT identity FROM cloud_backend').fetchone()
            if binding and binding[0]!=identity:
                return error('Existing uploads belong to another destination.',409)
        with conn():
            conn().execute('UPDATE operation_settings SET paused=0 WHERE id=1')
        return ok(verified=True)

    @app.delete('/api/v1/cloud/connection')
    @admin
    def disconnect_cloud():
        with conn():
            conn().execute('UPDATE operation_settings SET paused=1 WHERE id=1')
        return ok(paused=True)

    @app.post('/api/v1/cloud/jobs/<job_id>/retry')
    @admin
    def retry_upload(job_id):
        rid,_,fmt=job_id.rpartition('-')
        if queue_status(conn())['queue_ready']:
            with conn():
                changed=conn().execute('UPDATE cloud_uploads SET next_attempt=? WHERE recording_id=? AND format=? AND last_error IS NOT NULL',
                                       (now().isoformat(),rid,fmt)).rowcount
            if changed:
                return ok(scheduled=True)
        return error('Failed upload not found',404)

    def authorized_jobs(kind, job_id=None):
        user=g.current_user
        camera_ids={c['id'] for c in server.auth_db.get_user_cameras(user.user_id)}
        root=Path(server.VIDEO_DIR)/'.outputs'
        operations.expire_outputs(conn(),root,now().isoformat())
        return operations.visible_jobs(conn(),user.user_id,camera_ids,kind,job_id)

    @app.get('/api/v1/exports')
    @app.get('/api/v1/merges')
    @auth
    def list_media_jobs():
        if g.current_user.role not in server.INCIDENT_ROLES:
            return error('Manager or administrator role required',403)
        return ok(items=list(authorized_jobs(request.path.rsplit('/',1)[1])))

    @app.get('/api/v1/<any(exports,merges):kind>/<job_id>/download')
    @auth
    def download_job(kind,job_id):
        if g.current_user.role not in server.INCIDENT_ROLES:
            return error('Manager or administrator role required',403)
        job=next(authorized_jobs(kind,job_id),None)
        if not job or 'download_url' not in job:
            return error('Output unavailable',404)
        path=server.media_file(Path(server.VIDEO_DIR)/'.outputs',job_id+'.mp4')
        if not path:
            return error('Output unavailable',404)
        response=send_file(path,mimetype='video/mp4',as_attachment=True,download_name=job_id+'.mp4')
        response.headers['Cache-Control']='no-store'
        return response

    @app.post('/api/v1/merges')
    @auth
    def create_merge():
        if g.current_user.role not in server.INCIDENT_ROLES:
            return error('Manager or administrator role required',403)
        filenames=body().get('filenames')
        title=body().get('title','Merged recording')
        if (not isinstance(filenames,list) or not 2<=len(filenames)<=32
                or not all(isinstance(n,str) and Path(n).name==n and n.endswith('.mp4') for n in filenames)
                or len(set(filenames))!=len(filenames) or not isinstance(title,str) or not 0<len(title.strip())<=200):
            return error('Select 2–32 distinct MP4 recordings and a title of up to 200 characters',400)
        uid=g.current_user.user_id
        sources=[]
        for name in filenames:
            row=conn().execute("""SELECT r.capture_start_utc,r.capture_end_utc,r.camera_id
                FROM recording_variants v JOIN recordings r ON r.id=v.recording_id
                JOIN user_cameras u ON u.camera_id=r.camera_id JOIN cameras c ON c.id=r.camera_id
                WHERE v.filename=? AND v.format='mp4' AND u.user_id=? AND c.enabled=1""",(name,uid)).fetchone()
            if row is None:
                return error('Recording unavailable',404)
            sources.append((*row,name))
        sources.sort()
        job=operations.new_job(conn(),'merges',uid,title.strip(),[r[2] for r in sources],
                               sources[0][0],max(r[1] for r in sources))
        root=Path(server.VIDEO_DIR)/'.outputs'
        root.mkdir(parents=True,exist_ok=True)
        output=root/(job+'.mp4')
        try:
            with ExitStack() as stack:
                work=Path(stack.enter_context(TemporaryDirectory()))
                paths=[]
                for _,_,_,name in sources:
                    hold=acquire_local_job_hold(server.auth_db,uid,name)
                    stack.callback(release_job_hold,server.auth_db,hold)
                    path=server.resolve_recording(uid,name)
                    if path is None:
                        remote=server.fetch_cloud_recording(server.auth_db,uid,name,
                                                             lambda:server.configured_store(os.environ))
                        if not remote:
                            raise FileNotFoundError()
                        path=work/name
                        with remote[0] as src,path.open('wb') as dest:
                            shutil.copyfileobj(src,dest)
                    paths.append(path)
                tpool.execute(operations.merge_mp4,paths,output)
            operations.finish(conn(),job,'completed')
        except Exception as exc:
            output.unlink(missing_ok=True)
            operations.finish(conn(),job,'failed')
            app.logger.warning('Merge %s failed: %s',job,type(exc).__name__)
            return error('A source is unavailable or could not be merged',422)
        return ok(id=job,status='completed'),201

    @app.post('/api/v1/incidents/<incident_id>/preservation')
    @admin
    def extend_preservation(incident_id):
        days=body().get('extend_days')
        if type(days) is not int or not 1<=days<=3650:
            return error('Choose a preservation extension from 1 to 3650 days',400)
        if not server.visible_incident(g.current_user.user_id,incident_id):
            return error('Incident does not exist',404)
        with conn():
            conn().execute("""INSERT INTO incident_preservation(incident_id,until_utc)
                VALUES(?,strftime('%Y-%m-%dT%H:%M:%f+00:00','now',?))
                ON CONFLICT(incident_id) DO UPDATE SET until_utc=strftime('%Y-%m-%dT%H:%M:%f+00:00',
                MAX(datetime(until_utc),datetime('now')),?)""",(incident_id,f'+{days} days',f'+{days} days'))
        return ok(id=incident_id,preserved_until=conn().execute(
            'SELECT until_utc FROM incident_preservation WHERE incident_id=?',(incident_id,)).fetchone()[0])

"""Thread-safe queue, bounded UI mailbox and debounced durable state."""
from collections import deque
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import threading
import uuid

from downloader import Cancelled, DownloadEngine, normalize_url


ACTIVE = {'preparing', 'downloading', 'muxing', 'verifying'}
LABELS = {'pending': 'Menunggu', 'preparing': 'Menyiapkan', 'downloading': 'Mengunduh',
          'muxing': 'Menggabungkan', 'verifying': 'Memeriksa', 'done': 'Selesai',
          'failed': 'Gagal', 'cancelled': 'Dibatalkan'}


@dataclass
class Job:
    id: str
    url: str
    title: str
    cap: int
    folder: str
    selected: bool = True
    status: str = 'pending'
    height: int = 0
    ext: str = ''
    error: str = ''
    result: str = ''
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    stage: str = ''

    def durable(self):
        data = asdict(self)
        for key in ('percent', 'speed', 'eta', 'stage'):
            data.pop(key)
        return data


class Mailbox:
    """Coalesce refresh requests; progress never builds an unbounded event queue."""
    def __init__(self):
        self.lock = threading.Lock()
        self.dirty = True
        self.logs = deque(maxlen=500)
        self.notices = deque(maxlen=20)

    def post(self, kind, value=None):
        with self.lock:
            if kind == 'log':
                self.logs.extend(str(value).splitlines() or [''])
            elif kind != 'changed':
                self.notices.append((kind, value))
            self.dirty = True

    def drain(self):
        with self.lock:
            result = self.dirty, list(self.logs), list(self.notices)
            self.dirty = False
            self.logs.clear()
            self.notices.clear()
            return result


class QueueController:
    def __init__(self, state_path, engine=None, mailbox=None):
        self.path = Path(state_path)
        self.engine = engine if engine is not None else DownloadEngine()
        self.mailbox = mailbox if mailbox is not None else Mailbox()
        self.condition = threading.Condition(threading.RLock())
        self.jobs = []
        self.by_id = {}
        self.by_url = {}
        self.settings = {'folder': str(Path.home() / 'Downloads' / 'YouTube'), 'cap': 1080}
        self.running = False
        self.closed = False
        self.active_id = None
        self.imports = 0
        self.cancel = threading.Event()
        self.dirty = threading.Event()
        self.stop_saver = threading.Event()
        self._load()
        self.worker = threading.Thread(target=self._run, daemon=True, name='download-queue')
        self.saver = threading.Thread(target=self._save_loop, daemon=True, name='queue-save')
        self.worker.start()
        self.saver.start()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            settings = data.get('settings', {})
            self.settings = {'folder': str(settings.get('folder', self.settings['folder'])),
                             'cap': int(settings.get('cap', 1080))}
            for item in data.get('jobs', []):
                try:
                    item = dict(item)
                    item['url'] = normalize_url(item['url'])
                    if len(item['id']) != 32 or any(c not in '0123456789abcdef' for c in item['id']):
                        raise ValueError('ID pekerjaan tidak valid')
                    if item.get('status') in ACTIVE:
                        item['status'] = 'pending'
                    if item.get('status') not in LABELS:
                        item['status'] = 'pending'
                    job = Job(**item)
                    if job.url in self.by_url or job.id in self.by_id:
                        continue
                    self.jobs.append(job)
                    self.by_id[job.id] = job
                    self.by_url[job.url] = job.id
                except (KeyError, ValueError, TypeError) as exc:
                    self.mailbox.post('log', f'Entri antrean tidak dapat dipulihkan: {exc}')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.mailbox.post('log', f'Antrean tersimpan tidak dapat dibaca: {exc}. File asli tidak dihapus.')

    def snapshot(self):
        with self.condition:
            return {'version': 1, 'settings': dict(self.settings), 'jobs': [j.durable() for j in self.jobs]}

    def _save_loop(self):
        while True:
            self.dirty.wait()
            self.dirty.clear()
            self.stop_saver.wait(0.4)  # Coalesce bursts, never block Tk's event loop.
            self.dirty.clear()
            try:
                data = self.snapshot()
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                temporary.replace(self.path)
            except OSError as exc:
                self.mailbox.post('log', f'Antrean gagal disimpan: {exc}')
            if self.stop_saver.is_set():
                return

    def changed(self, durable=True):
        self.mailbox.post('changed')
        if durable:
            self.dirty.set()

    def configure(self, cap, folder):
        with self.condition:
            self.settings.update(cap=int(cap), folder=str(folder))
            for job in self.jobs:
                if job.status == 'pending' and job.selected:
                    job.cap, job.folder = int(cap), str(folder)
            self.changed()

    def add(self, url, title=None, cap=None, folder=None, unavailable=False):
        url = normalize_url(url)
        with self.condition:
            if url in self.by_url:
                return None
            job = Job(uuid.uuid4().hex, url, title or url.split('v=')[-1],
                      int(cap or self.settings['cap']), str(folder or self.settings['folder']))
            if unavailable:
                job.status, job.error = 'failed', 'Video privat, dihapus, atau membutuhkan akses khusus.'
            self.jobs.append(job)
            self.by_id[job.id] = job
            self.by_url[url] = job.id
            self.changed()
            self.condition.notify_all()
            return job.id

    def view(self, page=0, size=100):
        with self.condition:
            count = len(self.jobs)
            page = max(0, min(page, max(0, (count - 1) // size)))
            visible = [replace(j) for j in self.jobs[page * size:(page + 1) * size]]
            counts = {status: 0 for status in LABELS}
            for job in self.jobs:
                counts[job.status] += 1
            active = replace(self.by_id[self.active_id]) if self.active_id else None
            return visible, count, page, counts, active, self.running

    def get(self, job_id):
        with self.condition:
            return replace(self.by_id[job_id]) if job_id in self.by_id else None

    def select(self, ids, selected):
        with self.condition:
            for job_id in ids:
                job = self.by_id.get(job_id)
                if job and job.status not in ACTIVE:
                    job.selected = selected
            self.changed()
            self.condition.notify_all()

    def select_all(self, selected):
        with self.condition:
            self.select(list(self.by_id), selected)

    def remove_selected(self):
        with self.condition:
            removed = [j for j in self.jobs if j.selected and j.status not in ACTIVE]
            removed_ids = {j.id for j in removed}
            self.jobs = [j for j in self.jobs if j.id not in removed_ids]
            for job in removed:
                self.by_id.pop(job.id)
                self.by_url.pop(job.url)
            self.changed()

    def retry_failed(self):
        with self.condition:
            for job in self.jobs:
                if job.selected and job.status in ('failed', 'cancelled'):
                    job.status, job.error, job.percent = 'pending', '', None
            self.changed()
            self.condition.notify_all()

    def start(self):
        with self.condition:
            self.running = bool(self.active_id or self.imports or any(j.selected and j.status == 'pending' for j in self.jobs))
            self.condition.notify_all()
            self.changed(False)

    def begin_import(self):
        with self.condition:
            self.imports += 1

    def end_import(self):
        with self.condition:
            self.imports = max(0, self.imports - 1)
            if not self.imports and not self.active_id and not any(j.selected and j.status == 'pending' for j in self.jobs):
                self.running = False
            self.changed(False)

    def pause(self):
        with self.condition:
            self.running = False
            self.changed(False)

    def cancel_active(self):
        with self.condition:
            if self.active_id:
                self.cancel.set()

    def _event(self, job, kind, value):
        with self.condition:
            if kind == 'log':
                self.mailbox.post('log', f'[{job.title}] {value}')
                return
            if kind == 'selection':
                job.title, job.height, job.ext = value['title'], value['height'], value['ext']
                self.changed()
                return
            if kind == 'progress':
                job.status = 'downloading'
                job.percent, job.speed, job.eta = value['percent'], value['speed'], value['eta']
                job.stage = value['stage']
            elif kind == 'status':
                job.stage = str(value)
                if value.startswith('Menggabungkan'):
                    job.status = 'muxing'
                elif value.startswith('Memeriksa file'):
                    job.status = 'verifying'
            self.changed(False)

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or (self.running and any(
                    j.selected and j.status == 'pending' for j in self.jobs)))
                if self.closed:
                    return
                job = next(j for j in self.jobs if j.selected and j.status == 'pending')
                self.active_id, job.status = job.id, 'preparing'
                job.error, job.percent = '', None
                self.cancel = threading.Event()
                self.changed()
            try:
                result = self.engine.download(job.url, job.cap, job.folder,
                    lambda kind, value: self._event(job, kind, value), self.cancel, job.id)
                with self.condition:
                    job.result, job.status, job.percent = str(result), 'done', 100
            except Cancelled as exc:
                with self.condition:
                    job.status, job.error = ('pending' if self.closed else 'cancelled'), str(exc)
            except Exception as exc:
                with self.condition:
                    job.status, job.error = 'failed', str(exc)
                    self.mailbox.post('log', f'[{job.title}] {exc}')
            finally:
                with self.condition:
                    job.speed, job.eta = None, None
                    self.active_id = None
                    if not self.imports and not any(j.selected and j.status == 'pending' for j in self.jobs):
                        self.running = False
                    self.changed()

    def shutdown(self):
        with self.condition:
            self.closed, self.running = True, False
            self.cancel.set()
            self.condition.notify_all()
        self.worker.join()
        self.stop_saver.set()
        self.dirty.set()
        self.saver.join()

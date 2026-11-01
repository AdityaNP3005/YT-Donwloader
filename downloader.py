"""Cached metadata, resumable streams and a single lossless mux. No UI code."""
from __future__ import annotations

from collections import OrderedDict
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid


class AppError(Exception):
    pass


class Cancelled(AppError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('Dibatalkan. File parsial disimpan untuk dicoba lagi.')


def parse_link(value, whole_playlist=False):
    try:
        url = urlsplit(value.strip())
        host = (url.hostname or '').lower()
        if url.scheme not in ('http', 'https') or url.username or url.password:
            raise ValueError
        if host not in ('youtu.be', 'www.youtu.be', 'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
            raise ValueError
        query = parse_qs(url.query)
        playlist = query.get('list', [''])[0]
        if playlist and (whole_playlist or url.path.rstrip('/') == '/playlist'):
            if not re.fullmatch(r'[A-Za-z0-9_-]{2,200}', playlist):
                raise ValueError
            return 'playlist', 'https://www.youtube.com/playlist?' + urlencode({'list': playlist})
        if host.endswith('youtu.be'):
            video_id = url.path.strip('/').split('/')[0]
        else:
            parts = url.path.strip('/').split('/')
            video_id = (query.get('v', [''])[0] if url.path == '/watch' else
                        parts[1] if len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live') else '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError
        return 'video', 'https://www.youtube.com/watch?' + urlencode({'v': video_id})
    except ValueError as exc:
        raise AppError('Link YouTube tidak valid. Gunakan link video atau playlist.') from exc


def normalize_url(value):
    kind, url = parse_link(value)
    if kind != 'video':
        raise AppError('Gunakan link satu video untuk Cek Video.')
    return url


def find_tool(name):
    local = Path(__file__).resolve().parent / '.tools' / 'bin' / f'{name}.exe'
    return str(local) if local.is_file() else shutil.which(name)


def tools_required():
    tools = {name: find_tool(name) for name in ('ffmpeg', 'ffprobe', 'deno')}
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise AppError('Program pendukung belum ditemukan: ' + ', '.join(missing) + '. Lihat README.md; gunakan .tools/bin atau PATH.')
    return tools


def ydl_class():
    try:
        from yt_dlp import YoutubeDL
        return YoutubeDL
    except ImportError as exc:
        raise AppError('Dependensi belum terpasang. Lihat README.md.') from exc


class Logger:
    def __init__(self, emit):
        self.emit = emit

    def debug(self, message):
        pass

    def warning(self, message):
        self.emit('log', str(message))

    def error(self, message):
        self.emit('log', str(message))


def options(emit):
    ffmpeg = find_tool('ffmpeg')
    return {'noplaylist': True, 'quiet': True, 'no_color': True, 'logger': Logger(emit),
            'socket_timeout': 20, 'retries': 1, 'fragment_retries': 1,
            'js_runtimes': {'deno': {'path': find_tool('deno')}}, 'windowsfilenames': True,
            'ffmpeg_location': str(Path(ffmpeg).parent) if ffmpeg else None,
            'concurrent_fragment_downloads': 2, 'progress_delta': 0.2,
            'fixup': 'never', 'continuedl': True, 'overwrites': False}


class MetadataCache:
    def __init__(self, limit=10, ttl=300, clock=time.monotonic):
        self.limit, self.ttl, self.clock = limit, ttl, clock
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def get(self, url):
        with self.lock:
            entry = self.items.get(url)
            if not entry:
                return None
            stamp, info = entry
            if self.clock() - stamp >= self.ttl:
                del self.items[url]
                return None
            self.items.move_to_end(url)
            return copy.deepcopy(info)

    def put(self, url, info):
        with self.lock:
            self.items[url] = (self.clock(), copy.deepcopy(info))
            self.items.move_to_end(url)
            while len(self.items) > self.limit:
                self.items.popitem(last=False)


def usable_formats(info):
    return [f for f in info.get('formats', []) if f.get('url') and not f.get('has_drm')
            and f.get('vcodec') not in (None, 'none') and f.get('height')]


def choose_formats(formats, cap):
    audios = [f for f in formats if f.get('url') and not f.get('has_drm')
              and f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')]
    videos = [f for f in usable_formats({'formats': formats}) if f['height'] <= cap
              and (audios or f.get('acodec') not in (None, 'none'))]
    if not videos:
        raise AppError(f'Tidak ada video dengan suara pada resolusi hingga {cap}p.')
    height = max(f['height'] for f in videos)
    videos = [f for f in videos if f['height'] == height]
    video = max(enumerate(videos), key=lambda p: (
        str(p[1].get('vcodec', '')).startswith(('avc1', 'h264')),
        p[1].get('acodec') == 'none', p[0]))[1]
    if video.get('acodec') not in (None, 'none'):
        return video, None
    audio = max(enumerate(audios), key=lambda p: (
        str(p[1].get('acodec', '')).startswith(('mp4a', 'aac')), p[0]))[1]
    return video, audio


def container_for(video, audio):
    acodec = (audio or video).get('acodec', '')
    compatible = (str(video.get('vcodec', '')).startswith(('avc1', 'h264'))
                  and str(acodec).startswith(('mp4a', 'aac')))
    return 'mp4' if compatible else 'mkv'


def resolutions(info):
    values = sorted({int(f['height']) for f in usable_formats(info)}, reverse=True)
    if not values:
        raise AppError('Tidak ada resolusi video yang dapat diunduh.')
    choose_formats(info.get('formats', []), values[0])
    return values


def reject_live(info):
    if info.get('is_live') or info.get('live_status') == 'is_upcoming':
        raise AppError('Live atau video yang belum tayang belum didukung.')


def probe(path, ffprobe):
    result = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise AppError('Pemeriksaan file gagal: ' + result.stderr[-1500:])
    return json.loads(result.stdout)


def av_streams(metadata):
    streams = metadata.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    if not video or not audio:
        raise AppError('File hasil belum memiliki video dan audio lengkap.')
    return video, audio


def mux_args(video, audio, output, ffmpeg):
    args = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(video)]
    if audio is not None:
        args += ['-i', str(audio)]
    args += ['-map', '0:v:0', '-map', '1:a:0' if audio is not None else '0:a:0', '-c', 'copy', '-threads', '1']
    return args + [str(output)]


def run_mux(args, cancel, log_path):
    with Path(log_path).open('w', encoding='utf-8') as log:
        with subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=log,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
            try:
                while process.poll() is None:
                    if cancel.wait(0.1):
                        raise Cancelled('Penggabungan dibatalkan. Bahan download disimpan.')
                check_cancel(cancel)
                if process.returncode:
                    raise AppError('FFmpeg gagal menggabungkan stream. Periksa ffmpeg.log.')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def finalize(source, destination):
    """Publish on the same volume without copying bytes or overwriting files."""
    destination = Path(destination)
    stem, suffix, number = destination.stem, destination.suffix, 1
    while True:
        try:
            os.link(source, destination)
        except FileExistsError:
            destination = destination.with_name(f'{stem} ({number}){suffix}')
            number += 1
        except OSError:
            # FAT/exFAT may not support hard links; Windows rename never replaces.
            if os.name != 'nt':
                raise
            try:
                os.rename(source, destination)
                return destination
            except FileExistsError:
                destination = destination.with_name(f'{stem} ({number}){suffix}')
                number += 1
        else:
            # Publication succeeded; a cleanup failure must not publish a duplicate.
            try:
                Path(source).unlink()
            except OSError:
                pass
            return destination


def is_refresh_error(exc):
    return bool(re.search(r'\b(403|410)\b|url.*expired|signature.*expired', str(exc), re.I))


class DownloadEngine:
    def __init__(self, cache=None):
        self.cache = cache if cache is not None else MetadataCache()
        self.metadata_lock = threading.Lock()

    def metadata(self, url, emit, cancel=None, refresh=False):
        url = normalize_url(url)
        cancel = cancel if cancel is not None else threading.Event()
        while not self.metadata_lock.acquire(timeout=0.1):
            check_cancel(cancel)
        try:
            check_cancel(cancel)
            info = None if refresh else self.cache.get(url)
            if info is not None:
                return info
            emit('status', 'Mengambil informasi video...')
            with ydl_class()(options(emit)) as ydl:
                info = ydl.extract_info(url, download=False)
            check_cancel(cancel)
            reject_live(info)
            resolutions(info)
            self.cache.put(url, info)
            return copy.deepcopy(info)
        finally:
            self.metadata_lock.release()

    def inspect(self, url, emit, cancel=None):
        tools_required()
        info = self.metadata(url, emit, cancel)
        return {'url': normalize_url(url), 'title': info.get('title', 'Video'), 'resolutions': resolutions(info)}

    def playlist(self, url, emit, cancel):
        opts = options(emit)
        opts.update(noplaylist=False, extract_flat='in_playlist', lazy_playlist=True, ignoreerrors=True, skip_download=True)
        with ydl_class()(opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
            if not info or 'entries' not in info:
                raise AppError('Playlist tidak dapat dibaca atau membutuhkan login.')
            for entry in info['entries']:
                check_cancel(cancel)
                if not entry:
                    continue
                video_id = entry.get('id', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                    continue
                yield {'url': f'https://www.youtube.com/watch?v={video_id}',
                       'title': entry.get('title') or video_id,
                       'unavailable': entry.get('availability') in ('private', 'premium_only', 'subscriber_only')
                           or entry.get('title') in ('[Deleted video]', '[Private video]')}

    def download(self, url, cap, folder, emit, cancel=None, job_id=None):
        cancel = cancel if cancel is not None else threading.Event()
        tools = tools_required()
        url = normalize_url(url)
        job_id = job_id or uuid.uuid4().hex
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise AppError('ID pekerjaan tidak valid.')
        target = Path(folder).expanduser().resolve()
        work = target / '.youtube-work' / job_id
        try:
            work.mkdir(parents=True, exist_ok=True)
            test = work / 'write-check'
            test.write_bytes(b'')
            test.unlink()
        except OSError as exc:
            raise AppError(f'Folder tidak dapat ditulis. Periksa izin dan ruang kosong.\n{exc}') from exc
        try:
            info = self.metadata(url, emit, cancel)
            for attempt in range(2):
                check_cancel(cancel)
                video, audio = choose_formats(info['formats'], cap)
                height, ext = int(video['height']), container_for(video, audio)
                emit('selection', {'title': info.get('title') or info['id'], 'height': height, 'ext': ext})
                paths = self._prepare_work(work, url, video, audio)
                try:
                    self._streams(info, video, audio, paths, emit, cancel, 2 if attempt == 0 else 1)
                    break
                except Exception as exc:
                    check_cancel(cancel)
                    if attempt:
                        raise
                    if is_refresh_error(exc):
                        emit('log', 'URL stream ditolak/kedaluwarsa; memperbarui metadata sekali.')
                        info = self.metadata(url, emit, cancel, refresh=True)
                    else:
                        emit('log', 'Mencoba kembali dengan satu fragmen paralel; file parsial digunakan kembali.')
            check_cancel(cancel)
            output = work / f'final.{ext}'
            emit('status', 'Menggabungkan gambar dan suara tanpa encoding ulang...')
            run_mux(mux_args(paths[0], paths[1], output, tools['ffmpeg']), cancel, work / 'ffmpeg.log')
            check_cancel(cancel)
            emit('status', 'Memeriksa file akhir...')
            actual_video, actual_audio = av_streams(probe(output, tools['ffprobe']))
            if actual_video.get('height') != height or output.stat().st_size == 0:
                raise AppError('Resolusi file hasil tidak sesuai pilihan.')
            if ext == 'mp4' and (actual_video.get('codec_name') != 'h264' or actual_audio.get('codec_name') != 'aac'):
                raise AppError('Codec file MP4 tidak sesuai.')
            check_cancel(cancel)
            title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', info.get('title') or 'Video')[:110].rstrip('. ')
            result = finalize(output, target / f"{title or 'Video'} [{info['id']}] {height}p.{ext}")
            shutil.rmtree(work, ignore_errors=True)
            return result
        except Cancelled:
            raise
        except Exception as exc:
            raise AppError(f'{exc}\nFile sementara dipertahankan di:\n{work}') from exc

    @staticmethod
    def _prepare_work(work, url, video, audio):
        manifest = {'url': url, 'formats': [(f['format_id'], f.get('ext'), f.get('vcodec'), f.get('acodec'))
                                          for f in (video, audio) if f is not None]}
        manifest = json.loads(json.dumps(manifest))
        path = work / 'resume.json'
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            previous = None
        if previous is not None and previous != manifest:
            archive = work / ('previous-' + uuid.uuid4().hex[:8])
            archive.mkdir()
            for item in list(work.iterdir()):
                if item.is_file():
                    item.rename(archive / item.name)
        path.write_text(json.dumps(manifest), encoding='utf-8')
        return [work / ('video.' + video['ext']), work / ('audio.' + audio['ext']) if audio else None]

    @staticmethod
    def _streams(info, video, audio, paths, emit, cancel, concurrency):
        total_streams, last = (2 if audio is not None else 1), [0.0]
        for index, stream in enumerate((video, audio)):
            if stream is None:
                continue
            check_cancel(cancel)

            def progress(data):
                check_cancel(cancel)
                now = time.monotonic()
                if data['status'] != 'finished' and now - last[0] < 0.2:
                    return
                last[0] = now
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                fraction = min(1, data.get('downloaded_bytes', 0) / total) if total else None
                if data['status'] == 'finished':
                    fraction = 1
                emit('progress', {'percent': (index + fraction) / total_streams * 100 if fraction is not None else None,
                                  'speed': data.get('speed'), 'eta': data.get('eta'),
                                  'stage': f'Mengunduh stream {index + 1}/{total_streams}'})

            opts = options(emit)
            opts.update(format=str(stream['format_id']), outtmpl=str(paths[index]),
                        concurrent_fragment_downloads=concurrency, progress_hooks=[progress])
            with ydl_class()(opts) as ydl:
                # extract_info(download=False) may already contain a default merged
                # selection. Leaving requested_formats here would trigger an extra
                # merger even when our new selector asks for just one stream.
                stale = {'requested_formats', 'requested_downloads', 'filepath', '_filename'}
                clean = {key: value for key, value in info.items()
                         if key not in stale and not key.startswith('__')}
                ydl.process_ie_result(copy.deepcopy(clean), download=True)


DEFAULT_ENGINE = DownloadEngine()


def inspect_video(url, emit):
    return DEFAULT_ENGINE.inspect(url, emit)


def download_video(url, height, folder, emit):
    return DEFAULT_ENGINE.download(url, height, folder, emit)

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import downloader as d

URL = 'https://www.youtube.com/watch?v=abcdefghijk'


def video(height=1080, codec='avc1.640028', acodec='none', ident='v'):
    return dict(format_id=ident, height=height, vcodec=codec, acodec=acodec,
                url='https://media.test/video?signature=secret', protocol='https', ext='mp4')


def audio(codec='mp4a.40.2', ident='a'):
    return dict(format_id=ident, vcodec='none', acodec=codec,
                url='https://media.test/audio?signature=secret', protocol='https', ext='m4a')


def info(height=1080):
    return dict(id='abcdefghijk', title='Judul: contoh / video?', formats=[video(height), audio()])


def probe_info(height=1080, vcodec='h264', acodec='aac'):
    return {'streams': [{'codec_type': 'video', 'codec_name': vcodec, 'height': height},
                        {'codec_type': 'audio', 'codec_name': acodec}]}


class EngineTests(unittest.TestCase):
    def test_url_types_and_default_watch_playlist(self):
        self.assertEqual(d.normalize_url('https://youtu.be/abcdefghijk?list=PL123'), URL)
        self.assertEqual(d.normalize_url('https://m.youtube.com/shorts/abcdefghijk'), URL)
        self.assertEqual(d.parse_link(URL + '&list=PL123')[0], 'video')
        self.assertEqual(d.parse_link(URL + '&list=PL123', True),
                         ('playlist', 'https://www.youtube.com/playlist?list=PL123'))
        self.assertEqual(d.parse_link('https://www.youtube.com/playlist?list=PL123')[0], 'playlist')

    def test_invalid_urls(self):
        for url in ('', 'file:///abcdefghijk', 'https://youtube.com.evil.test/watch?v=abcdefghijk',
                    'https://user@youtube.com/watch?v=abcdefghijk', 'https://youtu.be/short'):
            with self.subTest(url=url), self.assertRaises(d.AppError):
                d.parse_link(url)

    def test_resolution_cap_then_codec_priority(self):
        formats = [video(720), video(1080, 'vp9', ident='vp9'), video(2160), audio()]
        selected, _ = d.choose_formats(formats, 1080)
        self.assertEqual(selected['format_id'], 'vp9')
        self.assertEqual(d.container_for(selected, audio()), 'mkv')
        formats.append(video(1080, ident='h264'))
        self.assertEqual(d.choose_formats(formats, 1080)[0]['format_id'], 'h264')
        self.assertEqual(d.container_for(video(), audio()), 'mp4')

    def test_lower_quality_fallback_never_upscales(self):
        self.assertEqual(d.choose_formats([video(720), audio()], 1080)[0]['height'], 720)
        with self.assertRaises(d.AppError):
            d.choose_formats([video(2160), audio()], 1080)

    def test_combined_video_has_one_audio(self):
        self.assertIsNone(d.choose_formats([video(acodec='mp4a.40.2'), audio()], 1080)[1])

    def test_no_audio_and_drm_rejected(self):
        for formats in ([video()], [dict(video(), has_drm=True), audio()]):
            with self.assertRaises(d.AppError):
                d.resolutions({'formats': formats})

    def test_cache_ttl_lru_and_mutation_isolation(self):
        now = [0]
        cache = d.MetadataCache(limit=2, ttl=300, clock=lambda: now[0])
        cache.put('a', info())
        cached = cache.get('a')
        cached['formats'].clear()
        self.assertEqual(len(cache.get('a')['formats']), 2)
        cache.put('b', info())
        cache.get('a')
        cache.put('c', info())
        self.assertIsNone(cache.get('b'))
        now[0] = 300
        self.assertIsNone(cache.get('a'))

    def test_repeated_metadata_extracts_only_once_and_refresh_bypasses_cache(self):
        engine = d.DownloadEngine()
        instance = MagicMock()
        instance.__enter__.return_value = instance
        instance.extract_info.return_value = info()
        with patch('downloader.ydl_class', return_value=MagicMock(return_value=instance)):
            engine.metadata(URL, lambda *_: None)
            engine.metadata(URL, lambda *_: None)
            self.assertEqual(instance.extract_info.call_count, 1)
            engine.metadata(URL, lambda *_: None, refresh=True)
            self.assertEqual(instance.extract_info.call_count, 2)

    def test_lossless_mux_arguments_and_space_paths(self):
        args = d.mux_args('video spasi.mp4', 'suara spasi.m4a', 'hasil.mkv', 'ffmpeg')
        self.assertEqual(args[args.index('-c') + 1], 'copy')
        self.assertIn('video spasi.mp4', args)
        self.assertNotIn('libx264', args)
        self.assertEqual(d.mux_args('v.mp4', None, 'hasil.mp4', 'ffmpeg').count('-i'), 1)

    def test_atomic_publication_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            target = folder / 'hasil.mp4'
            target.write_bytes(b'original')
            source = folder / 'source.mp4'
            source.write_bytes(b'new')
            result = d.finalize(source, target)
            self.assertEqual(result.name, 'hasil (1).mp4')
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(result.read_bytes(), b'new')
            self.assertFalse(source.exists())

    def test_resume_manifest_excludes_signed_urls_and_preserves_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            paths = d.DownloadEngine._prepare_work(work, URL, video(), audio())
            partial = Path(str(paths[0]) + '.part')
            partial.write_bytes(b'partial')
            d.DownloadEngine._prepare_work(work, URL, video(), audio())
            self.assertTrue(partial.exists())
            self.assertNotIn('signature', (work / 'resume.json').read_text())
            d.DownloadEngine._prepare_work(work, URL, video(720, ident='different'), audio())
            self.assertFalse(partial.exists())
            self.assertEqual(len(list(work.glob('previous-*/*.part'))), 1)

    def test_cancelled_mux_terminates_child(self):
        process = MagicMock()
        process.__enter__.return_value = process
        process.poll.return_value = None
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as folder, patch('downloader.subprocess.Popen', return_value=process):
            with self.assertRaises(d.Cancelled):
                d.run_mux(['ffmpeg'], cancel, Path(folder) / 'ffmpeg.log')
            process.terminate.assert_called_once()

    def test_cancel_checked_even_for_throttled_progress(self):
        cancel = threading.Event()
        def factory(opts):
            instance = MagicMock()
            instance.__enter__.return_value = instance
            def process(*_, **__):
                cancel.set()
                opts['progress_hooks'][0]({'status': 'downloading'})
            instance.process_ie_result.side_effect = process
            return instance
        with patch('downloader.ydl_class', return_value=factory), self.assertRaises(d.Cancelled):
            d.DownloadEngine._streams(info(), video(), audio(), ['v.mp4', 'a.m4a'], lambda *_: None, cancel, 2)

    def test_progress_is_throttled(self):
        events = []
        def factory(opts):
            instance = MagicMock()
            instance.__enter__.return_value = instance
            def process(*_, **__):
                for _ in range(1000):
                    opts['progress_hooks'][0]({'status': 'downloading', 'total_bytes': 1000, 'downloaded_bytes': 1})
            instance.process_ie_result.side_effect = process
            return instance
        with patch('downloader.ydl_class', return_value=factory), patch('downloader.time.monotonic', return_value=1):
            d.DownloadEngine._streams(info(), video(), audio(), ['v.mp4', 'a.m4a'], lambda *x: events.append(x), threading.Event(), 2)
        self.assertEqual(len(events), 1)

    def test_playlist_is_lazy_and_unavailable_entries_are_marked(self):
        visited = []
        def entries():
            for i in range(1000):
                visited.append(i)
                yield {'id': f'{i:011d}', 'title': '[Private video]' if i == 0 else str(i)}
        instance = MagicMock()
        instance.__enter__.return_value = instance
        instance.extract_info.return_value = {'entries': entries()}
        with patch('downloader.ydl_class', return_value=MagicMock(return_value=instance)):
            result = d.DownloadEngine().playlist('https://www.youtube.com/playlist?list=PL123', lambda *_: None, threading.Event())
            self.assertTrue(next(result)['unavailable'])
            self.assertEqual(visited, [0])
            result.close()

    def test_local_tools_and_actionable_missing_error(self):
        with patch('downloader.Path.is_file', return_value=True), patch('downloader.shutil.which') as which:
            self.assertEqual(Path(d.find_tool('deno')).name, 'deno.exe')
            which.assert_not_called()
        with patch('downloader.find_tool', return_value=None), self.assertRaisesRegex(d.AppError, 'README'):
            d.tools_required()

    def test_missing_audio_verification(self):
        with self.assertRaises(d.AppError):
            d.av_streams({'streams': probe_info()['streams'][:1]})

    def pipeline(self, failing=None, final_height=1080):
        engine = d.DownloadEngine()
        engine.cache.put(URL, info())
        emits, calls = [], []
        def streams(metadata, v, a, paths, emit, cancel, concurrency):
            calls.append(concurrency)
            if failing and len(calls) == 1:
                raise RuntimeError(failing)
            for path in paths:
                if path:
                    Path(path).write_bytes(b'fake stream')
        def mux(args, cancel, log):
            Path(args[-1]).write_bytes(b'fake muxed data')
        with tempfile.TemporaryDirectory() as folder, \
                patch('downloader.tools_required', return_value=dict(ffmpeg='ffmpeg', ffprobe='ffprobe', deno='deno')), \
                patch.object(engine, '_streams', side_effect=streams), \
                patch('downloader.run_mux', side_effect=mux), \
                patch('downloader.probe', return_value=probe_info(final_height)) as probe, \
                patch.object(engine, 'metadata', wraps=engine.metadata) as metadata:
            if failing and '403' in failing:
                fresh = info()
                metadata.side_effect = [copy.deepcopy(fresh), copy.deepcopy(fresh)]
            if final_height != 1080:
                with self.assertRaises(d.AppError):
                    engine.download(URL, 1080, folder, lambda *x: emits.append(x))
                self.assertEqual(len(list(Path(folder).glob('.youtube-work/*/final.mp4'))), 1)
            else:
                result = engine.download(URL, 1080, folder, lambda *x: emits.append(x))
                self.assertTrue(result.exists())
                self.assertNotIn(':', result.name)
                self.assertFalse(list(Path(folder).glob('.youtube-work/*')))
            self.assertEqual(probe.call_count, 1)
            return calls, metadata.call_count

    def test_pipeline_checks_once_uses_cache_and_cleans_up(self):
        self.assertEqual(self.pipeline(), ([2], 1))

    def test_403_refreshes_metadata_once_and_falls_back_to_one_fragment(self):
        self.assertEqual(self.pipeline('HTTP Error 403: Forbidden'), ([2, 1], 2))

    def test_network_retry_reuses_metadata(self):
        self.assertEqual(self.pipeline('connection reset'), ([2, 1], 1))

    def test_failed_verification_preserves_inputs(self):
        self.pipeline(final_height=720)


if __name__ == '__main__':
    unittest.main()

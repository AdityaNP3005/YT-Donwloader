"""Actual yt-dlp + FFmpeg tests with local fixtures; no YouTube connection."""
import copy
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import downloader as d


def run(*args):
    subprocess.run(list(args), check=True, capture_output=True)


@unittest.skipUnless(d.find_tool('ffmpeg') and d.find_tool('ffprobe'), 'FFmpeg/FFprobe not installed')
class MediaIntegrationTests(unittest.TestCase):
    def test_real_ytdlp_and_lossless_mp4_mkv_download_pipeline(self):
        try:
            import yt_dlp
        except ImportError:
            self.skipTest('yt-dlp not installed in test interpreter')
        ffmpeg = d.find_tool('ffmpeg')
        normal_options = d.options
        def local_options(emit):
            opts = normal_options(emit)
            opts['enable_file_urls'] = True  # Only this local fixture test permits file URLs.
            return opts
        with tempfile.TemporaryDirectory(prefix='media test ') as folder:
            root = Path(folder)
            v, a, other = root / 'video.mp4', root / 'audio.m4a', root / 'video.webm'
            run(ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                'color=c=blue:s=1920x1080:r=24:d=0.5', '-an', '-c:v', 'libx264', '-threads', '1', str(v))
            run(ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                'sine=frequency=440:duration=0.5', '-vn', '-c:a', 'aac', str(a))
            run(ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                'color=c=blue:s=1920x1080:r=24:d=0.5', '-an', '-c:v', 'libvpx-vp9',
                '-deadline', 'realtime', '-cpu-used', '8', '-threads', '1', str(other))
            for codec, fixture, extension in [('avc1.640028', v, 'mp4'), ('vp9', other, 'mkv')]:
                with self.subTest(extension=extension):
                    engine = d.DownloadEngine()
                    url = 'https://www.youtube.com/watch?v=abcdefghijk'
                    metadata = {'id': 'abcdefghijk', 'title': 'Judul: lokal / dengan spasi',
                                'extractor': 'youtube', 'extractor_key': 'Youtube', 'webpage_url': url,
                                'formats': [dict(format_id='v', height=1080, width=1920, vcodec=codec,
                                                 acodec='none', ext=fixture.suffix[1:], url=fixture.as_uri(), protocol='file'),
                                            dict(format_id='a', vcodec='none', acodec='mp4a.40.2',
                                                 ext='m4a', url=a.as_uri(), protocol='file')]}
                    # Real extract_info(download=False) returns the default chosen
                    # format as well as all formats. It must not trigger another mux.
                    metadata.update(requested_formats=copy.deepcopy(metadata['formats']),
                                    format_id='v+a', protocol='file+file', ext='mkv')
                    engine.cache.put(url, metadata)
                    with patch('downloader.options', side_effect=local_options), \
                            patch.object(engine, 'metadata', wraps=engine.metadata) as lookup:
                        result = engine.download(url, 1080, root / 'hasil spasi', lambda *_: None)
                    self.assertEqual(lookup.call_count, 1)
                    self.assertEqual(result.suffix, '.' + extension)
                    video, audio = d.av_streams(d.probe(result, d.find_tool('ffprobe')))
                    self.assertEqual(video['height'], 1080)
                    self.assertEqual(video['codec_name'], 'h264' if extension == 'mp4' else 'vp9')
                    self.assertEqual(audio['codec_name'], 'aac')


if __name__ == '__main__':
    unittest.main()

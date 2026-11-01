"""Optional benchmark; --network reads public YouTube metadata, never full video."""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import downloader as d


def memory_mib():
    if os.name != 'nt':
        return None
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wt.DWORD), ('faults', wt.DWORD)] + [(key, ctypes.c_size_t) for key in
            ('peak_working', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = wt.HANDLE
    handle = kernel.GetCurrentProcess()
    api = ctypes.WinDLL('psapi')
    api.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
    if not api.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return None
    return counters.working / 1048576


def command_metrics(args):
    started = time.perf_counter()
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    _, error = process.communicate()
    if process.returncode:
        raise RuntimeError(error.decode('utf-8', errors='replace'))
    cpu = None
    if os.name == 'nt':
        values = [wt.FILETIME() for _ in range(4)]
        api = ctypes.WinDLL('kernel32')
        api.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
        if api.GetProcessTimes(int(process._handle), *[ctypes.byref(v) for v in values]):
            cpu = sum((v.dwHighDateTime << 32) + v.dwLowDateTime for v in values[2:]) / 10_000_000
    return {'wall_seconds': time.perf_counter() - started, 'child_cpu_seconds': cpu}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--network', action='store_true')
    parser.add_argument('--url', default='https://www.youtube.com/watch?v=LRy-MMx2pvI')
    args = parser.parse_args()
    output = {'notes': '3 repetitions. Network reference is metadata re-extraction, not an end-to-end old-app benchmark.'}
    ffmpeg = d.tools_required()['ffmpeg']
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        source = folder / 'source.mkv'
        command_metrics([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
            'color=c=blue:s=1920x1080:r=24:d=1', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libvpx-vp9', '-deadline', 'realtime', '-cpu-used', '8', '-threads', '1',
            '-c:a', 'libopus', '-shortest', str(source)])
        legacy, optimized = [], []
        for _ in range(3):
            legacy.append(command_metrics([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(folder / 'legacy.mp4')]))
            optimized.append(command_metrics(d.mux_args(source, None, folder / 'new.mkv', ffmpeg)))
        output['synthetic_1080p_postprocessing'] = {'legacy_transcode': legacy, 'new_lossless_mux': optimized}
    if args.network:
        engine = d.DownloadEngine()
        cold, cached = [], []
        cpu = time.process_time()
        for _ in range(3):
            started = time.perf_counter()
            metadata = engine.metadata(args.url, lambda *_: None, refresh=True)
            cold.append(time.perf_counter() - started)
            started = time.perf_counter()
            engine.metadata(args.url, lambda *_: None)
            cached.append(time.perf_counter() - started)
        output['network_metadata'] = {'title': metadata['title'], 'resolutions': d.resolutions(metadata),
            'reextract_seconds': cold, 'cached_seconds': cached,
            'median_reextract_seconds': statistics.median(cold), 'median_cached_seconds': statistics.median(cached),
            'python_cpu_seconds_total': time.process_time() - cpu, 'python_working_set_mib': memory_mib()}
        cancel = threading.Event()
        entries = engine.playlist('https://www.youtube.com/playlist?list=PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU', lambda *_: None, cancel)
        try:
            output['live_playlist_first_entry'] = next(entries)
        finally:
            entries.close()
    path = Path(__file__).resolve().parents[1] / '.tools' / 'benchmark.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()

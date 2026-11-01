"""Manual/CI desktop smoke test: python tests/gui_smoke.py [--capture-wait]."""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / '.tools'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        cpu, started = time.process_time(), time.perf_counter()
        window = App(Path(folder) / 'state.json')
        window.withdraw()
        for number in range(1000):
            window.controller.add(f'https://www.youtube.com/watch?v={number:011d}',
                                  'ROOM TOUR RUMAH TAKIM !!!' if number == 0 else f'Video playlist {number + 1:04d}')
        with window.controller.condition:
            for i, job in enumerate(window.controller.jobs[:8]):
                job.height, job.ext = (720 if i == 2 else 1080), ('mkv' if i == 3 else 'mp4')
                job.status, job.percent = 'done', 100
            first = window.controller.jobs[8]
            first.height, first.ext, first.status, first.percent = 1080, 'mp4', 'downloading', 42.7
            first.speed, first.eta, first.stage = 4_500_000, 28, 'Mengunduh stream 1/2'
            window.controller.active_id = first.id
            window.controller.running = False  # Simulated display; never download fixtures.
            failed = window.controller.jobs[9]
            failed.status, failed.error = 'failed', 'Video tidak tersedia. Entri berikutnya tetap diproses.'
        window.links.insert('1.0', 'https://www.youtube.com/watch?v=LRy-MMx2pvI\nhttps://www.youtube.com/playlist?list=PLcontoh')
        tick = time.perf_counter()
        window.render()
        render_ms = (time.perf_counter() - tick) * 1000
        window.update()
        assert len(window.tree.get_children()) == 100
        window.turn_page(9)
        assert len(window.tree.get_children()) == 100 and window.page == 9
        window.turn_page(-9)
        window.controller.select_all(False)
        window.render()
        assert all(window.tree.item(i, 'values')[0] == '—' for i in window.tree.get_children() if i != first.id)
        window.controller.select_all(True)
        window.render()
        setup_seconds, setup_cpu = time.perf_counter() - started, time.process_time() - cpu
        window.deiconify()
        window.update()
        assert window.progress.winfo_ismapped()
        assert window.footer.winfo_rooty() + window.footer.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        window.geometry('860x650')
        window.update()
        window.toggle_details()
        window.update()
        assert window.detail.winfo_ismapped()
        assert window.footer.winfo_rooty() + window.footer.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        window.toggle_details()
        window.geometry('1080x760')
        window.update()
        handle = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
        bounds = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(bounds))
        (artifacts / 'ui-window.json').write_text(json.dumps({'hwnd': handle,
            'width': bounds.right - bounds.left, 'height': bounds.bottom - bounds.top}), encoding='utf-8')
        delays = []
        last = [time.perf_counter()]
        idle_cpu, idle_started = time.process_time(), time.perf_counter()
        def heartbeat():
            now = time.perf_counter()
            delays.append(max(0, now - last[0] - 0.05))
            last[0] = now
            if len(delays) < 40:
                window.after(50, heartbeat)
            else:
                result = {'entries': 1000, 'visible_rows': len(window.tree.get_children()),
                          'setup_seconds': setup_seconds, 'setup_python_cpu_seconds': setup_cpu,
                          'render_ms': render_ms, 'max_heartbeat_delay_ms': max(delays) * 1000,
                          'idle_python_cpu_seconds': time.process_time() - idle_cpu,
                          'idle_wall_seconds': time.perf_counter() - idle_started}
                (artifacts / 'ui-performance.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                window.after(8000 if '--capture-wait' in sys.argv else 0, window.close)
        window.after(50, heartbeat)
        window.mainloop()
        print((artifacts / 'ui-performance.json').read_text())


if __name__ == '__main__':
    import ctypes.wintypes
    main()

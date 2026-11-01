"""Manual/CI desktop smoke test: python tests/gui_smoke.py [--capture-wait]."""
import ctypes
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App


def capture(window, name):
    if '--screenshots' not in sys.argv or not sys.platform.startswith('linux'):
        return
    window.update()
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['/usr/bin/python3', str(root / 'scripts/capture_window.py'),
                    str(window.winfo_id()), str(window.winfo_width()), str(window.winfo_height()),
                    str(root / '.tools' / name)], check=True)


def check_responsive_layout(window):
    """Check that resizing reallocates controls without scrolling the page."""
    for width, height in ((1400, 1000), (640, 620), (800, 720), (1400, 1000)):
        window.geometry(f'{window.u(width)}x{window.u(height)}')
        window.update()
        assert window.winfo_width() == window.u(width)
        assert window.winfo_height() == window.u(height)
        if window.compact:
            assert window.settings_panel.winfo_y() >= (window.composer_left.winfo_y()
                                                        + window.composer_left.winfo_height())
        else:
            assert window.settings_panel.winfo_x() > window.composer_left.winfo_x()
        for widget in (window.add_button, window.check_button, window.start_button,
                       window.folder_entry, window.quality, window.tree, window.footer):
            assert widget.winfo_ismapped()
            assert widget.winfo_rootx() >= window.winfo_rootx()
            assert widget.winfo_rootx() + widget.winfo_width() <= window.winfo_rootx() + window.winfo_width()
            assert widget.winfo_rooty() + widget.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        assert window.tree.winfo_height() >= window.u(40)
        assert window.folder_entry.winfo_width() > window.u(40)
        assert window.add_button.winfo_width() >= window.add_button.winfo_reqwidth()
        assert window.add_button.winfo_height() >= window.u(36)
        if window.compact or height < 820:
            assert window.queue_more.winfo_ismapped()
            assert window.selection_more.winfo_ismapped()
        capture(window, f'ui-resize-{width}x{height}.png')
    assert int(window.links.cget('font').split()[-1]) > 0


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / '.tools'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        cpu, started = time.process_time(), time.perf_counter()
        window = App(Path(folder) / 'state.json')
        window.update()
        assert window.winfo_class() == 'Youtubedownloader'
        assert len(window.logo_images) == 4
        assert window.empty_state.winfo_ismapped()
        assert window.start_button.instate(['disabled'])
        assert window.previous_button.instate(['disabled'])
        assert window.next_button.instate(['disabled'])
        check_responsive_layout(window)
        capture(window, 'ui-empty.png')
        with patch.object(window, 'clipboard_get', return_value='https://youtu.be/abcdefghijk'):
            window.paste_links()
        assert window.links.get('1.0', 'end-1c') == 'https://youtu.be/abcdefghijk'
        window.links.delete('1.0', 'end')
        window.playlist_toggle.invoke()
        assert window.whole.get()
        window.playlist_toggle.invoke()
        assert not window.whole.get()
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
        assert not window.empty_state.winfo_ismapped()
        render_ms = (time.perf_counter() - tick) * 1000
        window.update()
        assert len(window.tree.get_children()) == 100
        assert window.next_button.instate(['!disabled'])
        window.turn_page(9)
        assert len(window.tree.get_children()) == 100 and window.page == 9
        assert window.next_button.instate(['disabled'])
        assert window.previous_button.instate(['!disabled'])
        window.turn_page(-9)
        window.controller.select_all(False)
        window.render()
        assert all(window.tree.item(i, 'values')[0] == '—' for i in window.tree.get_children() if i != first.id)
        window.controller.select_all(True)
        window.render()
        setup_seconds, setup_cpu = time.perf_counter() - started, time.process_time() - cpu
        window.deiconify()
        window.update()
        capture(window, 'ui-queue.png')
        assert window.progress.winfo_ismapped()
        assert window.footer.winfo_rooty() + window.footer.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        window.geometry('860x650')
        window.update()
        window.toggle_details()
        window.update()
        assert window.detail.winfo_ismapped()
        assert not window.empty_state.winfo_ismapped()
        assert window.footer.winfo_rooty() + window.footer.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        capture(window, 'ui-details.png')
        window.toggle_details()
        window.geometry('1080x760')
        window.update()
        capture(window, 'ui-compact.png')
        if sys.platform == 'win32':
            handle = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
            bounds = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(bounds))
            geometry = {'hwnd': handle, 'width': bounds.right - bounds.left,
                        'height': bounds.bottom - bounds.top}
        else:
            geometry = {'width': window.winfo_width(), 'height': window.winfo_height()}
        (artifacts / 'ui-window.json').write_text(json.dumps(geometry), encoding='utf-8')
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

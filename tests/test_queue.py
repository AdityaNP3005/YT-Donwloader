import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from downloader import Cancelled
from queue_model import Mailbox, QueueController


def url(number):
    return f'https://www.youtube.com/watch?v={number:011d}'


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Background operation timed out')


class FakeEngine:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.fail = False
        self.error_message = 'network error'
        self.call_times = []

    def download(self, link, cap, folder, emit, cancel, job_id):
        self.calls.append(link)
        self.call_times.append(time.monotonic())
        self.started.set()
        while not self.release.wait(0.01):
            if cancel.is_set():
                raise Cancelled('cancelled')
        if self.fail and len(self.calls) == 1:
            raise RuntimeError(self.error_message)
        emit('selection', {'title': 'Video', 'height': 720, 'ext': 'mp4'})
        return Path(folder) / 'result.mp4'


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = FakeEngine()
        self.controller = QueueController(Path(self.temp.name) / 'state.json', engine=self.engine, inter_video_delay=0)

    def tearDown(self):
        self.engine.release.set()
        self.controller.shutdown()
        self.temp.cleanup()

    def test_deduplication_and_selected_only(self):
        first = self.controller.add(url(1))
        second = self.controller.add(url(2))
        self.assertIsNone(self.controller.add('https://youtu.be/00000000001'))
        self.controller.select([first], False)
        self.engine.release.set()
        self.controller.start()
        wait_for(lambda: self.controller.get(second).status == 'done')
        self.assertEqual(self.engine.calls, [url(2)])
        self.assertEqual(self.controller.get(first).status, 'pending')

    def test_pause_after_active_and_add_during_download(self):
        first = self.controller.add(url(1))
        self.controller.start()
        self.assertTrue(self.engine.started.wait(1))
        second = self.controller.add(url(2))
        self.controller.pause()
        self.engine.release.set()
        wait_for(lambda: self.controller.get(first).status == 'done')
        self.assertEqual(self.controller.get(second).status, 'pending')
        self.assertEqual(len(self.engine.calls), 1)

    def test_queue_waits_for_incremental_playlist_entries(self):
        self.controller.begin_import()
        first = self.controller.add(url(1))
        self.engine.release.set()
        self.controller.start()
        wait_for(lambda: self.controller.get(first).status == 'done')
        self.assertTrue(self.controller.running)
        second = self.controller.add(url(2))
        wait_for(lambda: self.controller.get(second).status == 'done')
        self.controller.end_import()
        self.assertFalse(self.controller.running)

    def test_failure_continues_queue_and_can_retry(self):
        self.engine.fail = True
        self.engine.release.set()
        first, second = self.controller.add(url(1)), self.controller.add(url(2))
        self.controller.start()
        wait_for(lambda: self.controller.get(second).status == 'done')
        self.assertEqual(self.controller.get(first).status, 'failed')
        self.controller.retry_failed()
        self.assertEqual(self.controller.get(first).status, 'pending')
        self.controller.start()
        wait_for(lambda: self.controller.get(first).status == 'done')

    def test_delay_between_downloads(self):
        self.controller.inter_video_delay = 0.2
        self.engine.release.set()
        self.controller.add(url(1))
        second = self.controller.add(url(2))
        self.controller.start()
        wait_for(lambda: self.controller.get(second).status == 'done')
        self.assertGreaterEqual(self.engine.call_times[1] - self.engine.call_times[0], 0.2)

    def test_pause_interrupts_delay_and_resume_keeps_jobs(self):
        self.controller.inter_video_delay = 0.15
        self.engine.release.set()
        self.controller.add(url(1))
        second = self.controller.add(url(2))
        self.controller.start()
        wait_for(lambda: self.controller.waiting)
        self.controller.pause()
        time.sleep(0.2)
        self.assertEqual(self.engine.calls, [url(1)])
        self.assertEqual(self.controller.get(second).status, 'pending')
        self.controller.start()
        wait_for(lambda: self.controller.get(second).status == 'done')

    def test_shutdown_does_not_wait_for_download_delay(self):
        self.controller.inter_video_delay = 60
        self.engine.release.set()
        self.controller.add(url(1))
        self.controller.add(url(2))
        self.controller.start()
        wait_for(lambda: self.controller.waiting)
        started = time.monotonic()
        self.controller.shutdown()
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(self.engine.calls, [url(1)])

    def test_restriction_pauses_queue_preserves_job_and_manual_resume(self):
        self.engine.fail = True
        self.engine.error_message = 'HTTP Error 429: Too Many Requests'
        self.engine.release.set()
        first, second = self.controller.add(url(1)), self.controller.add(url(2))
        self.controller.start()
        wait_for(lambda: bool(self.controller.notice))
        self.assertFalse(self.controller.running)
        self.assertEqual(self.engine.calls, [url(1)])
        self.assertEqual(self.controller.get(first).status, 'pending')
        self.assertEqual(self.controller.get(second).status, 'pending')
        self.assertIn('429', self.controller.get(first).error)
        self.assertEqual([j['status'] for j in self.controller.snapshot()['jobs']], ['pending', 'pending'])
        self.controller.start()
        wait_for(lambda: self.controller.get(second).status == 'done')
        self.assertEqual(self.engine.calls, [url(1), url(1), url(2)])

    def test_cancellation_preserves_job_and_retry_identity(self):
        first = self.controller.add(url(1))
        self.controller.start()
        self.assertTrue(self.engine.started.wait(1))
        self.controller.pause()
        self.controller.cancel_active()
        wait_for(lambda: self.controller.get(first).status == 'cancelled')
        self.controller.retry_failed()
        self.assertEqual(self.controller.get(first).id, first)
        self.assertEqual(self.controller.get(first).status, 'pending')

    def test_1000_entries_page_and_progress_mailbox_are_bounded(self):
        for i in range(1000):
            self.controller.add(url(i))
        page, count, number, *_ = self.controller.view(9)
        self.assertEqual((len(page), count, number), (100, 1000, 9))
        self.assertEqual(self.controller.view(999)[2], 9)
        mailbox = Mailbox()
        for i in range(10000):
            mailbox.post('changed')
            mailbox.post('log', str(i))
        dirty, logs, notices = mailbox.drain()
        self.assertTrue(dirty)
        self.assertEqual(len(logs), 500)
        self.assertEqual(notices, [])

    def test_restore_active_as_pending_and_never_autostart(self):
        first = self.controller.add(url(1))
        with self.controller.condition:
            self.controller.by_id[first].status = 'muxing'
        self.controller.shutdown()
        data = json.loads(self.controller.path.read_text(encoding='utf-8'))
        self.assertNotIn('percent', data['jobs'][0])
        restored = QueueController(self.controller.path, engine=FakeEngine())
        try:
            self.assertEqual(restored.get(first).status, 'pending')
            self.assertFalse(restored.running)
            self.assertFalse(restored.engine.started.is_set())
        finally:
            restored.shutdown()

    def test_settings_apply_only_to_selected_pending_and_remove_is_safe(self):
        first, second = self.controller.add(url(1)), self.controller.add(url(2))
        self.controller.select([second], False)
        self.controller.configure(720, 'folder baru')
        self.assertEqual(self.controller.get(first).cap, 720)
        self.assertEqual(self.controller.get(second).cap, 1080)
        self.controller.start()
        self.assertTrue(self.engine.started.wait(1))
        self.controller.remove_selected()
        self.assertIsNotNone(self.controller.get(first))
        self.assertIsNotNone(self.controller.get(second))


if __name__ == '__main__':
    unittest.main()

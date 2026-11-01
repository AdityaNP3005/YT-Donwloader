"""A lightweight desktop download manager. Run through the .bat launcher."""
from collections import deque
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from downloader import Cancelled, check_cancel, normalize_url, parse_link
from queue_model import LABELS, Mailbox, QueueController


ROOT = Path(__file__).resolve().parent
PAGE_SIZE = 100
BG, WHITE, INK, MUTED, LINE, BLUE = '#f3f5f8', '#ffffff', '#192434', '#5c687a', '#dce2ea', '#235bd6'


class App(tk.Tk):
    def __init__(self, state_path=None):
        super().__init__()
        self.title('YouTube Downloader')
        self.geometry(f'{min(1080, max(860, self.winfo_screenwidth() - 80))}x{min(800, max(650, self.winfo_screenheight() - 110))}')
        self.minsize(860, 650)
        self.configure(bg=BG)
        self.mailbox = Mailbox()
        self.controller = QueueController(state_path or ROOT / 'data' / 'state.json', mailbox=self.mailbox)
        self.page = 0
        self.rows = {}
        self.logs = deque(maxlen=500)
        self.aux_thread = None
        self.aux_cancel = threading.Event()
        self.closing = False
        self.close_thread = None
        self.cap = tk.StringVar(value=f"{self.controller.settings['cap']}p")
        self.folder = tk.StringVar(value=self.controller.settings['folder'])
        self.whole = tk.BooleanVar(value=False)
        self.input_status = tk.StringVar(value='Satu link per baris. Video dan playlist dapat dicampur.')
        self.summary = tk.StringVar()
        self.status = tk.StringVar(value='Siap. Tambahkan link untuk memulai.')
        self.transfer = tk.StringVar(value='1 video aktif · hingga 2 fragmen paralel')
        self.page_text = tk.StringVar()
        self.detail_visible = False
        self.style_ui()
        self.build_ui()
        self.render()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.poll)

    def style_ui(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=INK)
        style.configure('TFrame', background=BG)
        style.configure('White.TFrame', background=WHITE)
        style.configure('TLabel', background=BG)
        style.configure('White.TLabel', background=WHITE)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('TButton', padding=(12, 7), background=WHITE, bordercolor=LINE)
        style.map('TButton', background=[('active', '#e8edf5')])
        style.configure('Accent.TButton', background=BLUE, foreground=WHITE, bordercolor=BLUE)
        style.map('Accent.TButton', background=[('active', '#1947ad'), ('disabled', '#a5b8df')], foreground=[('disabled', WHITE)])
        style.configure('TEntry', padding=6, fieldbackground=WHITE)
        style.configure('TCombobox', padding=5, fieldbackground=WHITE)
        style.configure('White.TCheckbutton', background=WHITE)
        style.configure('Treeview', background=WHITE, fieldbackground=WHITE, rowheight=33, borderwidth=0)
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), padding=(8, 9), background='#eaf0f7')
        style.map('Treeview', background=[('selected', '#dce9ff')], foreground=[('selected', INK)])
        style.configure('Horizontal.TProgressbar', background=BLUE, troughcolor='#e2e8f1', thickness=6)

    def build_ui(self):
        panel = ttk.Frame(self, padding=(24, 18))
        panel.pack(fill='both', expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(5, weight=1)
        header = ttk.Frame(panel)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 16))
        ttk.Label(header, text='YouTube Downloader', font=('Segoe UI', 21, 'bold')).pack(side='left')
        ttk.Label(header, text='VIDEO + SUARA', foreground=MUTED, font=('Segoe UI', 9, 'bold')).pack(side='right', pady=8)

        input_card = ttk.Frame(panel, style='White.TFrame', padding=14)
        input_card.grid(row=1, column=0, sticky='ew')
        ttk.Label(input_card, text='Tambahkan video atau playlist', style='White.TLabel', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.links = tk.Text(input_card, height=3, wrap='none', font=('Segoe UI', 10), background=WHITE,
                             foreground=INK, relief='solid', borderwidth=1, highlightthickness=0, padx=9, pady=7, undo=True)
        self.links.pack(fill='x', pady=(8, 9))
        actions = ttk.Frame(input_card, style='White.TFrame')
        actions.pack(fill='x')
        self.add_button = ttk.Button(actions, text='Tambahkan ke antrean', style='Accent.TButton', command=self.add_links)
        self.add_button.pack(side='left')
        self.check_button = ttk.Button(actions, text='Cek satu video', command=self.check_video)
        self.check_button.pack(side='left', padx=8)
        self.stop_import = ttk.Button(actions, text='Hentikan pemeriksaan', command=self.cancel_aux, state='disabled')
        self.stop_import.pack(side='left')
        ttk.Checkbutton(actions, text='Seluruh playlist pada link video', variable=self.whole, style='White.TCheckbutton').pack(side='right')
        ttk.Label(panel, textvariable=self.input_status, style='Muted.TLabel', wraplength=980).grid(row=2, column=0, sticky='w', pady=(7, 12))

        settings = ttk.Frame(panel)
        settings.grid(row=3, column=0, sticky='ew', pady=(0, 14))
        ttk.Label(settings, text='Kualitas hingga').pack(side='left')
        self.quality = ttk.Combobox(settings, textvariable=self.cap, values=['360p', '480p', '720p', '1080p', '1440p', '2160p', '4320p'], state='readonly', width=8)
        self.quality.pack(side='left', padx=(8, 16))
        self.quality.bind('<<ComboboxSelected>>', lambda _: self.save_settings())
        ttk.Label(settings, text='Simpan ke').pack(side='left')
        self.folder_entry = ttk.Entry(settings, textvariable=self.folder)
        self.folder_entry.pack(side='left', fill='x', expand=True, padx=8)
        self.folder_entry.bind('<FocusOut>', lambda _: self.save_settings())
        self.folder_entry.bind('<Return>', lambda _: self.save_settings())
        ttk.Button(settings, text='Pilih folder', command=self.browse).pack(side='left')

        toolbar = ttk.Frame(panel)
        toolbar.grid(row=4, column=0, sticky='ew', pady=(0, 10))
        self.start_button = ttk.Button(toolbar, text='Mulai', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.pause_button = ttk.Button(toolbar, text='Jeda setelah video ini', command=self.controller.pause)
        self.pause_button.pack(side='left', padx=6)
        self.cancel_button = ttk.Button(toolbar, text='Batalkan video aktif', command=self.controller.cancel_active)
        self.cancel_button.pack(side='left')
        ttk.Button(toolbar, text='Coba lagi yang gagal', command=self.controller.retry_failed).pack(side='left', padx=6)
        ttk.Button(toolbar, text='Hapus terpilih', command=self.controller.remove_selected).pack(side='right')

        table = ttk.Frame(panel)
        self.table = table
        table.grid(row=5, column=0, sticky='nsew')
        self.tree = ttk.Treeview(table, columns=('pick', 'title', 'quality', 'format', 'progress', 'status'), show='headings', selectmode='browse')
        for key, title, width, stretch in [('pick', 'Pilih', 48, False), ('title', 'Judul', 380, True),
                                          ('quality', 'Kualitas', 95, False), ('format', 'Format', 65, False),
                                          ('progress', 'Progres', 80, False), ('status', 'Status', 110, False)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=40, stretch=stretch, anchor='w' if key == 'title' else 'center')
        self.tree.tag_configure('failed', foreground='#af3030')
        self.tree.tag_configure('done', foreground='#26704c')
        self.tree.tag_configure('active', background='#f0f5ff')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.table_scroll = scroll
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<ButtonRelease-1>', self.row_click)
        self.tree.bind('<space>', self.toggle_row)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.render_detail())
        self.tree.bind('<Double-1>', self.open_selected)

        pagination = ttk.Frame(panel)
        pagination.grid(row=6, column=0, sticky='ew', pady=8)
        ttk.Button(pagination, text='Pilih semua', command=lambda: self.controller.select_all(True)).pack(side='left')
        ttk.Button(pagination, text='Kosongkan pilihan', command=lambda: self.controller.select_all(False)).pack(side='left', padx=6)
        ttk.Button(pagination, text='›', width=3, command=lambda: self.turn_page(1)).pack(side='right')
        ttk.Label(pagination, textvariable=self.page_text).pack(side='right', padx=10)
        ttk.Button(pagination, text='‹', width=3, command=lambda: self.turn_page(-1)).pack(side='right')
        ttk.Label(panel, textvariable=self.summary, style='Muted.TLabel').grid(row=7, column=0, sticky='w')
        self.progress = ttk.Progressbar(panel, maximum=100)
        self.progress.grid(row=8, column=0, sticky='ew', pady=(10, 7))
        ttk.Label(panel, textvariable=self.status, wraplength=980).grid(row=9, column=0, sticky='w')
        footer = ttk.Frame(panel)
        self.footer = footer
        footer.grid(row=10, column=0, sticky='ew', pady=(3, 0))
        ttk.Label(footer, textvariable=self.transfer, style='Muted.TLabel').pack(side='left')
        self.details_button = ttk.Button(footer, text='Detail & log', command=self.toggle_details)
        self.details_button.pack(side='right')
        ttk.Button(footer, text='Buka folder', command=self.open_folder).pack(side='right', padx=6)
        self.detail = tk.Text(table, height=5, wrap='word', font=('Consolas', 9), bg=WHITE, fg=INK,
                              relief='solid', borderwidth=1, padx=8, pady=6, state='disabled')

    def save_settings(self):
        folder = self.folder.get().strip()
        if folder:
            self.controller.configure(int(self.cap.get().rstrip('p')), folder)

    def browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder.set(folder)
            self.save_settings()

    def start(self):
        if not self.folder.get().strip():
            self.input_status.set('Pilih folder penyimpanan terlebih dahulu.')
            return
        self.save_settings()
        self.controller.start()

    def begin_aux(self, task):
        if self.aux_thread and self.aux_thread.is_alive():
            return
        self.aux_cancel = threading.Event()
        cancel = self.aux_cancel
        self.add_button.configure(state='disabled')
        self.check_button.configure(state='disabled')
        self.stop_import.configure(state='normal')
        self.controller.begin_import()
        def worker():
            try:
                task(cancel)
            except Cancelled:
                self.mailbox.post('input', 'Pemeriksaan dihentikan. Entri yang sudah ditambahkan tetap tersedia.')
            except Exception as exc:
                self.mailbox.post('input', 'Pemeriksaan gagal. Buka Detail & log untuk pesan lengkap.')
                self.mailbox.post('log', str(exc))
            finally:
                self.controller.end_import()
                self.mailbox.post('aux_done')
        self.aux_thread = threading.Thread(target=worker, daemon=True, name='link-import')
        self.aux_thread.start()

    def cancel_aux(self):
        self.aux_cancel.set()
        self.input_status.set('Menghentikan pemeriksaan; menunggu permintaan jaringan yang sedang berjalan...')

    def check_video(self):
        lines = [line.strip() for line in self.links.get('1.0', 'end').splitlines() if line.strip()]
        if len(lines) != 1:
            self.input_status.set('Cek satu video menerima satu link. Gunakan Tambahkan ke antrean untuk banyak link.')
            return
        try:
            url = normalize_url(lines[0])
        except Exception as exc:
            self.input_status.set(str(exc))
            return
        self.save_settings()
        cap, folder = int(self.cap.get()[:-1]), self.folder.get().strip()
        self.input_status.set('Memeriksa video. Metadata akan digunakan kembali saat download...')
        def check(cancel):
            result = self.controller.engine.inspect(url, lambda kind, value: self.mailbox.post('log' if kind == 'log' else 'input', value), cancel)
            check_cancel(cancel)
            self.controller.add(url, result['title'], cap, folder)
            self.mailbox.post('input', f"{result['title']} · tersedia: {', '.join(str(h) + 'p' for h in result['resolutions'])}. Siap di antrean.")
        self.begin_aux(check)

    def add_links(self):
        raw = self.links.get('1.0', 'end')
        if not raw.strip():
            self.input_status.set('Paste minimal satu link terlebih dahulu.')
            return
        self.save_settings()
        cap, folder, whole = int(self.cap.get()[:-1]), self.folder.get().strip(), self.whole.get()
        self.input_status.set('Menambahkan link. Playlist dimuat bertahap tanpa memeriksa semua format...')
        self.links.tag_remove('invalid', '1.0', 'end')
        self.links.tag_configure('invalid', background='#ffe8e8')
        # Parse and highlight input on Tk's thread; all network I/O stays off it.
        parsed, invalid = [], 0
        for number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed.append(parse_link(line, whole))
            except Exception as exc:
                invalid += 1
                self.links.tag_add('invalid', f'{number}.0', f'{number}.end')
                self.mailbox.post('log', f'Baris {number}: {exc}')
        def import_links(cancel):
            added = duplicates = 0
            for kind, url in dict.fromkeys(parsed):
                check_cancel(cancel)
                entries = self.controller.engine.playlist(url, lambda k, v: self.mailbox.post('log', v), cancel) if kind == 'playlist' else [{'url': url}]
                try:
                    for entry in entries:
                        check_cancel(cancel)
                        job_id = self.controller.add(entry['url'], entry.get('title'), cap, folder, entry.get('unavailable', False))
                        added += bool(job_id)
                        duplicates += job_id is None
                        if (added + duplicates) % 50 == 0:
                            self.mailbox.post('input', f'{added} video ditambahkan · {duplicates} duplikat dilewati. Masih memuat...')
                except Cancelled:
                    raise
                except Exception as exc:
                    self.mailbox.post('log', f'{url}: {exc}')
                    invalid_count[0] += 1
            self.mailbox.post('input', f'{added} video ditambahkan · {duplicates} duplikat · {invalid + invalid_count[0]} input gagal. Pilih entri, lalu Mulai.')
        invalid_count = [0]
        self.begin_aux(import_links)

    def row_click(self, event):
        if self.tree.identify_column(event.x) == '#1':
            job_id = self.tree.identify_row(event.y)
            job = self.controller.get(job_id)
            if job:
                self.controller.select([job_id], not job.selected)

    def toggle_row(self, _=None):
        selected = self.tree.selection()
        if selected:
            job = self.controller.get(selected[0])
            if job:
                self.controller.select([job.id], not job.selected)
        return 'break'

    def turn_page(self, delta):
        self.page += delta
        self.render()

    def open_folder(self):
        selected = self.tree.selection()
        job = self.controller.get(selected[0]) if selected else None
        path = Path(job.result).parent if job and job.result else Path(self.folder.get()).expanduser()
        try:
            os.startfile(str(path))
        except OSError as exc:
            self.mailbox.post('log', f'Folder belum tersedia: {exc}')
            self.input_status.set('Folder belum tersedia; akan dibuat saat download dimulai.')

    def open_selected(self, _=None):
        selected = self.tree.selection()
        job = self.controller.get(selected[0]) if selected else None
        if job and job.result and Path(job.result).is_file():
            try:
                os.startfile(job.result)
            except OSError as exc:
                self.mailbox.post('log', str(exc))

    def toggle_details(self):
        self.detail_visible = not self.detail_visible
        if self.detail_visible:
            self.tree.pack_forget()
            self.table_scroll.pack_forget()
            self.detail.pack(fill='both', expand=True)
            self.details_button.configure(text='Kembali ke antrean')
            self.render_detail()
        else:
            self.detail.pack_forget()
            self.tree.pack(side='left', fill='both', expand=True)
            self.table_scroll.pack(side='right', fill='y')
            self.details_button.configure(text='Detail & log')

    def render_detail(self):
        if not self.detail_visible:
            return
        selected = self.tree.selection()
        job = self.controller.get(selected[0]) if selected else None
        heading = f'{job.title}\n{job.url}\n{job.error or job.result or job.stage}\n\n' if job else ''
        content = heading + '\n'.join(self.logs)
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('1.0', content)
        self.detail.configure(state='disabled')

    def render(self):
        jobs, count, self.page, counts, active, running = self.controller.view(self.page, PAGE_SIZE)
        ids = [j.id for j in jobs]
        old_ids = list(self.tree.get_children())
        if old_ids != ids:
            self.tree.delete(*old_ids)
            self.rows.clear()
        for job in jobs:
            quality = f'{job.height}p' if job.height else f'≤ {job.cap}p'
            if job.height and job.height < job.cap:
                quality += ' ↓'
            values = ('✓' if job.selected else '—', job.title, quality, job.ext.upper() or 'Auto',
                      f'{job.percent:.0f}%' if job.percent is not None else '—', LABELS[job.status])
            tag = 'active' if job.id == (active.id if active else None) else job.status
            row = (values, tag)
            if self.rows.get(job.id) != row:
                if self.tree.exists(job.id):
                    self.tree.item(job.id, values=values, tags=(tag,))
                else:
                    self.tree.insert('', 'end', iid=job.id, values=values, tags=(tag,))
                self.rows[job.id] = row
        self.page_text.set(f'Halaman {self.page + 1} / {max(1, (count + 99) // 100)}')
        self.summary.set(f"{count} video   ·   {counts['pending']} menunggu   ·   {counts['done']} selesai   ·   {counts['failed']} gagal   ·   {counts['cancelled']} dibatalkan")
        self.cancel_button.configure(state='normal' if active and not self.closing else 'disabled')
        self.pause_button.configure(state='normal' if running and not self.closing else 'disabled')
        self.start_button.configure(state='disabled' if running or self.closing else 'normal')
        if self.closing:
            self.status.set('Menghentikan proses dan menyimpan antrean. Tunggu permintaan jaringan selesai...')
        elif active:
            paused = ' · jeda setelah video ini' if not running else ''
            self.status.set(f'{active.title} · {active.stage or LABELS[active.status]}{paused}')
            speed = f'{active.speed / 1048576:.2f} MB/detik' if active.speed else '— MB/detik'
            eta = f'{int(active.eta)} detik' if active.eta is not None else '—'
            self.transfer.set(f'{speed}   ·   ETA stream {eta}   ·   1 video aktif')
        else:
            self.status.set('Antrean menunggu link baru.' if running else 'Siap. Pilih entri lalu klik Mulai; kualitas mengikuti sumber.')
            self.transfer.set('MP4 / MKV otomatis · tanpa encoding ulang · 1 video aktif')
        # No animated timer: keep the last known progress during metadata/muxing.
        self.progress.configure(value=active.percent or 0 if active else (100 if count and counts['done'] == count else 0))

    def poll(self):
        dirty, logs, notices = self.mailbox.drain()
        self.logs.extend(logs)
        for kind, value in notices:
            if kind == 'input':
                self.input_status.set(value)
            elif kind == 'aux_done' and not self.closing:
                self.add_button.configure(state='normal')
                self.check_button.configure(state='normal')
                self.stop_import.configure(state='disabled')
        if dirty:
            self.render()
            if logs:
                self.render_detail()
        if self.closing and self.close_thread and not self.close_thread.is_alive():
            self.destroy()
            return
        self.after(200, self.poll)

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.save_settings()
        self.aux_cancel.set()
        self.add_button.configure(state='disabled')
        self.check_button.configure(state='disabled')
        self.stop_import.configure(state='disabled')
        self.controller.pause()
        self.controller.cancel_active()
        def shutdown():
            if self.aux_thread:
                self.aux_thread.join()
            self.controller.shutdown()
        self.close_thread = threading.Thread(target=shutdown, daemon=True)
        self.close_thread.start()
        self.render()


if __name__ == '__main__':
    App().mainloop()

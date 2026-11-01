"""A lightweight desktop download manager. Run through the platform launcher."""
from collections import deque
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter import font as tkfont

from downloader import Cancelled, check_cancel, normalize_url, parse_link
from queue_model import LABELS, Mailbox, QueueController


ROOT = Path(__file__).resolve().parent
PAGE_SIZE = 100
BG, WHITE, INK, MUTED, LINE, BLUE = '#f3f7fc', '#ffffff', '#1c304a', '#64788f', '#dce6f1', '#1672df'


def open_path(path):
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])


class App(tk.Tk):
    def __init__(self, state_path=None):
        super().__init__(className='YouTubeDownloader')
        self.title('YouTube Downloader')
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
        self.input_status = tk.StringVar(value='Tambahkan tautan untuk menyiapkan unduhan. Kualitas mengikuti video sumber.')
        self.summary = tk.StringVar()
        self.status = tk.StringVar(value='Siap. Tambahkan link untuk memulai.')
        self.transfer = tk.StringVar(value='1 video aktif · hingga 2 fragmen paralel')
        self.page_text = tk.StringVar()
        self.detail_visible = False
        self.style_ui()
        self.geometry(f'{min(self.u(1180), self.winfo_screenwidth() - 60)}x{min(self.u(900), self.winfo_screenheight() - 90)}')
        self.minsize(min(self.u(640), self.winfo_screenwidth() - 60),
                     min(self.u(620), self.winfo_screenheight() - 90))
        self.build_ui()
        self.render()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.poll)

    def u(self, value):
        return round(value * self.ui_scale)

    def space(self, *values):
        return tuple(self.u(value) for value in values)

    def style_ui(self):
        available = set(tkfont.families(self))
        self.font_family = next((name for name in ('Ubuntu Sans', 'Ubuntu', 'Noto Sans', 'DejaVu Sans') if name in available), 'TkDefaultFont')
        # Point sizes follow Tk's display DPI; negative sizes lock text to tiny pixels.
        self.body_font = (self.font_family, 12)
        self.small_font = (self.font_family, 11)
        self.heading_font = (self.font_family, 14, 'bold')
        probe = tkfont.Font(self, font=self.body_font)
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
            tkfont.nametofont(name, root=self).configure(family=self.font_family, size=12)
        self.option_add('*TCombobox*Listbox.font', self.body_font)
        self.ui_scale = max(1, min(3, round(probe.metrics('linespace') / 20)))
        style = ttk.Style(self)
        style.theme_use('clam')
        self.ui_style = style
        style.configure('.', font=self.body_font, background=BG, foreground=INK)
        for name, background in (('TFrame', BG), ('Surface.TFrame', WHITE), ('TLabel', BG), ('Surface.TLabel', WHITE)):
            style.configure(name, background=background)
        style.configure('Muted.TLabel', foreground=MUTED, font=self.small_font)
        style.configure('SurfaceMuted.TLabel', background=WHITE, foreground=MUTED, font=self.small_font)
        style.configure('Section.TLabel', background=WHITE, font=self.heading_font)
        style.configure('Title.TLabel', font=(self.font_family, 22, 'bold'))
        style.configure('TButton', width=0, padding=self.space(14, 10), borderwidth=1, relief='flat', background=WHITE, bordercolor=LINE, focuscolor=BLUE)
        style.map('TButton', background=[('disabled', '#f1f5fa'), ('pressed', '#dcecff'), ('active', '#eaf3ff')], foreground=[('disabled', '#65768b')], bordercolor=[('focus', BLUE), ('active', '#9bc3f4')])
        style.configure('Accent.TButton', background=BLUE, foreground=WHITE, bordercolor=BLUE, focuscolor=WHITE)
        style.map('Accent.TButton', background=[('disabled', '#a4c8f2'), ('pressed', '#0e56ad'), ('active', '#1064c9')], foreground=[('disabled', '#ffffff')], bordercolor=[('focus', '#0b3f7b')])
        style.configure('TMenubutton', font=self.body_font, padding=self.space(12, 9), background=WHITE, foreground=INK, bordercolor=LINE)
        style.configure('Quiet.TButton', bordercolor=WHITE, padding=self.space(10, 9))
        style.map('Quiet.TButton', bordercolor=[('focus', BLUE), ('active', LINE)])
        style.configure('TEntry', padding=self.space(8, 7), fieldbackground=WHITE, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.map('TEntry', bordercolor=[('focus', BLUE)])
        style.configure('TCombobox', padding=self.space(7, 6), fieldbackground=WHITE, background=WHITE, bordercolor=LINE, arrowcolor=MUTED)
        style.map('TCombobox', fieldbackground=[('readonly', WHITE)], bordercolor=[('focus', BLUE)])
        style.configure('Surface.TCheckbutton', background=WHITE, padding=self.space(0, 4))
        style.map('Surface.TCheckbutton', background=[('active', WHITE)])
        style.configure('Treeview', background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=self.u(44), borderwidth=0, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, font=self.body_font)
        style.configure('Treeview.Heading', background='#f3f7fc', foreground=MUTED, font=(self.font_family, 11, 'bold'), padding=self.space(8, 10), relief='flat', borderwidth=0)
        style.map('Treeview.Heading', background=[('active', '#e9f1fb')])
        style.map('Treeview', background=[('selected', '#e5f1ff')], foreground=[('selected', '#184b82')])
        style.configure('Horizontal.TProgressbar', background=BLUE, troughcolor='#dfeafa', borderwidth=0, lightcolor=BLUE, darkcolor=BLUE, thickness=self.u(5))
        style.configure('Vertical.TScrollbar', background='#cad9ea', troughcolor=WHITE, borderwidth=0, arrowsize=self.u(12))
        self.images = {}
        for path in (ROOT / 'assets' / 'icons').glob('*.png'):
            if '@' not in path.stem:
                source = path.with_stem(f'{path.stem}@{self.ui_scale}x') if self.ui_scale > 1 else path
                self.images[path.stem] = tk.PhotoImage(master=self, file=str(source))
        style.element_create('Playlist.indicator', 'image', self.images['checkbox-off'],
                             ('selected', self.images['checkbox-on']), sticky='')
        style.layout('Surface.TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('Playlist.indicator', {'side': 'left', 'sticky': ''}),
            ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
        self.logo_images = [tk.PhotoImage(master=self, file=str(ROOT / 'assets' / f'youtube-downloader-{size}.png')) for size in (256, 64, 32, 16)]
        self.iconphoto(True, *self.logo_images)
        self.brand_image = tk.PhotoImage(master=self, file=str(ROOT / 'assets' / f'youtube-downloader-{self.u(48)}.png'))
        self.empty_image = tk.PhotoImage(master=self, file=str(ROOT / 'assets' / f'youtube-downloader-{self.u(64)}.png'))

    def button(self, parent, text, icon, command, style='TButton', **kwargs):
        key = icon + ('-white' if style == 'Accent.TButton' else '')
        return ttk.Button(parent, text='  ' + text if text else '', image=self.images[key], compound='left', command=command, style=style, **kwargs)

    def build_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        panel = ttk.Frame(self, padding=self.space(20, 18, 20, 16))
        panel.grid(row=0, column=0, sticky='nsew')
        self.layout_pending = None
        self.layout_signature = None
        self.compact = None
        self.composer_breakpoint = None
        self.panel = panel
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        header = ttk.Frame(panel)
        header.grid(row=0, column=0, sticky='ew', pady=self.space(0, 22))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, image=self.brand_image).grid(row=0, column=0, sticky='nw', padx=self.space(0, 13))
        brand = ttk.Frame(header)
        brand.grid(row=0, column=1, sticky='w')
        self.brand = brand
        self.brand_title = ttk.Label(brand, text='YouTube Downloader', style='Title.TLabel')
        self.brand_title.pack(anchor='w')
        self.brand_hint = ttk.Label(brand, text='Unduh video dan playlist ke komputermu.', style='Muted.TLabel')
        self.brand_hint.pack(anchor='w', pady=self.space(3, 0))
        self.open_folder_button = self.button(header, 'Buka folder', 'folder', self.open_folder)
        self.open_folder_button.grid(row=0, column=2, sticky='e')

        composer_border = tk.Frame(panel, background=LINE, borderwidth=0)
        composer_border.grid(row=1, column=0, sticky='ew', pady=self.space(0, 20))
        composer = ttk.Frame(composer_border, style='Surface.TFrame', padding=self.u(18))
        self.composer = composer
        composer.pack(fill='both', expand=True, padx=self.u(1), pady=self.u(1))
        composer.columnconfigure(0, weight=3)
        composer.columnconfigure(2, weight=2)
        left = ttk.Frame(composer, style='Surface.TFrame')
        left.grid(row=0, column=0, sticky='nsew', padx=self.space(0, 20))
        self.composer_left = left
        left.columnconfigure(0, weight=1)
        label_row = ttk.Frame(left, style='Surface.TFrame')
        self.link_label_row = label_row
        label_row.grid(row=0, column=0, sticky='ew', pady=self.space(0, 9))
        ttk.Label(label_row, text='Tambahkan tautan', image=self.images['link'], compound='left', style='Section.TLabel').pack(side='left')
        self.button(label_row, 'Tempel', 'paste', self.paste_links, style='Quiet.TButton').pack(side='right')
        self.links = tk.Text(left, height=3, width=1, wrap='word', font=self.body_font, background='#f8fafd', foreground=INK,
                             insertbackground=BLUE, selectbackground='#d3e7ff', relief='flat', borderwidth=0, highlightthickness=self.u(1),
                             highlightbackground=LINE, highlightcolor=BLUE, padx=self.u(11), pady=self.u(10), undo=True)
        self.links.grid(row=1, column=0, sticky='ew')
        self.links.bind('<Control-Return>', lambda _: self.add_links())
        self.link_hint = ttk.Label(left, text='Satu link per baris. Video dan playlist boleh dicampur.', style='SurfaceMuted.TLabel')
        self.link_hint.grid(row=2, column=0, sticky='w', pady=self.space(7, 11))
        actions = ttk.Frame(left, style='Surface.TFrame')
        actions.grid(row=3, column=0, sticky='ew')
        self.compact_paste = self.button(actions, 'Tempel', 'paste', self.paste_links, style='Quiet.TButton')
        self.add_button = self.button(actions, 'Tambah antrean', 'plus', self.add_links, style='Accent.TButton')
        self.add_button.pack(side='left')
        self.check_button = self.button(actions, 'Cek video', 'search', self.check_video, style='Quiet.TButton')
        self.check_button.pack(side='left', padx=self.space(6, 0))
        self.stop_import = self.button(actions, 'Hentikan', 'stop', self.cancel_aux, style='Quiet.TButton', state='disabled')
        self.stop_import.pack(side='left', padx=self.space(3, 0))

        self.composer_divider = tk.Frame(composer, bg=LINE, width=self.u(1))
        self.composer_divider.grid(row=0, column=1, sticky='ns', padx=self.space(0, 20))
        settings = ttk.Frame(composer, style='Surface.TFrame')
        settings.grid(row=0, column=2, sticky='nsew')
        self.settings_panel = settings
        settings.columnconfigure(0, weight=1)
        self.settings_heading = ttk.Label(settings, text='Pengaturan unduhan', style='Section.TLabel')
        self.settings_heading.grid(row=0, column=0, columnspan=2, sticky='w', pady=self.space(3, 11))
        self.quality_label = ttk.Label(settings, text='Kualitas maksimal', style='SurfaceMuted.TLabel')
        self.quality_label.grid(row=1, column=0, sticky='w', pady=self.space(0, 5))
        self.quality = ttk.Combobox(settings, textvariable=self.cap, values=['360p', '480p', '720p', '1080p', '1440p', '2160p', '4320p'], state='readonly', width=10, font=self.body_font)
        self.quality.grid(row=1, column=1, sticky='e', pady=self.space(0, 5))
        self.quality.bind('<<ComboboxSelected>>', lambda _: self.save_settings())
        self.folder_label = ttk.Label(settings, text='Folder penyimpanan', style='SurfaceMuted.TLabel')
        self.folder_label.grid(row=2, column=0, columnspan=2, sticky='w', pady=self.space(9, 5))
        destination = ttk.Frame(settings, style='Surface.TFrame')
        self.destination = destination
        destination.grid(row=3, column=0, columnspan=2, sticky='ew')
        destination.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(destination, textvariable=self.folder, width=1, font=self.body_font)
        self.folder_entry.grid(row=0, column=0, sticky='ew')
        self.folder_entry.bind('<FocusOut>', lambda _: self.save_settings())
        self.folder_entry.bind('<Return>', lambda _: self.save_settings())
        self.button(destination, 'Pilih', 'folder', self.browse).grid(row=0, column=1, padx=self.space(6, 0))
        self.playlist_toggle = ttk.Checkbutton(settings, text='  Sertakan seluruh playlist', variable=self.whole, style='Surface.TCheckbutton')
        self.playlist_toggle.grid(row=4, column=0, columnspan=2, sticky='w', pady=self.space(10, 0))
        self.input_label = ttk.Label(composer, textvariable=self.input_status, style='SurfaceMuted.TLabel', wraplength=self.u(900))
        self.input_label.grid(row=1, column=0, columnspan=3, sticky='ew', pady=self.space(13, 0))

        queue_border = tk.Frame(panel, bg=LINE)
        queue_border.grid(row=2, column=0, sticky='nsew')
        queue = ttk.Frame(queue_border, style='Surface.TFrame')
        queue.pack(fill='both', expand=True, padx=self.u(1), pady=self.u(1))
        queue.columnconfigure(0, weight=1)
        queue.rowconfigure(3, weight=1)
        queue_header = ttk.Frame(queue, style='Surface.TFrame', padding=self.space(17, 15))
        queue_header.grid(row=0, column=0, sticky='ew')
        title = ttk.Frame(queue_header, style='Surface.TFrame')
        title.pack(side='left')
        self.queue_title = title
        self.queue_actions = ttk.Frame(queue_header, style='Surface.TFrame')
        self.queue_actions.pack(side='right')
        self.queue_heading = tk.StringVar(value='Antrean unduhan')
        ttk.Label(title, textvariable=self.queue_heading, style='Section.TLabel').pack(anchor='w')
        self.queue_summary_label = ttk.Label(title, textvariable=self.summary, style='SurfaceMuted.TLabel')
        self.queue_summary_label.pack(anchor='w', pady=self.space(4, 0))
        self.cancel_button = self.button(self.queue_actions, 'Batalkan', 'cancel', self.controller.cancel_active, style='Quiet.TButton')
        self.cancel_button.pack(side='right')
        self.pause_button = self.button(self.queue_actions, 'Jeda', 'pause', self.controller.pause, style='Quiet.TButton')
        self.pause_button.pack(side='right', padx=self.space(6, 0))
        self.start_button = self.button(self.queue_actions, 'Mulai unduh', 'download', self.start, style='Accent.TButton')
        self.start_button.pack(side='right', padx=self.space(12, 6))
        tk.Frame(queue, bg=LINE, height=1).grid(row=1, column=0, sticky='ew')
        toolbar = ttk.Frame(queue, style='Surface.TFrame', padding=self.space(10, 6))
        toolbar.grid(row=2, column=0, sticky='ew')
        self.select_all_button = self.button(toolbar, 'Pilih semua', 'check', lambda: self.controller.select_all(True), style='Quiet.TButton')
        self.select_all_button.pack(side='left')
        self.clear_selection_button = self.button(toolbar, 'Kosongkan pilihan', 'clear', lambda: self.controller.select_all(False), style='Quiet.TButton')
        self.clear_selection_button.pack(side='left', padx=self.u(3))
        self.remove_button = self.button(toolbar, 'Hapus', 'trash', self.controller.remove_selected, style='Quiet.TButton')
        self.remove_button.pack(side='right')
        self.retry_button = self.button(toolbar, 'Coba lagi', 'retry', self.controller.retry_failed, style='Quiet.TButton')
        self.retry_button.pack(side='right', padx=self.u(6))

        self.table = ttk.Frame(queue, style='Surface.TFrame')
        self.table.grid(row=3, column=0, sticky='nsew')
        self.table.rowconfigure(0, weight=1)
        self.table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(self.table, columns=('pick', 'title', 'quality', 'format', 'progress', 'status'), show='headings', selectmode='browse', height=6)
        for key, title, width, stretch in [('pick', 'Pilih', 48, False), ('title', 'Video', 290, True),
                                          ('quality', 'Kualitas', 95, False), ('format', 'Format', 75, False),
                                          ('progress', 'Progres', 85, False), ('status', 'Status', 130, False)]:
            self.tree.heading(key, text=title, anchor='w' if key=='title' else 'center')
            self.tree.column(key, width=max(self.u(width), tkfont.Font(self, font=self.body_font).measure(title) + self.u(28)), minwidth=self.u(width if key != 'title' else 200), stretch=stretch, anchor='w' if key=='title' else 'center')
        self.tree.tag_configure('failed', foreground='#b13d54', background='#fff6f8')
        self.tree.tag_configure('done', foreground='#34705c')
        self.tree.tag_configure('active', foreground='#165798', background='#eaf4ff')
        self.tree.tag_configure('pending', foreground='#526b84')
        self.tree.tag_configure('cancelled', foreground=MUTED)
        self.table_scroll = ttk.Scrollbar(self.table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.table_scroll.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.table_scroll.grid(row=0, column=1, sticky='ns')
        self.tree.bind('<ButtonRelease-1>', self.row_click)
        self.tree.bind('<space>', self.toggle_row)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.render_detail())
        self.tree.bind('<Double-1>', self.open_selected)
        self.empty_state = ttk.Frame(self.table, style='Surface.TFrame', padding=self.space(24, 15))
        ttk.Label(self.empty_state, image=self.empty_image, style='Surface.TLabel').pack()
        ttk.Label(self.empty_state, text='Antrean masih kosong', style='Section.TLabel').pack(pady=self.space(10, 4))
        self.empty_hint = ttk.Label(self.empty_state, text='Tempel tautan di atas, lalu tambahkan ke antrean.', style='SurfaceMuted.TLabel')
        self.empty_hint.pack()

        pagination = ttk.Frame(queue, style='Surface.TFrame', padding=self.space(12, 9))
        pagination.grid(row=4, column=0, sticky='ew')
        self.details_button = self.button(pagination, 'Detail & log', 'list', self.toggle_details, style='Quiet.TButton')
        self.details_button.pack(side='left')
        self.next_button = self.button(pagination, '', 'chevron-right', lambda: self.turn_page(1), style='Quiet.TButton')
        self.next_button.pack(side='right')
        ttk.Label(pagination, textvariable=self.page_text, style='SurfaceMuted.TLabel').pack(side='right', padx=self.u(9))
        self.previous_button = self.button(pagination, '', 'chevron-left', lambda: self.turn_page(-1), style='Quiet.TButton')
        self.previous_button.pack(side='right')
        self.detail = tk.Text(self.table, height=5, wrap='word', font=('DejaVu Sans Mono', 11), bg='#f8fafd', fg=INK,
                              relief='flat', borderwidth=0, padx=self.u(16), pady=self.u(14), state='disabled', selectbackground='#d3e7ff')

        footer = ttk.Frame(panel, padding=self.space(0, 14, 0, 0))
        self.footer = footer
        footer.grid(row=3, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.grid(row=0, column=0, sticky='ew', pady=self.space(0, 10))
        self.status_label = ttk.Label(footer, textvariable=self.status, style='Muted.TLabel', wraplength=self.u(950))
        self.status_label.grid(row=1, column=0, sticky='w')
        self.transfer_label = ttk.Label(footer, textvariable=self.transfer, style='Muted.TLabel')
        self.transfer_label.grid(row=2, column=0, sticky='w', pady=self.space(4, 0))
        self.wrap_groups = [
            (self.queue_actions, [self.start_button, self.pause_button, self.cancel_button]),
            (actions, [self.add_button, self.check_button, self.stop_import]),
            (toolbar, [self.select_all_button, self.clear_selection_button, self.retry_button, self.remove_button]),
        ]
        self.queue_menu = tk.Menu(self, tearoff=False, font=self.body_font)
        self.queue_menu.add_command(label='Jeda', command=self.controller.pause)
        self.queue_menu.add_command(label='Batalkan unduhan', command=self.controller.cancel_active)
        self.queue_more = ttk.Menubutton(self.queue_actions, text='Lainnya', menu=self.queue_menu, style='TMenubutton')
        self.selection_menu = tk.Menu(self, tearoff=False, font=self.body_font)
        self.selection_menu.add_command(label='Pilih semua', command=lambda: self.controller.select_all(True))
        self.selection_menu.add_command(label='Kosongkan pilihan', command=lambda: self.controller.select_all(False))
        self.selection_menu.add_command(label='Coba lagi', command=self.controller.retry_failed)
        self.selection_menu.add_command(label='Hapus pilihan', command=self.controller.remove_selected)
        self.selection_more = ttk.Menubutton(toolbar, text='Kelola antrean', menu=self.selection_menu)
        for parent, buttons in self.wrap_groups:
            for button in buttons:
                button.pack_forget()
        self.bind('<Configure>', self.schedule_layout, add='+')
        self.after_idle(self.layout_ui)

    def schedule_layout(self, event=None):
        if self.layout_pending is None:
            self.layout_pending = self.after_idle(self.layout_ui)

    def layout_ui(self):
        self.layout_pending = None
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1:
            return
        signature = (width, height, self.composer_left.winfo_width(),
                     self.table.winfo_width(), self.table.winfo_height(),
                     *(parent.winfo_width() for parent, _ in self.wrap_groups))
        if signature == self.layout_signature:
            return
        self.layout_signature = signature
        content_width = max(self.u(200), width - self.u(80))
        if self.composer_breakpoint is None:
            left_width = sum(b.winfo_reqwidth() + self.u(6) for b in
                             (self.add_button, self.check_button, self.stop_import))
            self.composer_breakpoint = max(self.u(420), left_width) + self.settings_panel.winfo_reqwidth() + self.u(60)
        compact = content_width < self.composer_breakpoint
        short = height < self.u(820)
        dense = compact or short
        self.compact = compact
        self.panel.configure(padding=self.space(12, 8, 12, 8) if short else self.space(20, 18, 20, 16))
        self.composer.configure(padding=self.u(8 if short else 18))
        self.composer.master.grid_configure(pady=self.space(0, 8 if short else 20))
        self.brand.master.grid_configure(pady=self.space(0, 8 if short else 22))
        self.links.configure(height=1 if short else 3)
        for widget in (self.link_label_row, self.link_hint):
            if short:
                widget.grid_remove()
            else:
                widget.grid()
        if short:
            self.brand_hint.pack_forget()
            self.queue_summary_label.pack_forget()
            self.transfer_label.grid_remove()
        else:
            self.brand_hint.pack(anchor='w', pady=self.space(3, 0))
            self.queue_summary_label.pack(anchor='w', pady=self.space(4, 0))
            self.transfer_label.grid()
        if compact:
            self.composer_divider.grid_remove()
            self.composer_left.grid_configure(row=0, column=0, columnspan=3, padx=0)
            self.settings_panel.grid_configure(row=1, column=0, columnspan=3, pady=self.space(6, 0))
            self.settings_panel.columnconfigure(0, weight=0)
            self.settings_panel.columnconfigure(1, weight=1)
            self.settings_heading.grid_remove()
            self.quality_label.grid_configure(row=0, column=0, columnspan=1, pady=0)
            self.quality.grid_configure(row=1, column=0, sticky='w', padx=self.space(0, 10), pady=0)
            self.folder_label.grid_configure(row=0, column=1, columnspan=1, pady=0)
            self.destination.grid_configure(row=1, column=1, columnspan=1)
            self.playlist_toggle.grid_configure(row=2, pady=self.space(4, 0))
            self.input_label.grid_configure(row=2, pady=self.space(4, 0))
        else:
            self.composer_left.grid_configure(row=0, column=0, columnspan=1, padx=self.space(0, 20))
            self.composer_divider.grid()
            self.settings_panel.grid_configure(row=0, column=2, columnspan=1, pady=0)
            self.settings_panel.columnconfigure(0, weight=1)
            self.settings_panel.columnconfigure(1, weight=0)
            self.settings_heading.grid()
            self.quality_label.grid_configure(row=1, column=0, columnspan=1, pady=self.space(0, 5))
            self.quality.grid_configure(row=1, column=1, sticky='e', padx=0, pady=self.space(0, 5))
            self.folder_label.grid_configure(row=2, column=0, columnspan=2, pady=self.space(9, 5))
            self.destination.grid_configure(row=3, column=0, columnspan=2)
            self.playlist_toggle.grid_configure(row=4, pady=self.space(10, 0))
            self.input_label.grid_configure(row=1, pady=self.space(6 if short else 13, 0))
        self.queue_title.pack_configure(side='left', fill='none')
        self.queue_actions.pack_configure(side='right', pady=0)
        for parent, buttons in self.wrap_groups:
            for button in buttons:
                button.grid_remove()
        self.queue_more.grid_remove()
        self.selection_more.grid_remove()
        self.compact_paste.grid_remove()
        input_buttons = [self.add_button, self.check_button, self.stop_import]
        if short:
            input_buttons.insert(0, self.compact_paste)
        groups = [(self.wrap_groups[1][0], input_buttons)]
        if dense:
            groups.append((self.queue_actions, [self.start_button, self.queue_more]))
            groups.append((self.wrap_groups[2][0], [self.selection_more]))
        else:
            groups.extend((self.wrap_groups[0], self.wrap_groups[2]))
        for parent, buttons in groups:
            available = max(self.u(200), parent.winfo_width())
            row = column = used = 0
            for button in buttons:
                needed = button.winfo_reqwidth() + self.u(6)
                if column and used + needed > available:
                    row, column, used = row + 1, 0, 0
                button.grid(row=row, column=column, sticky='w', padx=self.space(0, 6), pady=self.u(2))
                used += needed
                column += 1
        for label in (self.input_label, self.status_label):
            label.configure(wraplength=0 if short else content_width, width=1)
        self.input_label.grid_configure(sticky='ew')
        self.status_label.grid_configure(sticky='ew')
        self.empty_hint.configure(wraplength=content_width)
        self.link_hint.configure(wraplength=max(self.u(180), self.composer_left.winfo_width()))
        brand_width = width - self.u(130) - self.open_folder_button.winfo_reqwidth()
        self.brand_title.configure(wraplength=max(self.u(180), brand_width),
                                   font=(self.font_family, 16 if dense else 22, 'bold'))
        self.brand_hint.configure(wraplength=max(self.u(180), brand_width))
        # Keep all table columns inside the queue; the title takes remaining width.
        table_width = max(1, self.table.winfo_width() - self.table_scroll.winfo_reqwidth())
        fields = [('pick', 48), ('quality', 90), ('format', 70), ('progress', 80), ('status', 125)]
        if compact:
            self.tree.configure(displaycolumns=('pick', 'title', 'progress', 'status'))
            fields = [('pick', 48), ('progress', 80), ('status', 125)]
        else:
            self.tree.configure(displaycolumns=('pick', 'title', 'quality', 'format', 'progress', 'status'))
        for key, size in fields:
            self.tree.column(key, width=self.u(size), minwidth=self.u(size), stretch=False)
        title_width = max(self.u(100), table_width - sum(self.u(size) for _, size in fields))
        self.tree.column('title', width=title_width, minwidth=self.u(100), stretch=True)
        empty_height = self.empty_state.winfo_reqheight()
        if self.table.winfo_height() < empty_height + self.u(50):
            self.empty_state.place_forget()
        elif not self.controller.jobs and not self.detail_visible:
            self.empty_state.place(relx=0.5, rely=0.56, anchor='center')

    def paste_links(self):
        try:
            value = self.clipboard_get().strip()
        except tk.TclError:
            self.input_status.set('Clipboard kosong. Salin tautan video atau playlist terlebih dahulu.')
            return
        if not value:
            self.input_status.set('Clipboard kosong. Salin tautan video atau playlist terlebih dahulu.')
            return
        current = self.links.get('1.0', 'end-1c')
        self.links.insert('end', ('\n' if current and not current.endswith('\n') else '') + value)
        self.links.focus_set()
        self.input_status.set('Tautan ditempel. Klik Tambah antrean untuk melanjutkan.')

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
            open_path(path)
        except OSError as exc:
            self.mailbox.post('log', f'Folder belum tersedia: {exc}')
            self.input_status.set('Folder belum tersedia; akan dibuat saat download dimulai.')

    def open_selected(self, _=None):
        selected = self.tree.selection()
        job = self.controller.get(selected[0]) if selected else None
        if job and job.result and Path(job.result).is_file():
            try:
                open_path(job.result)
            except OSError as exc:
                self.mailbox.post('log', str(exc))

    def toggle_details(self):
        self.detail_visible = not self.detail_visible
        if self.detail_visible:
            self.empty_state.place_forget()
            self.tree.grid_remove()
            self.table_scroll.grid_remove()
            self.detail.grid(row=0, column=0, columnspan=2, sticky='nsew')
            self.details_button.configure(text='  Kembali ke antrean')
            self.render_detail()
        else:
            self.detail.grid_remove()
            self.tree.grid()
            self.table_scroll.grid()
            self.details_button.configure(text='  Detail & log')
            self.render()

    def render_detail(self):
        if not self.detail_visible:
            return
        selected = self.tree.selection()
        job = self.controller.get(selected[0]) if selected else None
        heading = (f'{job.title}\n{job.url}\n'
                   f"Kualitas: {str(job.height) + 'p' if job.height else '≤ ' + str(job.cap) + 'p'} · Format: {job.ext.upper() or 'Auto'}\n"
                   f'{job.error or job.result or job.stage}\n\n') if job else ''
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
        self.queue_heading.set(f'Antrean unduhan ({count})' if count else 'Antrean unduhan')
        self.summary.set(f"{counts['pending']} menunggu    {counts['done']} selesai    {counts['failed']} gagal")
        if (not count and not self.detail_visible
                and self.table.winfo_height() >= self.empty_state.winfo_reqheight() + self.u(50)):
            self.empty_state.place(relx=0.5, rely=0.56, anchor='center')
        else:
            self.empty_state.place_forget()
        for button in (self.select_all_button, self.clear_selection_button, self.remove_button):
            button.configure(state='normal' if count and not self.closing else 'disabled')
        self.retry_button.configure(state='normal' if counts['failed'] + counts['cancelled'] and not self.closing else 'disabled')
        self.previous_button.configure(state='normal' if self.page else 'disabled')
        self.next_button.configure(state='normal' if (self.page + 1) * PAGE_SIZE < count else 'disabled')
        self.cancel_button.configure(state='normal' if active and not self.closing else 'disabled')
        self.pause_button.configure(state='normal' if running and not self.closing else 'disabled')
        for index, button in enumerate((self.pause_button, self.cancel_button)):
            self.queue_menu.entryconfigure(index, state=str(button.cget('state')))
        for index, button in enumerate((self.select_all_button, self.clear_selection_button, self.retry_button, self.remove_button)):
            self.selection_menu.entryconfigure(index, state=str(button.cget('state')))
        self.start_button.configure(state='disabled' if running or self.closing or not (counts['pending'] or self.controller.imports) else 'normal')
        if self.closing:
            self.status.set('Menghentikan proses dan menyimpan antrean. Tunggu permintaan jaringan selesai...')
        elif active:
            paused = ' · jeda setelah video ini' if not running else ''
            self.status.set(f'{active.title} · {active.stage or LABELS[active.status]}{paused}')
            speed = f'{active.speed / 1048576:.2f} MB/detik' if active.speed else '— MB/detik'
            eta = f'{int(active.eta)} detik' if active.eta is not None else '—'
            self.transfer.set(f'{speed}   ·   ETA stream {eta}   ·   1 video aktif')
        elif self.controller.notice:
            self.status.set(self.controller.notice)
            self.transfer.set('Jeda antarvideo.' if self.controller.waiting else 'Antrean tersimpan. Lanjutkan secara manual setelah pembatasan mereda.')
        else:
            self.status.set('Menunggu tautan berikutnya.' if running else 'Siap. Pilih video, lalu klik Mulai unduh.' if count else 'Siap menerima tautan video atau playlist.')
            self.transfer.set('Belum ada unduhan aktif.')
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

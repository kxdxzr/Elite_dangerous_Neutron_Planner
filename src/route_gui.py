"""Local ship favourites and Spansh online, ordered multi-leg exact routing."""
import json
import csv
import queue
import threading
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk as native_ttk

from destination_favorites import DestinationFavorites, clean_text
from localized_tk import ttk, messagebox, Toplevel
from result_copy import copy_result
from result_format import format_ly
from search_progress import SearchProgress
from route_history import RouteHistory, build_key, request_key, find_complete, validate_leg_overrides
from route_position import RoutePosition
import route_ship
import route_tool as tool
import journal_location
import journal_ship


def open_window(app, window=None):
    win = window if window is not None else Toplevel(app.root)
    win.title('中子星跳跃规划器')
    win.geometry('1400x850')
    store = tool.Favorites()
    tr = app.localizer.tr
    selected = tk.StringVar(win)
    source, destination, waypoint = (tk.StringVar(win, value=v) for v in ('Sol', '', ''))
    cargo, reserve = tk.StringVar(win, value='0'), tk.StringVar(win, value='0')
    algorithm, injection = tk.StringVar(win, value='优先少跳'), tk.StringVar(win, value='不使用')
    algorithms = {'优先少跳': 'optimistic', '优先计算速度': 'pessimistic'}
    injections = {'不使用': 'never', '仅在需要时': 'required', '始终使用': 'always'}
    flags = {key: tk.BooleanVar(win, value=value) for key, value in (
        ('supercharge', True), ('already_supercharged', False), ('exclude_secondary', False), ('refuel_every_scoopable', False))}
    stop, events = threading.Event(), queue.Queue()
    state = {'busy': False, 'info': None, 'points': [], 'result_key': None, 'pending': None, 'cached_at': None}
    map_window = None
    history_store = RouteHistory()
    history = []
    preview = {'generation': 0, 'identity': None, 'params': None, 'error': '', 'fsds': None}
    preview_lock, preview_closed = threading.Lock(), threading.Event()

    # One document: settings, actions and results share a single page scrollbar.
    page = ttk.Frame(win)
    page.pack(fill='both', expand=True)
    canvas = tk.Canvas(page, height=650, highlightthickness=0, yscrollincrement=24)
    scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    content = ttk.Frame(canvas)
    content_id = canvas.create_window((0, 0), window=content, anchor='nw')
    content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(content_id, width=e.width))
    form = ttk.Frame(content)
    form.pack(fill='x')
    result_area = ttk.Frame(content)
    result_area.pack(fill='x', pady=(8, 16))
    wheel_tag = f'RoutePageWheel{id(win)}'
    wheel_remainder = 0.0

    def scroll_page(event):
        nonlocal wheel_remainder
        if getattr(event, 'num', None) in (4, 5):
            steps = -3 if event.num == 4 else 3
        else:
            delta = getattr(event, 'delta', 0)
            if not delta:
                return
            wheel_remainder -= delta / 120 * 3
            steps = int(wheel_remainder)
            wheel_remainder -= steps
        if steps:
            if getattr(event, 'state', 0) & 1 and isinstance(event.widget, ttk.Treeview):
                event.widget.xview_scroll(steps, 'units')
            else:
                canvas.yview_scroll(steps, 'units')
        return 'break'

    for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
        win.bind_class(wheel_tag, sequence, scroll_page)
    win.settings_canvas = win.page_canvas = canvas
    win.page_content, win.page_form, win.page_results = content, form, result_area
    win.scroll_page = scroll_page

    ships = ttk.LabelFrame(form, text='舰船配置收藏', padding=6)
    ships.pack(fill='x', padx=8, pady=6)
    chooser = ttk.Combobox(ships, textvariable=selected, state='readonly', width=52, height=12)
    chooser.pack(fill='x', padx=4, pady=4)
    ship_actions = ttk.Frame(ships)
    ship_actions.pack(fill='x')

    def error(exc):
        messagebox.showerror('操作失败', str(exc), parent=win)

    def reload_favorites(name=None):
        try:
            names = sorted(store.load(), key=str.casefold)
            chooser.configure(values=names)
            selected.set(name if name in names else names[0] if names else '')
        except (OSError, ValueError, TypeError) as exc:
            chooser.configure(values=[])
            selected.set('')
            error(exc)

    def editor(existing=None, imported=None):
        dialog = Toplevel(win)
        dialog.title('编辑舰船配置')
        width = min(850, max(480, dialog.winfo_screenwidth() - 80))
        height = min(570, max(320, dialog.winfo_screenheight() - 120))
        dialog.geometry(f'{width}x{height}')
        dialog.minsize(480, 320)
        dialog.columnconfigure(0, weight=1)
        # Only the JSON area yields space; actions keep their requested height.
        dialog.rowconfigure(2, weight=1)
        name = tk.StringVar(dialog, value=existing or '')
        header = ttk.Frame(dialog, padding=6)
        header.grid(row=0, column=0, sticky='ew')
        ttk.Label(header, text='收藏名称').pack(side='left')
        ttk.Entry(header, textvariable=name, width=36).pack(side='left', fill='x', expand=True, padx=6)
        hint = ttk.Label(dialog, text='粘贴 Coriolis 配船 JSON 或 EDSY SLEF；不接受网页链接。', wraplength=800)
        hint.grid(row=1, column=0, sticky='ew', padx=8)
        hint.bind('<Configure>', lambda event: hint.configure(wraplength=max(100, event.width)))
        body = ttk.Frame(dialog)
        body.grid(row=2, column=0, sticky='nsew', padx=8, pady=6)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        text = tk.Text(body, wrap='none', undo=True, width=1, height=10)
        text.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(body, orient='vertical', command=text.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(body, orient='horizontal', command=text.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        if imported is not None:
            text.insert('1.0', imported.raw)
            identity = route_ship.ship_identity(imported.raw)
            name.set(identity['name'] or identity['model'])
            hint.configure(text=(tr('本地日志配船，请核对后保存；未自动覆盖收藏。') + '\n' +
                                 imported.timestamp + ' | ' + imported.filename))
        if existing:
            try:
                text.insert('1.0', store.load()[existing])
            except (OSError, ValueError, KeyError) as exc:
                error(exc)
                dialog.destroy()
                return

        def import_json():
            path = filedialog.askopenfilename(parent=dialog, filetypes=[('JSON', '*.json'), ('All', '*.*')])
            if path:
                try:
                    with open(path, encoding='utf-8-sig') as file:
                        raw = file.read(route_ship.MAX_BUILD_BYTES + 1)
                    route_ship.decode_build(raw)
                    text.delete('1.0', 'end')
                    text.insert('1.0', raw)
                except (OSError, ValueError) as exc:
                    error(exc)

        def save():
            try:
                raw = text.get('1.0', 'end-1c')
                route_ship.decode_build(raw)
                target = name.get().strip()
                names = store.load()
                duplicate = next((n for n in names if n.casefold() == target.casefold()), None)
                if duplicate is not None and not messagebox.askyesno('确认', '覆盖同名舰船配置？', parent=dialog):
                    return
                # Save-as is deliberate: renaming has its own explicit action.
                store.put(target, raw, replace=duplicate is not None)
                reload_favorites(target)
                dialog.destroy()
            except (OSError, ValueError, TypeError) as exc:
                error(exc)

        buttons = ttk.Frame(dialog, padding=6)
        buttons.grid(row=3, column=0, sticky='ew')
        ttk.Button(buttons, text='导入 JSON 文件', command=import_json).pack(side='left')
        ttk.Button(buttons, text='保存舰船配置', command=save).pack(side='right')
        dialog.json_text, dialog.name_variable, dialog.save_build = text, name, save
        dialog.action_frame, dialog.json_frame = buttons, body
        return dialog

    def rename():
        if not selected.get():
            return
        name = simpledialog.askstring(tr('重命名'), tr('收藏名称'), initialvalue=selected.get(), parent=win)
        if name is not None:
            try:
                store.rename(selected.get(), name)
                reload_favorites(name.strip())
            except (OSError, ValueError) as exc:
                error(exc)

    def delete():
        if selected.get() and messagebox.askyesno('确认', '删除所选舰船配置？', parent=win):
            try:
                store.delete(selected.get())
                reload_favorites()
            except (OSError, ValueError) as exc:
                error(exc)

    for label, command in (('新增舰船配置', editor), ('编辑舰船配置', lambda: editor(selected.get()) if selected.get() else editor()),
                           ('重命名', rename), ('删除收藏', delete)):
        ttk.Button(ship_actions, text=label, command=command).pack(side='left', padx=4)
    ship_reading = {'busy': False}

    def history_picker(report):
        dialog = Toplevel(win)
        dialog.title('选择历史配船')
        dialog.geometry('1000x520')
        dialog.minsize(650, 350)
        ttk.Label(dialog, text='历史配船可能过时或已出售，不代表当前船库；选择一艘后核对并保存，不会自动收藏。',
                  wraplength=950).pack(fill='x', padx=8, pady=8)
        ttk.Label(dialog, text=(tr('扫描结果') + f': {len(report.ships)} | ' +
                  tr('跳过无效或无法确认身份的记录') + f': {report.skipped}' +
                  (' | ' + tr('已达扫描上限，列表可能不完整。') if report.limited else '')),
                  wraplength=950).pack(fill='x', padx=8)
        commanders = {}
        for ship in report.ships:
            commanders.setdefault(ship.commander_id, ship.commander_name)
        choices = {f'{index + 1}. {name or tr("情况未知")}': ident
                   for index, (ident, name) in enumerate(commanders.items())}
        selected_commander = tk.StringVar(dialog, value=next(iter(choices), ''))
        row = ttk.Frame(dialog, padding=8)
        row.pack(fill='x')
        ttk.Label(row, text='指挥官').pack(side='left')
        combo = native_ttk.Combobox(row, textvariable=selected_commander, values=list(choices),
                                   state='readonly', width=45)
        combo.pack(side='left', padx=8)
        body = ttk.Frame(dialog, padding=8)
        body.pack(fill='both', expand=True)
        table = ttk.Treeview(body, columns=('model', 'name', 'ident', 'id', 'time'),
                             show='headings', selectmode='browse')
        for column, label in (('model', '船型'), ('name', '舰船名称'), ('ident', '舰船识别码'),
                              ('id', '舰船编号'), ('time', '日志时间')):
            table.heading(column, text=label)
            table.column(column, width=200 if column == 'time' else 150, minwidth=80)
        scroll = ttk.Scrollbar(body, orient='vertical', command=table.yview)
        horizontal = ttk.Scrollbar(body, orient='horizontal', command=table.xview)
        table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')

        def populate(*_):
            table.delete(*table.get_children())
            commander = choices.get(selected_commander.get())
            for index, ship in enumerate(report.ships):
                if ship.commander_id == commander:
                    identity = route_ship.ship_identity(ship.snapshot.raw)
                    table.insert('', 'end', iid=str(index), values=(identity['model'], identity['name'],
                                 identity['ident'], ship.ship_id, ship.snapshot.timestamp))

        combo.bind('<<ComboboxSelected>>', populate)

        def choose():
            selection = table.selection()
            if len(selection) == 1:
                snapshot = report.ships[int(selection[0])].snapshot
                dialog.destroy()
                editor(imported=snapshot)

        buttons = ttk.Frame(dialog, padding=8)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='查看所选配船并收藏', command=choose).pack(side='right')
        populate()
        dialog.ship_table, dialog.commander_choice = table, selected_commander
        dialog.commander_combo, dialog.choose_ship = combo, choose
        return dialog

    def read_ship(history=False):
        if ship_reading['busy']:
            return
        directory = app.journal_directory or journal_location.default_directory()
        ship_reading['busy'] = True
        ship_read_button.configure(state='disabled')
        ship_history_button.configure(state='disabled')

        def worker():
            try:
                result = (journal_ship.read_ship_history(directory, preview_closed) if history else
                          journal_ship.read_current_ship(directory))
                if not preview_closed.is_set():
                    events.put(('journal_ship', (result, None)))
            except (OSError, ValueError, TypeError) as exc:
                if not preview_closed.is_set():
                    events.put(('journal_ship', (None, str(exc))))
        threading.Thread(target=worker, daemon=True, name='journal-ship').start()

    ship_read_button = ttk.Button(ship_actions, text='读取当前配船', command=read_ship)
    ship_read_button.pack(side='left', padx=4)
    ship_history_button = ttk.Button(ship_actions, text='读取历史配船', command=lambda: read_ship(history=True))
    ship_history_button.pack(side='left', padx=4)
    ttk.Label(ships, text='仅点击时读取最新日志会话的配船，不依赖 EDMC；请先在游戏中切换到目标舰船。日志目录可在起点区域选择。',
              wraplength=1300, style='Muted.TLabel').pack(fill='x', padx=4, pady=4)
    ttk.Label(form, text='收藏仅保存在本地；开始规划后，舰船配置和航点将发送至 Spansh。首次解析需要联网获取 FSD 数据。',
              wraplength=1360, style='Muted.TLabel').pack(fill='x', padx=8)

    summary = ttk.LabelFrame(form, text='所选舰船与跳跃属性', padding=6)
    summary.pack(fill='x', padx=8, pady=4)
    identity_text, range_text = (tk.StringVar(win) for _ in range(2))
    for variable in (identity_text, range_text):
        ttk.Label(summary, textvariable=variable, wraplength=1350).pack(fill='x')
    ttk.Label(summary, text='理论单跳：主油箱与备用油箱满油，使用当前货物质量，不含注入；不代表当前位置可中子增压，实际路线受储备燃油等设置限制。',
              style='Muted.TLabel', wraplength=1350).pack(fill='x')

    def render_preview():
        identity = preview['identity']
        if not identity:
            identity_text.set(tr('请先选择舰船配置'))
        else:
            identity_text.set('   |   '.join(f"{tr(label)}: {identity[key] or tr('情况未知')}" for label, key in
                                           (('船型', 'model'), ('舰船名称', 'name'))))
        params = preview['params']
        if preview['error']:
            range_text.set(tr('无法计算跳跃属性') + ': ' + tr(preview['error']))
        elif params is None:
            range_text.set(tr('正在读取跳跃属性…') if identity else '')
        else:
            try:
                values = route_ship.jump_attributes(params, cargo.get())
                range_text.set(f"{tr('普通满油跳距')}: {format_ly(values['normal_range'])} ly   |   "
                               f"{tr('中子增压后跳距')}: {format_ly(values['neutron_range'])} ly")
            except (ValueError, TypeError, KeyError) as exc:
                range_text.set(tr('无法计算跳跃属性') + ': ' + tr(str(exc)))

    def refresh_preview(*_):
        preview['generation'] += 1
        generation = preview['generation']
        preview.update(identity=None, params=None, error='')
        try:
            raw = store.load().get(selected.get())
            if raw is not None:
                preview['identity'] = route_ship.ship_identity(raw)
        except (OSError, ValueError, TypeError) as exc:
            preview['error'] = str(exc)
            raw = None
        render_preview()
        if raw is None:
            return

        def worker():
            try:
                # Share one catalogue load and ignore obsolete queued selections.
                with preview_lock:
                    if preview_closed.is_set() or generation != preview['generation']:
                        return
                    if preview['fsds'] is None:
                        preview['fsds'] = route_ship.catalog(tool.http_json)
                    fsds = preview['fsds']
                params = route_ship.parse_ship(raw, fsds)
                events.put(('preview', (generation, params, '')))
            except Exception as exc:
                events.put(('preview', (generation, None, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    selected_trace = selected.trace_add('write', refresh_preview)
    cargo_trace = cargo.trace_add('write', lambda *_: render_preview())
    app.localizer.register(render_preview)

    endpoints = ttk.Frame(form, padding=8)
    endpoints.pack(fill='x')
    from suggestion_ui import attach_system_suggest
    endpoints.columnconfigure(1, weight=1)
    for row, (label, variable) in enumerate((('起点星系', source), ('终点星系', destination))):
        ttk.Label(endpoints, text=label).grid(row=row, column=0, sticky='w')
        box = ttk.Combobox(endpoints, textvariable=variable, width=52, height=12)
        box.grid(row=row, column=1, sticky='ew', padx=8, pady=5)
        suggestion = attach_system_suggest(box, variable)
        if variable is source:
            set_source_system = suggestion['set_value']

    journal_status = tk.StringVar(win, value='点击读取本地日志作为起点；持续跟随需在结果区单独开启。')
    journal_state = {'busy': False, 'source': None, 'location': None}
    def render_journal():
        location = journal_state['location']
        if location is not None:
            journal_status.set(f"{tr('日志位置（非实时）')}: {location.system} | {location.timestamp}")
    app.localizer.register(render_journal)
    journal_actions = ttk.Frame(endpoints)
    journal_actions.grid(row=2, column=0, columnspan=2, sticky='ew', pady=4)

    def read_journal(choose=False):
        if journal_state['busy']:
            return
        directory = app.journal_directory or journal_location.default_directory()
        if choose:
            directory = filedialog.askdirectory(parent=win, title=tr('选择游戏日志文件夹'),
                                                initialdir=directory, mustexist=True)
            if not directory:
                return
            app.journal_directory = directory
            if follow_enabled.get():
                restart_follow()
        journal_state.update(busy=True, source=source.get(), location=None)
        for button in journal_buttons:
            button.configure(state='disabled')
        journal_status.set('正在读取本地游戏日志…')

        def worker():
            try:
                result = journal_location.read_current_system(directory)
                events.put(('journal', (result, None)))
            except (OSError, ValueError) as exc:
                events.put(('journal', (None, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    journal_buttons = []
    for label, command in (('使用当前星系', read_journal), ('选择游戏日志文件夹', lambda: read_journal(choose=True))):
        button = ttk.Button(journal_actions, text=label, command=command)
        button.pack(side='left', padx=4)
        journal_buttons.append(button)
    ttk.Label(endpoints, textvariable=journal_status, style='Muted.TLabel', wraplength=1000).grid(
        row=3, column=0, columnspan=2, sticky='ew')

    destination_store = DestinationFavorites()
    favorite_destination = tk.StringVar(win)
    favorites_frame = ttk.LabelFrame(form, text='目的地收藏', padding=6)
    favorites_frame.pack(fill='x', padx=8, pady=4)
    # User-defined names are data, not translation catalogue keys.
    destination_chooser = native_ttk.Combobox(favorites_frame, textvariable=favorite_destination,
                                             state='readonly', width=52, height=12)
    destination_chooser.pack(fill='x', padx=4, pady=4)
    destination_actions = ttk.Frame(favorites_frame)
    destination_actions.pack(fill='x')

    def reload_destinations(name=None):
        try:
            names = sorted(destination_store.load(), key=str.casefold)
            destination_chooser.configure(values=names)
            favorite_destination.set(name if name in names else names[0] if names else '')
        except (OSError, ValueError, TypeError) as exc:
            destination_chooser.configure(values=[])
            favorite_destination.set('')
            error(exc)

    def save_destination():
        try:
            system = clean_text(destination.get())
            name = simpledialog.askstring(tr('收藏当前终点'), tr('收藏名称'), initialvalue=system, parent=win)
            if name is not None:
                destination_store.put(name, system)
                reload_destinations(name.strip())
        except (OSError, ValueError, TypeError) as exc:
            error(exc)

    def use_destination():
        if favorite_destination.get():
            try:
                destination.set(destination_store.load()[favorite_destination.get()])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                error(exc)

    def rename_destination():
        old = favorite_destination.get()
        if not old:
            return
        name = simpledialog.askstring(tr('重命名目的地'), tr('收藏名称'), initialvalue=old, parent=win)
        if name is not None:
            try:
                destination_store.rename(old, name)
                reload_destinations(name.strip())
            except (OSError, ValueError, TypeError) as exc:
                error(exc)

    def delete_destination():
        name = favorite_destination.get()
        if name and messagebox.askyesno('确认', '删除所选目的地收藏？', parent=win):
            try:
                destination_store.delete(name)
                reload_destinations()
            except (OSError, ValueError, TypeError) as exc:
                error(exc)

    for label, command in (('收藏当前终点', save_destination), ('设为终点', use_destination),
                           ('重命名目的地', rename_destination), ('删除目的地', delete_destination)):
        ttk.Button(destination_actions, text=label, command=command).pack(side='left', padx=4)
    ttk.Label(form, text='目的地收藏仅保存在本地；保存时不联网验证星系，点击“设为终点”后可继续编辑。',
              style='Muted.TLabel', wraplength=1360).pack(fill='x', padx=8)

    points_frame = ttk.LabelFrame(form, text='有序途经点', padding=6)
    points_frame.pack(fill='x', padx=8)
    box = ttk.Combobox(points_frame, textvariable=waypoint, width=52, height=12)
    box.grid(row=0, column=0, columnspan=5, sticky='ew', pady=4)
    attach_system_suggest(box, waypoint)
    points = ttk.Treeview(points_frame, columns=('order', 'name'), show='headings', height=3,
                          selectmode='browse', sortable=False)
    points.heading('order', text='序号')
    points.heading('name', text='星系')
    points.column('order', width=55, stretch=False)
    points.column('name', width=380)
    points.grid(row=2, column=0, columnspan=5, sticky='ew', pady=4)
    points_frame.columnconfigure(0, weight=1)

    def render_points(select=None):
        points.delete(*points.get_children())
        for index, name in enumerate(state['points']):
            points.insert('', 'end', iid=str(index), values=(index + 1, name))
        if select is not None and 0 <= select < len(state['points']):
            points.selection_set(str(select))
        render_legs()

    def add_point():
        name = waypoint.get().strip()
        if name:
            state['points'].append(name)
            render_points(len(state['points']) - 1)
            waypoint.set('')

    def edit_point(move=None):
        picked = points.selection()
        if not picked:
            return
        index = int(picked[0])
        if move is None:
            state['points'].pop(index)
            render_points(min(index, len(state['points']) - 1))
        elif 0 <= index + move < len(state['points']):
            state['points'][index], state['points'][index + move] = state['points'][index + move], state['points'][index]
            render_points(index + move)

    for col, (label, action) in enumerate((('添加途经点', add_point), ('上移', lambda: edit_point(-1)),
                                         ('下移', lambda: edit_point(1)), ('删除途经点', edit_point)), 1):
        ttk.Button(points_frame, text=label, command=action).grid(row=1, column=col - 1, padx=3, sticky='w')

    settings = ttk.Frame(form, padding=8)
    settings.pack(fill='x')
    for column, (label, variable) in enumerate((('货物 t', cargo), ('储备燃油 t', reserve))):
        ttk.Label(settings, text=label).grid(row=0, column=column * 2, sticky='w')
        ttk.Entry(settings, textvariable=variable, width=18).grid(row=0, column=column * 2 + 1, sticky='ew', padx=8, pady=5)
    for column, (label, variable, values) in enumerate((('注入策略', injection, injections), ('规划算法', algorithm, algorithms))):
        ttk.Label(settings, text=label).grid(row=1, column=column * 2, sticky='w')
        ttk.Combobox(settings, textvariable=variable, values=list(values), state='readonly', width=24).grid(
            row=1, column=column * 2 + 1, sticky='ew', padx=8, pady=5)
        settings.columnconfigure(column * 2 + 1, weight=1)
    flags_frame = ttk.Frame(form, padding=(8, 0))
    flags_frame.pack(fill='x')
    for index, (key, label) in enumerate((('supercharge', '使用中子增压'), ('already_supercharged', '第一段已增压'),
                                        ('exclude_secondary', '排除副星'), ('refuel_every_scoopable', '遇可补油恒星即补油'))):
        ttk.Checkbutton(flags_frame, text=label, variable=flags[key]).grid(row=index // 2, column=index % 2, sticky='w', padx=4)

    leg_state = dict(topology=None, overrides=[], dialog=None)
    leg_area = ttk.LabelFrame(form, text='分段配船（开始规划前配置）', padding=8)
    leg_area.pack(fill='x', padx=8, pady=6)
    ttk.Label(leg_area, text='默认各段沿用统一配船、货物和储备燃油；选中分段可单独配置。所有段校验完成后才开始查询。',
              wraplength=1300).pack(fill='x')
    leg_table = ttk.Treeview(leg_area, columns=('leg', 'source', 'destination', 'ship', 'cargo', 'reserve'),
                             show='headings', height=3, selectmode='browse', sortable=False)
    for key, label in (('leg', '分段编号'), ('source', '起点星系'), ('destination', '终点星系'),
                       ('ship', '本段配船'), ('cargo', '货物 t'), ('reserve', '储备燃油 t')):
        leg_table.heading(key, text=label)
        leg_table.column(key, width=65 if key == 'leg' else 180, minwidth=50)
    leg_table.pack(fill='x')
    leg_notice = tk.StringVar(win)
    ttk.Label(leg_area, textvariable=leg_notice, wraplength=1300, style='Warning.TLabel').pack(fill='x')
    ttk.Label(leg_area, text='每段独立满油；不验证途经点是否能换船或补油，请自行确认。',
              wraplength=1300, style='Warning.TLabel').pack(fill='x')

    def topology():
        return [source.get().strip(), *state['points'], destination.get().strip()]

    def render_legs(*_):
        route = topology()
        if route != leg_state['topology']:
            if any(entry['enabled'] for entry in leg_state['overrides']):
                leg_notice.set(tr('航点已变化，各段恢复统一设置，请重新核对分段配置。'))
            leg_state['topology'] = route
            leg_state['overrides'] = [dict(source=a, destination=b, enabled=False,
                                            selected='', cargo='', reserve='') for a, b in zip(route, route[1:])]
        selection = leg_table.selection()
        leg_table.delete(*leg_table.get_children())
        for index, entry in enumerate(leg_state['overrides']):
            own = entry['enabled']
            leg_table.insert('', 'end', iid=str(index), values=(index + 1, route[index], route[index + 1],
                entry['selected'] if own else f"{tr('沿用统一设置')}: {selected.get()}",
                entry['cargo'] if own else cargo.get(), entry['reserve'] if own else reserve.get()))
        if selection and leg_table.exists(selection[0]):
            leg_table.selection_set(selection[0])

    def edit_leg():
        if state['busy']:
            return
        if leg_state['dialog'] is not None and leg_state['dialog'].winfo_exists():
            leg_state['dialog'].lift()
            return
        picked = leg_table.selection()
        if not picked:
            return
        index = int(picked[0])
        entry = dict(leg_state['overrides'][index])
        route = list(leg_state['topology'])
        dialog = Toplevel(win)
        leg_state['dialog'] = dialog
        def close_editor(event):
            if event.widget is dialog and leg_state['dialog'] is dialog:
                leg_state['dialog'] = None
                # Break the public test/UI hook cycle while still on Tk's main
                # thread; a later worker must not finalize these Tk variables.
                if hasattr(dialog, 'leg_variables'):
                    dialog.leg_variables.clear()
                if hasattr(dialog, 'apply_leg'):
                    del dialog.apply_leg
        dialog.bind('<Destroy>', close_editor, add='+')
        dialog.title('单独配置分段')
        ttk.Label(dialog, text=f"{index + 1}. {route[index]} → {route[index + 1]}",
                  wraplength=650).pack(fill='x', padx=8, pady=8)
        enabled = tk.BooleanVar(dialog, value=entry['enabled'])
        own_ship = tk.StringVar(dialog, value=entry['selected'] if entry['enabled'] else selected.get())
        own_cargo = tk.StringVar(dialog, value=entry['cargo'] if entry['enabled'] else cargo.get())
        own_reserve = tk.StringVar(dialog, value=entry['reserve'] if entry['enabled'] else reserve.get())
        controls = []
        def toggle():
            for widget in controls:
                widget.configure(state=('readonly' if isinstance(widget, native_ttk.Combobox) else 'normal')
                                 if enabled.get() else 'disabled')
        ttk.Checkbutton(dialog, text='此段单独配置', variable=enabled, command=toggle).pack(anchor='w', padx=8)
        try:
            names = sorted(store.load(), key=str.casefold)
        except (OSError, ValueError) as exc:
            dialog.destroy()
            error(exc)
            return
        for label, variable in (('本段配船', own_ship), ('货物 t', own_cargo), ('储备燃油 t', own_reserve)):
            row = ttk.Frame(dialog, padding=8)
            row.pack(fill='x')
            ttk.Label(row, text=label).pack(side='left')
            widget = (native_ttk.Combobox(row, textvariable=variable, values=names, width=40) if variable is own_ship
                      else ttk.Entry(row, textvariable=variable, width=20))
            widget.pack(side='right', fill='x', expand=True, padx=8)
            controls.append(widget)
        toggle()

        def apply():
            if topology() != route:
                error(tr('航点已变化，请关闭并重新配置该分段。'))
                return
            try:
                if enabled.get():
                    if own_ship.get() not in store.load():
                        raise ValueError(tr('请先选择舰船配置'))
                    route_ship.numeric(own_cargo.get(), 'Cargo')
                    route_ship.numeric(own_reserve.get(), 'Reserve fuel')
                leg_state['overrides'][index] = dict(source=route[index], destination=route[index + 1],
                    enabled=enabled.get(), selected=own_ship.get(), cargo=own_cargo.get(), reserve=own_reserve.get())
                leg_notice.set('')
                render_legs()
                dialog.destroy()
            except (OSError, ValueError) as exc:
                error(exc)
        ttk.Button(dialog, text='应用分段配置', command=apply).pack(padx=8, pady=8)
        dialog.leg_variables = dict(enabled=enabled, selected=own_ship, cargo=own_cargo, reserve=own_reserve)
        dialog.apply_leg = apply
        return dialog

    ttk.Button(leg_area, text='配置所选分段', command=edit_leg).pack(anchor='w', pady=4)

    def restore_leg_overrides(entries, ships=None):
        render_legs()
        try:
            validate_leg_overrides(entries)
            if not entries:
                for entry in leg_state['overrides']:
                    entry.update(enabled=False, selected='', cargo='', reserve='', build_key='')
                render_legs()
                return
            if len(entries) != len(leg_state['overrides']) or any(
                    (entry['source'], entry['destination']) != (a, b)
                    for entry, a, b in zip(entries, topology(), topology()[1:])):
                if entries:
                    raise ValueError('Leg endpoints no longer match.')
                return
            restored = [dict(entry) for entry in entries]
            if ships is not None:
                for entry in restored:
                    if entry['enabled'] and entry.get('build_key'):
                        matches = [name for name, raw in ships.items() if build_key(raw) == entry['build_key']]
                        entry['selected'] = entry['selected'] if entry['selected'] in matches else matches[0] if matches else ''
            leg_state['overrides'] = restored
            render_legs()
        except (ValueError, TypeError, KeyError):
            leg_notice.set(tr('分段配置无法恢复，请重新核对。'))

    leg_traces = [(variable, variable.trace_add('write', render_legs))
                  for variable in (source, destination, selected, cargo, reserve)]
    app.localizer.register(render_legs)
    result_warning = tk.StringVar(win, value=tr(tool.FULL_TANK_NOTE))
    ttk.Label(result_area, textvariable=result_warning, style='Warning.TLabel', wraplength=1360).pack(fill='x', padx=8, pady=4)

    status = tk.StringVar(win, value='选择收藏舰船，填写起终点；途经点按列表顺序规划。')
    ttk.Label(result_area, textvariable=status, wraplength=1360).pack(fill='x', padx=8)
    bar = ttk.Progressbar(result_area, mode='determinate')
    bar.pack(fill='x', padx=8)
    progress_text = tk.StringVar(win)
    ttk.Label(result_area, textvariable=progress_text).pack(fill='x', padx=8)
    tracker = SearchProgress(bar, progress_text, app.localizer)
    actions = ttk.Frame(result_area, padding=8)
    actions.pack(fill='x')
    recent = ttk.Frame(result_area, padding=(8, 0))
    recent.pack(fill='x')
    ttk.Label(recent, text='最近5次规划').pack(side='left')
    history_choice = tk.StringVar(win)
    history_chooser = native_ttk.Combobox(recent, textvariable=history_choice, state='readonly', width=60, height=5)
    history_chooser.pack(side='left', fill='x', expand=True, padx=6)
    ttk.Label(result_area, text='蓝色行：Spansh 标记含中子星的星系；实际增压条件请在游戏中确认。',
              style='Muted.TLabel', wraplength=1360).pack(fill='x', padx=8)
    table = ttk.Frame(result_area)
    table.pack(fill='both', expand=True, padx=8, pady=4)
    tree = ttk.Treeview(table, columns=[key for key, _ in tool.COLUMNS], show='headings')
    for key, title in tool.COLUMNS:
        tree.heading(key, text=title)
        tree.column(key, width=300 if key in ('name', 'assumption') else 150, stretch=False)
    yscroll = ttk.Scrollbar(table, orient='vertical', command=tree.yview)
    xscroll = ttk.Scrollbar(table, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    tree.grid(row=0, column=0, sticky='nsew')
    yscroll.grid(row=0, column=1, sticky='ns')
    xscroll.grid(row=1, column=0, sticky='ew')
    table.rowconfigure(0, weight=1)
    table.columnconfigure(0, weight=1)

    # Monitoring is deliberately not a route parameter or a persisted setting:
    # both switches start off, and no Journal is touched until explicitly enabled.
    follow_enabled, auto_copy = tk.BooleanVar(win, value=False), tk.BooleanVar(win, value=False)
    position = RoutePosition()
    follow_state = dict(info=None, location=None, generation=0, stop=threading.Event(),
                        marked=None, copied=None, error=None)
    follow_text = tk.StringVar(win)
    follow_controls = ttk.Frame(result_area, padding=8)
    follow_controls.pack(fill='x', before=table)

    def refresh_follow(rebuilt=False):
        if follow_state['info'] is not state['info']:
            info = state['info']
            position.set_route(info['rows'] if info else [])
            follow_state.update(info=info, copied=None)
        location = follow_state['location'] if follow_enabled.get() else None
        index = position.match(location.system if location else None,
                               (location.filename, location.timestamp) if location else None)
        target = str(index) if index is not None else None
        old = follow_state['marked']
        if old is not None and tree.exists(old) and (old != target or rebuilt):
            tree.item(old, tags=tuple(tag for tag in tree.item(old, 'tags') if tag != 'route_current'))
        if target is not None and tree.exists(target) and (old != target or rebuilt):
            tree.item(target, tags=('route_current', *tuple(tag for tag in tree.item(target, 'tags')
                                                          if tag != 'route_current')))
        follow_state['marked'] = target
        text = ''
        if location and position.ambiguous:
            text = tr('当前位置在路线中多次出现，请选中对应行并点击“确认所选位置”。')
        elif index is not None:
            next_system = position.next_system
            text = (f"{tr('当前星系')}: {position.names[index]} | {tr('路线位置')}: {index + 1}/{len(position.names)}"
                    f" | {tr('日志时间')}: {location.timestamp}")
            if next_system is not None:
                text += f" | {tr('计划下一跳')}: {next_system}"
            else:
                label = ('已到达终点' if state['info']['complete'] else
                         '已到 CSV 文件末尾（不代表完整航线终点）' if state['info'].get('imported') else
                         '已到已验证路线末尾（路线未完成）')
                text += ' | ' + tr(label)
            if auto_copy.get() and position.should_copy:
                try:
                    win.clipboard_clear()
                    win.clipboard_append(next_system)
                except tk.TclError:
                    text += ' | ' + tr('剪贴板暂不可用，可重新切换自动复制开关重试。')
                else:
                    position.mark_copied()
                    follow_state['copied'] = (index, next_system)
            if follow_state['copied'] == (index, next_system) and next_system is not None:
                text += f" | {tr('已复制下一跳')}: {next_system}"
        else:
            follow_state['copied'] = None
            if follow_enabled.get() and follow_state['error']:
                text = tr('读取日志位置失败，等待重试。')
        if follow_text.get() != text:
            follow_text.set(text)
        if map_window is not None:
            map_window.sync()

    def restart_follow():
        follow_state['stop'].set()
        follow_state['generation'] += 1
        generation = follow_state['generation']
        stopped = threading.Event()
        follow_state.update(stop=stopped, location=None, error=None, copied=None)
        auto_control.configure(state='normal' if follow_enabled.get() else 'disabled')
        refresh_follow()
        if not follow_enabled.get():
            return
        directory = app.journal_directory or journal_location.default_directory()

        def worker():
            reader = journal_location.JournalFollower(directory)
            previous = object()
            while not stopped.is_set():
                try:
                    payload = (reader.poll(), None)
                except (OSError, ValueError) as exc:
                    payload = (None, str(exc))
                if stopped.is_set():
                    break
                if payload != previous:
                    events.put(('follow', (generation, *payload)))
                    previous = payload
                stopped.wait(2)
        threading.Thread(target=worker, daemon=True, name='journal-follow').start()

    def locate_current():
        if position.index is not None:
            tree.see(str(position.index))
            win.update_idletasks()
            bounds = canvas.bbox('all')
            if bounds:
                canvas.yview_moveto(max(0, (table.winfo_y() + result_area.winfo_y()) / max(1, bounds[3])))

    def choose_position():
        selected_rows = tree.selection()
        location = follow_state['location']
        if follow_enabled.get() and location and len(selected_rows) == 1:
            if position.choose(int(selected_rows[0]), location.system):
                refresh_follow()

    ttk.Checkbutton(follow_controls, text='跟随游戏位置', variable=follow_enabled,
                    command=restart_follow).grid(row=0, column=0, sticky='w', padx=4)
    auto_control = ttk.Checkbutton(follow_controls, text='自动复制计划下一跳', variable=auto_copy,
                                   command=refresh_follow, state='disabled')
    auto_control.grid(row=0, column=1, sticky='w', padx=4)
    ttk.Button(follow_controls, text='定位当前行', command=locate_current).grid(row=1, column=0, sticky='w', padx=4)
    ttk.Button(follow_controls, text='确认所选位置', command=choose_position).grid(row=1, column=1, sticky='w', padx=4)
    ttk.Label(follow_controls, textvariable=follow_text, wraplength=1200).grid(row=2, column=0, columnspan=2, sticky='ew')
    ttk.Label(follow_controls, text='绿色行表示当前位置；自动复制会替换剪贴板内容，不在路线中时不操作。',
              style='Muted.TLabel', wraplength=1200).grid(row=3, column=0, columnspan=2, sticky='ew')
    app.localizer.register(refresh_follow)

    def render_results():
        if not win.winfo_exists():
            return
        selection = tree.selection()
        result_warning.set(tr('导入路线仅依据 CSV 记录，不确认配船、满油、完整性或实际可行性。')
                           if state['info'] and state['info'].get('imported') else tr(tool.FULL_TANK_NOTE))
        tree.delete(*tree.get_children())
        # Let short routes fit naturally, but keep long routes bounded so Tk
        # does not need an enormous native child window. Their scrollbar remains.
        count = len(state['info']['rows']) if state['info'] else 0
        tree.configure(height=min(25, max(8, count)))
        if state['info']:
            for index, values in enumerate(tool.display_rows(state['info'], app.localizer.tr)):
                row = state['info']['rows'][index]
                neutron = row.get('has_neutron') is True or row.get('has_neutron') == 1
                tree.insert('', 'end', iid=str(index), values=values, tags=('neutron',) if neutron else ())
            for item in selection:
                if tree.exists(item):
                    tree.selection_add(item)
            info = state['info']
            en = app.localizer.language == 'en'
            status.set((f"Completed legs: {len(info['segments']):,}/{info['planned_segments']:,}; " if en else
                         f"已完成分段：{len(info['segments']):,}/{info['planned_segments']:,}；") + app.localizer.tr(info['reason']))
            if info.get('imported'):
                status.set(tr(info['reason']) + ' | ' + info.get('import_filename', ''))
            if state['cached_at']:
                status.set(status.get() + f" | {tr('历史结果，未重新查询')}: {state['cached_at']}")
            timing = info.get('timings')
            if isinstance(timing, dict):
                fields = (('配船处理', 'ship_seconds'), ('星系解析', 'resolve_seconds'),
                          ('路线请求与等待', 'route_seconds'), ('总耗时', 'total_seconds'))
                values = ' | '.join(f'{tr(label)}: {timing[key]:.2f}s' for label, key in fields
                                    if isinstance(timing.get(key), (int, float)))
                status.set(status.get() + '\n' + tr('该次查询耗时') + ': ' + values)
        refresh_follow(rebuilt=True)
    app.localizer.register(render_results)

    def render_history(reset=False):
        selected_index = 0 if reset else max(0, history_chooser.current())
        labels = []
        for index, entry in enumerate(history, 1):
            p = entry['parameters']
            labels.append(f"{index}. {entry['created']} | {p['source']} → {p['destination']} | "
                          f"{p['selected']} | {tr('完整' if entry['result']['complete'] else '未完成')}")
        history_chooser.configure(values=labels)
        history_choice.set(labels[min(selected_index, len(labels) - 1)] if labels else '')
    app.localizer.register(render_history)

    def restore_history():
        if state['busy']:
            return
        index = history_chooser.current()
        if not 0 <= index < len(history):
            return
        entry = history[index]
        try:
            ships = store.load()
            matches = [name for name, raw in ships.items() if build_key(raw) == entry['build_key']]
            original = entry['parameters']['selected']
            name = original if original in matches else matches[0] if matches else ''
        except (OSError, ValueError, TypeError) as exc:
            error(exc)
            return
        for key, value in entry['parameters'].items():
            if key in win.route_variables and key != 'selected':
                win.route_variables[key].set(value)
        selected.set(name)
        state.update(points=list(entry['points']), info=entry['result'], result_key=entry['key'], cached_at=entry['created'])
        render_points()
        restore_leg_overrides(entry['parameters'].get('leg_overrides', []), ships)
        tracker.finish(entry['result']['complete'])
        render_results()
        if not name:
            messagebox.showinfo('提示', '历史配船已删除或修改；结果仍可查看和导出，请重新选择配船后再规划。', parent=win)

    ttk.Button(recent, text='查看历史结果', command=restore_history).pack(side='left')

    def run():
        if state['busy']:
            return
        try:
            if leg_state['dialog'] is not None and leg_state['dialog'].winfo_exists():
                raise ValueError(tr('请先应用分段配置或关闭配置窗口，再开始规划。'))
            render_legs()
            ships = store.load()
            raw = ships.get(selected.get())
            if raw is None:
                raise ValueError(tr('请先选择舰船配置'))
            route_points = [source.get().strip(), *state['points'], destination.get().strip()]
            if any(not p for p in route_points):
                raise ValueError(tr('请填写起点和终点星系'))
            options = tool.Options(cargo=cargo.get(), reserve=reserve.get(), injection=injections[injection.get()],
                                   algorithm=algorithms[algorithm.get()], **{k: v.get() for k, v in flags.items()}).validate()
            configs, saved_overrides = [], []
            for number, entry in enumerate(leg_state['overrides'], 1):
                own = entry['enabled']
                name = entry['selected'] if own else selected.get()
                leg_raw = ships.get(name)
                if leg_raw is None or own and entry.get('build_key') and build_key(leg_raw) != entry['build_key']:
                    raise ValueError(tr('分段配船已删除或修改，请重新配置。') + f' ({number})')
                route_ship.decode_build(leg_raw)
                config = dict(raw=leg_raw, name=name,
                              cargo=route_ship.numeric(entry['cargo'] if own else options.cargo, 'Cargo'),
                              reserve=route_ship.numeric(entry['reserve'] if own else options.reserve, 'Reserve fuel'))
                configs.append(config)
                saved_overrides.append(dict(entry, build_key=build_key(leg_raw) if own else ''))
            key = request_key(raw, route_points, options, configs if any(e['enabled'] for e in saved_overrides) else None)
        except (OSError, ValueError) as exc:
            error(exc)
            return
        if state['info'] and state['info']['complete'] and key == state['result_key']:
            return
        retrying = state['info'] and not state['info']['complete'] and key == state['result_key']
        cached = None if retrying else find_complete(history, key)
        if cached is not None:
            index, entry = cached
            state.update(info=entry['result'], result_key=key, cached_at=entry['created'])
            history_chooser.current(index)
            tracker.finish(True)
            render_results()
            return
        if len(route_points) > 2 and not messagebox.askyesno('多段航线确认',
                '每一段都按起点满油独立计算，不继承上一段剩余燃油或增压状态。途经点不保证能补油，请确认下一段出发前可以补满。继续？', parent=win):
            return
        stop.clear()
        parameters = {key: variable.get() for key, variable in win.route_variables.items() if key != 'waypoint'}
        parameters['leg_overrides'] = saved_overrides
        state.update(busy=True, info=None, result_key=None, cached_at=None,
                     pending=dict(key=key, ship_key=build_key(raw), parameters=parameters, points=list(state['points'])))
        tree.delete(*tree.get_children())
        refresh_follow(rebuilt=True)
        start_button.configure(state='disabled')
        stop_button.configure(state='normal')
        tracker.update()
        status.set('正在提交联网航线规划…')
        def worker():
            try:
                result = tool.plan(raw, route_points, options, stop,
                                   lambda text, detail: events.put(('progress', (text, detail))), leg_configs=configs)
            except Exception as exc:
                result = dict(complete=False, rows=[], segments=[], planned_segments=len(route_points) - 1,
                              reason=str(exc), failed_segment=None, full_tank_each_segment=True)
            events.put(('done', result))
        threading.Thread(target=worker, daemon=True).start()

    def export():
        info = state['info']
        if not info or not info['rows']:
            messagebox.showinfo('提示', '暂无结果', parent=win)
            return
        confirmation = ('导入航线的完整性未确认，仍要导出文件中的记录？' if info.get('imported') else
                        '航线未完成，仅导出已完成分段？')
        if not info['complete'] and not messagebox.askyesno('确认', confirmation, parent=win):
            return
        path = filedialog.asksaveasfilename(parent=win, defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if path:
            try:
                tool.export_csv(path, info, app.localizer.tr, language=app.localizer.language)
            except OSError as exc:
                error(exc)

    def import_route():
        if state['busy']:
            return
        path = filedialog.askopenfilename(parent=win, filetypes=[('CSV', '*.csv'), ('All', '*.*')])
        if not path:
            return
        state['busy'] = True
        stop.clear()
        start_button.configure(state='disabled')
        stop_button.configure(state='normal')
        import_button.configure(state='disabled')
        status.set(tr('正在导入 CSV（不联网）…'))
        def worker():
            try:
                from route_csv import import_csv
                info = import_csv(path, stop)
                events.put(('csv_import', (info, None)))
            except (OSError, ValueError, csv.Error) as exc:
                events.put(('csv_import', (None, str(exc))))
        threading.Thread(target=worker, daemon=True, name='csv-import').start()

    start_button = ttk.Button(actions, text='规划航线', command=run)
    start_button.pack(side='left')
    stop_button = ttk.Button(actions, text='停止', command=stop.set, state='disabled')
    stop_button.pack(side='left', padx=5)
    ttk.Button(actions, text='复制星系名', command=lambda: copy_result(win, tree, 'name')).pack(side='left', padx=5)
    ttk.Button(actions, text='导出 CSV', command=export).pack(side='left', padx=5)
    import_button = ttk.Button(actions, text='导入路线 CSV', command=import_route)
    import_button.pack(side='left', padx=5)
    def show_map():
        nonlocal map_window
        if map_window is None or map_window.closed:
            from route_map import RouteMap
            map_window = RouteMap(win, app, lambda: state['info'], lambda: position.index)
        else:
            map_window.win.deiconify()
            map_window.win.lift()
            map_window.sync()
        return map_window
    ttk.Button(actions, text='俯视路线图', command=show_map).pack(side='left', padx=5)
    win.show_route_map = show_map
    poll_id = None
    def poll():
        nonlocal poll_id, history
        if not win.winfo_exists():
            return
        try:
            while True:
                event, result = events.get_nowait()
                if event == 'preview':
                    generation, params, failure = result
                    if generation == preview['generation']:
                        preview.update(params=params, error=failure)
                        render_preview()
                elif event == 'journal_ship':
                    imported, failure = result
                    ship_reading['busy'] = False
                    ship_read_button.configure(state='normal')
                    ship_history_button.configure(state='normal')
                    if failure:
                        error(tr(failure))
                    elif isinstance(imported, journal_ship.ShipHistory):
                        history_picker(imported)
                    else:
                        editor(imported=imported)
                elif event == 'csv_import':
                    imported, failure = result
                    state['busy'] = False
                    start_button.configure(state='normal')
                    stop_button.configure(state='disabled')
                    import_button.configure(state='normal')
                    if failure:
                        status.set(tr('CSV 导入失败，原结果未更改。'))
                        error(failure)
                    else:
                        # Loading a file is not consent to copy a new route's
                        # next system or scan Journals. Re-enable explicitly.
                        follow_enabled.set(False)
                        auto_copy.set(False)
                        restart_follow()
                        state.update(info=imported, result_key=None, cached_at=None)
                        tracker.finish(imported['complete'])
                        render_results()
                elif event == 'progress':
                    text, detail = result
                    status.set(text)
                    tracker.update(text, detail)
                elif event == 'journal':
                    location, failure = result
                    journal_state['busy'] = False
                    for button in journal_buttons:
                        button.configure(state='normal')
                    if failure:
                        journal_status.set('读取日志失败；起点未更改。')
                        error(failure)
                    elif source.get() != journal_state['source']:
                        journal_status.set('起点已手动更改，未覆盖；如需日志位置请再次点击。')
                    else:
                        # Bypass autocomplete: reading a local position must not
                        # silently send that system to a suggestion service.
                        set_source_system(location.system)
                        journal_state['location'] = location
                        render_journal()
                elif event == 'follow':
                    generation, location, failure = result
                    if follow_enabled.get() and generation == follow_state['generation']:
                        follow_state.update(location=location, error=failure)
                        refresh_follow()
                else:
                    pending = state['pending']
                    state.update(busy=False, info=result, result_key=pending['key'], pending=None, cached_at=None)
                    start_button.configure(state='normal')
                    stop_button.configure(state='disabled')
                    tracker.finish(result['complete'])
                    render_results()
                    try:
                        history = history_store.add(history, result=result, **pending)
                        render_history(reset=True)
                    except (OSError, ValueError, TypeError) as exc:
                        error(exc)
        except queue.Empty:
            pass
        poll_id = win.after(100, poll)

    def dispose(event):
        if event.widget is win:
            stop.set()
            preview_closed.set()
            follow_state['stop'].set()
            selected.trace_remove('write', selected_trace)
            cargo.trace_remove('write', cargo_trace)
            for variable, trace in leg_traces:
                variable.trace_remove('write', trace)
            app.localizer.callbacks.discard(render_preview)
            app.localizer.callbacks.discard(render_results)
            app.localizer.callbacks.discard(render_history)
            app.localizer.callbacks.discard(render_journal)
            app.localizer.callbacks.discard(refresh_follow)
            app.localizer.callbacks.discard(render_legs)
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                win.unbind_class(wheel_tag, sequence)
            if poll_id is not None:
                win.after_cancel(poll_id)
    win.bind('<Destroy>', dispose, add='+')
    poll_id = win.after(100, poll)
    win.route_state, win.result_tree, win.waypoint_tree = state, tree, points
    win.route_variables = dict(source=source, destination=destination, waypoint=waypoint, selected=selected,
                               cargo=cargo, reserve=reserve, algorithm=algorithm, injection=injection, **flags)
    win.render_points = render_points
    win.leg_state, win.leg_table, win.leg_notice = leg_state, leg_table, leg_notice
    win.edit_leg, win.render_legs, win.restore_leg_overrides = edit_leg, render_legs, restore_leg_overrides
    win.ship_preview = preview
    win.ship_summary_variables = dict(identity=identity_text, ranges=range_text)
    win.build_editor, win.reload_favorites = editor, reload_favorites
    win.destination_favorite_variable = favorite_destination
    win.destination_chooser = destination_chooser
    win.reload_destinations = reload_destinations
    win.history_chooser = history_chooser
    win.render_results = render_results
    win.journal_state, win.journal_status = journal_state, journal_status
    win.follow_variables = dict(enabled=follow_enabled, auto_copy=auto_copy)
    win.follow_state, win.follow_position, win.follow_text = follow_state, position, follow_text
    win.refresh_follow, win.restart_follow = refresh_follow, restart_follow
    try:
        history = history_store.load()
        render_history()
    except (OSError, ValueError, TypeError) as exc:
        error(exc)
    reload_destinations()
    reload_favorites()
    # Run before widget class bindings: wheel over a closed combobox scrolls
    # the page instead of silently changing a route option. Popups/editors have
    # their own widgets and are deliberately not assigned this page-only tag.
    def bind_page_wheel(widget):
        widget.bindtags((wheel_tag, *widget.bindtags()))
        for child in widget.winfo_children():
            bind_page_wheel(child)
    bind_page_wheel(page)
    return win

"""Offline X/Z route preview. Canonical order only; missing coordinates break lines."""
import math
import tkinter as tk

from localized_tk import Toplevel, ttk


def top_down(row):
    values = (row.get('x'), row.get('z'))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        return None
    if any(not math.isfinite(v) or abs(v) > 1e9 for v in values):
        return None
    return tuple(float(v) for v in values)


def line_runs(points):
    runs, run = [], []
    for point in points:
        if point is None:
            if len(run) > 1:
                runs.append(run)
            run = []
        else:
            run.append(point)
    if len(run) > 1:
        runs.append(run)
    return runs


class View:
    def __init__(self):
        self.scale, self.ox, self.oy = 1., 0., 0.

    def fit(self, points, width, height):
        valid = [p for p in points if p is not None]
        if not valid:
            self.scale, self.ox, self.oy = 1., width / 2, height / 2
            return
        xs, zs = zip(*valid)
        span_x, span_z = max(xs) - min(xs), max(zs) - min(zs)
        self.scale = min(max(1, width - 100) / max(1, span_x),
                         max(1, height - 100) / max(1, span_z))
        self.ox = width / 2 - (min(xs) + span_x / 2) * self.scale
        self.oy = height / 2 + (min(zs) + span_z / 2) * self.scale

    def project(self, point):
        return self.ox + point[0] * self.scale, self.oy - point[1] * self.scale

    def zoom(self, factor, x, y):
        scale = max(1e-8, min(1e6, self.scale * factor))
        factor = scale / self.scale
        self.ox, self.oy = x + (self.ox - x) * factor, y + (self.oy - y) * factor
        self.scale = scale


class RouteMap:
    def __init__(self, parent, app, get_info, get_position):
        self.app, self.get_info, self.get_position = app, get_info, get_position
        self.win = Toplevel(parent)
        self.win.title('俯视路线图')
        self.win.geometry('1000x680')
        self.win.minsize(550, 380)
        self.info, self.current, self.theme = None, None, None
        self.rows, self.points, self.screen_points = [], [], []
        self.view, self.drag = View(), None
        self.closed, self.timer = False, None
        controls = ttk.Frame(self.win, padding=8)
        controls.pack(fill='x')
        ttk.Button(controls, text='适应整条路线', command=self.fit).pack(side='left')
        ttk.Label(controls, text='俯视 X/Z（ly）；滚轮缩放，左键拖动，指向星点查看名称。',
                  wraplength=780).pack(side='left', padx=12)
        self.summary, self.hover = tk.StringVar(self.win), tk.StringVar(self.win)
        ttk.Label(self.win, textvariable=self.summary, wraplength=950).pack(fill='x', padx=8)
        ttk.Label(self.win, text='蓝：中子星；橙圈：补油；绿圈：当前位置；菱形：途经点。',
                  wraplength=950).pack(fill='x', padx=8)
        self.canvas = tk.Canvas(self.win, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Label(self.win, textvariable=self.hover).pack(fill='x', padx=8, pady=(0, 8))
        self.canvas.bind('<Configure>', lambda e: self.fit())
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-4>', self.wheel)
        self.canvas.bind('<Button-5>', self.wheel)
        self.canvas.bind('<ButtonPress-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.pan)
        self.canvas.bind('<Motion>', self.inspect)
        self.canvas.bind('<Leave>', lambda e: self.hover.set(''))
        self.win.bind('<Destroy>', self.dispose, add='+')
        app.localizer.register(self.draw)
        self.sync()
        self.tick()

    def sync(self):
        if self.closed:
            return
        info, current = self.get_info(), self.get_position()
        theme = self.app.appearance_manager.effective
        changed = info is not self.info
        repaint = changed or current != self.current or theme != self.theme
        self.info, self.current, self.theme = info, current, theme
        if changed:
            self.rows = info['rows'] if info else []
            self.points = [top_down(row) for row in self.rows]
            self.fit()
        elif repaint:
            self.draw()

    def tick(self):
        self.sync()
        self.timer = self.win.after(500, self.tick)

    def fit(self):
        self.view.fit(self.points, self.canvas.winfo_width(), self.canvas.winfo_height())
        self.draw()

    def wheel(self, event):
        delta = getattr(event, 'delta', 0)
        direction = 1 if getattr(event, 'num', None) == 4 or delta > 0 else -1
        self.view.zoom(1.2 if direction > 0 else 1 / 1.2, event.x, event.y)
        self.draw()
        return 'break'

    def start_drag(self, event):
        self.drag = (event.x, event.y)

    def pan(self, event):
        if self.drag is not None:
            self.view.ox += event.x - self.drag[0]
            self.view.oy += event.y - self.drag[1]
            self.drag = (event.x, event.y)
            self.draw()

    def inspect(self, event):
        closest = [(math.hypot(p[0] - event.x, p[1] - event.y), index)
                   for index, p in enumerate(self.screen_points) if p is not None]
        distance, index = min(closest, default=(float('inf'), 0))
        if distance <= 12:
            x, z = self.points[index]
            self.hover.set(f"{index + 1}. {self.rows[index]['name']} | X: {x:g}, Z: {z:g} ly")
        else:
            self.hover.set('')

    def draw(self):
        if self.closed:
            return
        tr, canvas = self.app.localizer.tr, self.canvas
        p = self.app.appearance_manager.palette
        canvas.configure(background=p['surface'])
        canvas.delete('all')
        self.hover.set('')
        count = sum(point is not None for point in self.points)
        message = tr('完整路线' if self.info and self.info['complete'] else '未完成路线：仅显示已验证部分')
        if self.info and self.info.get('imported'):
            message = tr('导入路线：未重新验证，以文件记录为准')
        self.summary.set(f"{message} | {tr('可绘制星系')}: {count}/{len(self.points)} | " +
                         tr('缺失坐标处断开；俯视投影不显示高度，图上距离不等于跳跃距离。'))
        self.screen_points = [self.view.project(point) if point is not None else None for point in self.points]
        if not count:
            canvas.create_text(canvas.winfo_width() / 2, canvas.winfo_height() / 2,
                               text=tr('暂无可用坐标；不会推算位置或额外联网。'), fill=p['text'])
        for run in line_runs(self.screen_points):
            canvas.create_line(*[value for point in run for value in point], fill=p['muted'], width=2,
                               tags='route_line')
        # Bound ordinary point markers for long routes; keep the full polyline
        # and all special markers, and hit-test against every original row.
        stride = max(1, len(self.rows) // 2000)
        for index, point in enumerate(self.screen_points):
            if point is None:
                continue
            row = self.rows[index]
            x, y = point
            special = index in (0, len(self.rows) - 1, self.current) or any(
                row.get(key) for key in ('has_neutron', 'must_refuel', 'waypoint'))
            if index % stride and not special:
                continue
            color = '#4098ff' if row.get('has_neutron') else p['accent']
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color, tags='star')
            if row.get('must_refuel'):
                canvas.create_oval(x - 6, y - 6, x + 6, y + 6, outline='#e69923', width=2, tags='refuel')
            if row.get('waypoint'):
                canvas.create_polygon(x, y - 8, x + 8, y, x, y + 8, x - 8, y,
                                      fill='', outline=p['text'], tags='waypoint')
            if index == self.current:
                canvas.create_oval(x - 10, y - 10, x + 10, y + 10, outline='#25ad65', width=3, tags='current')
            if index in (0, len(self.rows) - 1):
                label = '起点' if index == 0 else ('终点' if self.info['complete'] else
                        'CSV 文件末尾' if self.info.get('imported') else '已验证末尾')
                canvas.create_text(x + 10, y - 14 if index == 0 else y + 14, anchor='w',
                                   text=f"{tr(label)}: {row['name']}", fill=p['text'], tags='endpoint')
        canvas.create_text(12, 12, anchor='nw', text='+Z ↑    +X →', fill=p['muted'])
        # A projection scale only, never a claimed in-game jump distance.
        if count:
            canvas.create_line(15, 42, 115, 42, fill=p['muted'])
            canvas.create_text(15, 49, anchor='nw', text=f'{100 / self.view.scale:.3g} ly (X/Z)', fill=p['muted'])

    def dispose(self, event):
        if event.widget is self.win:
            self.closed = True
            self.app.localizer.callbacks.discard(self.draw)
            if self.timer is not None:
                self.win.after_cancel(self.timer)

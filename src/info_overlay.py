"""Read-only Win32 overlay. No Tk window, input hooks, clipboard or networking.

Layered + WS_EX_TRANSPARENT passes input to underlying applications; NOACTIVATE
and SWP_NOACTIVATE prevent focus changes. All calls/painting run on Tk's thread.
See Microsoft Learn: window-features#layered-windows, extended-window-styles.
"""
import ctypes
from ctypes import wintypes as w
import math
from decimal import Decimal
import sys
import tkinter as tk
from tkinter import font

from localized_tk import ttk

from result_format import format_ly, format_number

EX_TRANSPARENT = 0x20
EX_TOOLWINDOW = 0x80
EX_LAYERED = 0x80000
EX_NOACTIVATE = 0x08000000
EX_STYLES = EX_TRANSPARENT | EX_TOOLWINDOW | EX_LAYERED | EX_NOACTIVATE
CORNERS = {'top_right': '右上角', 'top_left': '左上角', 'bottom_right': '右下角', 'bottom_left': '左下角'}
DEFAULTS = dict(corner='top_right', margin_x=24, margin_y=80, font_size=14, opacity=85)


def settings(value):
    """Validate persisted preferences without ever persisting enabled state."""
    result = dict(DEFAULTS)
    if not isinstance(value, dict):
        return result
    if isinstance(value.get('corner'), str) and value['corner'] in CORNERS:
        result['corner'] = value['corner']
    for key, low, high in (('margin_x', 0, 2000), ('margin_y', 0, 2000), ('font_size', 10, 28), ('opacity', 35, 100)):
        number = value.get(key)
        if type(number) is int and low <= number <= high:
            result[key] = number
    return result


def placement(work, size, config):
    left, top, right, bottom = work
    width, height = min(size[0], max(1, right - left)), min(size[1], max(1, bottom - top))
    x = left + config['margin_x'] if config['corner'].endswith('left') else right - width - config['margin_x']
    y = top + config['margin_y'] if config['corner'].startswith('top') else bottom - height - config['margin_y']
    return max(left, min(right - width, x)), max(top, min(bottom - height, y)), width, height


HEALTH_COLOURS = dict(green='#42d67b', yellow='#f2c94c', red='#ff6868')


def health_colour(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return HEALTH_COLOURS['green' if value > .85 else 'yellow' if value >= .8 else 'red']


class OverlayText(str):
    def __new__(cls, value, line_colours):
        instance = super().__new__(cls, value)
        instance.line_colours = line_colours
        return instance


def overlay_text(info, index, following, timestamp, tr, fsd_health=None):
    """None means hide quietly (off-route, unreadable or ambiguous position)."""
    if not following:
        return tr('路线信息悬浮窗') + '\n' + tr('请在主窗口开启“跟随游戏位置”。')
    rows = info.get('rows', []) if info else []
    if index is None or not 0 <= index < len(rows):
        return None
    short = lambda value: str(value)[:100] + ('…' if len(str(value)) > 100 else '')
    row = rows[index]
    lines = [tr('当前星系') + ': ' + short(row['name'])]
    if index + 1 < len(rows):
        next_row = rows[index + 1]
        lines.append(tr('计划下一跳') + ': ' + short(next_row['name']))
        distance = next_row.get('distance')
        if type(distance) in (int, float) and math.isfinite(distance) and distance >= 0:
            lines.append(tr('下一跳距离') + ': ' + format_ly(distance) + ' ly')
    else:
        lines.append(tr('已到达终点' if info['complete'] else
                        '已到 CSV 文件末尾（不代表完整航线终点）' if info.get('imported') else
                        '已到已验证路线末尾（路线未完成）'))
    lines.append(f"{tr('路线位置')}: {index + 1}/{len(rows)} | {tr('剩余跳数')}: {len(rows) - index - 1}")
    ship = row.get('departure_ship') or row.get('ship_name')
    if ship:
        lines.append(tr('本段配船') + ': ' + short(ship))
    actions = [tr(label) for key, label in (('must_refuel', '需要补油'), ('has_neutron', '中子星'))
               if row.get(key) is True or row.get(key) == 1]
    if actions and index + 1 < len(rows):
        lines.append(' | '.join(actions))
    if info.get('imported'):
        lines.append(tr('导入路线：未重新验证，以文件记录为准'))
    elif not info['complete']:
        lines.append(tr('未完成路线：仅显示已验证部分'))
    if timestamp:
        lines.append(tr('日志时间') + ': ' + timestamp)
    from journal_health import FsdHealth
    colour = health_colour(fsd_health.value) if isinstance(fsd_health, FsdHealth) else None
    colours = {}
    label = tr('FSD 耐久（日志快照）')
    if colour:
        # Decimal string conversion avoids rounding 85.00001% to a yellow-looking
        # 85% label while the underlying value correctly belongs to green.
        percent = format_number(Decimal(str(fsd_health.value)) * 100)
        colours[len(lines)] = colour
        lines.append(f'{label}: {percent}%')
        lines.append(tr('耐久记录时间') + ': ' + fsd_health.timestamp)
    else:
        lines.append(label + ': ' + tr('情况未知'))
    return OverlayText('\n'.join(lines), colours)


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [('hdc', w.HDC), ('erase', w.BOOL), ('rect', w.RECT), ('restore', w.BOOL),
                ('inc_update', w.BOOL), ('reserved', ctypes.c_byte * 32)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('monitor', w.RECT), ('work', w.RECT), ('flags', w.DWORD)]


_api = None
_callback = None  # Keep registered native callback alive for the process lifetime.
_windows = {}
_class_name = 'EliteNeutronPlannerReadOnlyOverlayV1'


def _colour(hex_value):
    value = hex_value.lstrip('#')
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return red | green << 8 | blue << 16


def api():
    global _api, _callback
    if _api is not None:
        return _api
    if sys.platform != 'win32':
        raise OSError('Click-through overlay requires Windows.')
    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    class WNDCLASS(ctypes.Structure):
        _fields_ = [('style', w.UINT), ('proc', proc), ('class_extra', ctypes.c_int), ('window_extra', ctypes.c_int),
                    ('instance', w.HINSTANCE), ('icon', w.HICON), ('cursor', w.HANDLE), ('background', w.HBRUSH),
                    ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]
    signatures = {
        'DefWindowProcW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], ctypes.c_ssize_t),
        'RegisterClassW': ([ctypes.POINTER(WNDCLASS)], w.ATOM),
        'CreateWindowExW': ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID], w.HWND),
        'SetWindowPos': ([w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT], w.BOOL),
        'SetLayeredWindowAttributes': ([w.HWND, w.DWORD, w.BYTE, w.DWORD], w.BOOL),
        'ShowWindow': ([w.HWND, ctypes.c_int], w.BOOL), 'DestroyWindow': ([w.HWND], w.BOOL),
        'InvalidateRect': ([w.HWND, ctypes.POINTER(w.RECT), w.BOOL], w.BOOL),
        'BeginPaint': ([w.HWND, ctypes.POINTER(PAINTSTRUCT)], w.HDC),
        'EndPaint': ([w.HWND, ctypes.POINTER(PAINTSTRUCT)], w.BOOL),
        'GetClientRect': ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
        'FillRect': ([w.HDC, ctypes.POINTER(w.RECT), w.HBRUSH], ctypes.c_int),
        'DrawTextW': ([w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(w.RECT), w.UINT], ctypes.c_int),
        'MonitorFromWindow': ([w.HWND, w.DWORD], w.HANDLE),
        'GetMonitorInfoW': ([w.HANDLE, ctypes.POINTER(MONITORINFO)], w.BOOL),
        'GetAncestor': ([w.HWND, w.UINT], w.HWND),
    }
    for name, (args, result) in signatures.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    for name, args, result in (
            ('CreateSolidBrush', [w.DWORD], w.HBRUSH), ('DeleteObject', [w.HANDLE], w.BOOL),
            ('CreateCompatibleDC', [w.HDC], w.HDC), ('DeleteDC', [w.HDC], w.BOOL),
            ('SelectObject', [w.HDC, w.HANDLE], w.HANDLE), ('SetBkMode', [w.HDC, ctypes.c_int], ctypes.c_int),
            ('SetTextColor', [w.HDC, w.DWORD], w.DWORD),
            ('CreateFontW', [ctypes.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR], w.HFONT)):
        function = getattr(gdi, name)
        function.argtypes, function.restype = args, result
    kernel.GetModuleHandleW.argtypes, kernel.GetModuleHandleW.restype = [w.LPCWSTR], w.HMODULE

    @proc
    def callback(hwnd, message, wp, lp):
        if message == 0x84:  # WM_NCHITTEST: never be a mouse target.
            return -1  # HTTRANSPARENT; layered transparency also crosses threads.
        if message == 0x21:  # WM_MOUSEACTIVATE
            return 3  # MA_NOACTIVATE
        if message == 0x14:  # WM_ERASEBKGND: paint owns the whole surface.
            return 1
        overlay = _windows.get(hwnd)
        if message == 0xF and overlay is not None:  # WM_PAINT
            overlay.paint()
            return 0
        return user.DefWindowProcW(hwnd, message, wp, lp)

    instance = kernel.GetModuleHandleW(None)
    registration = WNDCLASS(0, callback, 0, 0, instance, None, None, None, None, _class_name)
    if not user.RegisterClassW(ctypes.byref(registration)):
        raise ctypes.WinError(ctypes.get_last_error())
    _callback = callback
    _api = user, gdi, instance
    return _api


class NativeOverlay:
    def __init__(self):
        self.user, self.gdi, instance = api()
        self.text, self.font = '', None
        self.background, self.foreground = '#171e29', '#e7edf7'
        self.key = None
        self.font_key, self.measure_key, self.text_height = None, None, 0
        self.runs = []
        # Hidden at creation. Unowned, so minimizing the main window cannot hide
        # it. Disabled provides an extra barrier against all keyboard/input use.
        self.hwnd = self.user.CreateWindowExW(EX_STYLES, _class_name, 'Neutron Planner information',
                    0x80000000 | 0x08000000, 0, 0, 1, 1, None, None, instance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _windows[self.hwnd] = self

    def show(self, text, config, palette, parent_hwnd, dpi, family):
        work = MONITORINFO()
        work.size = ctypes.sizeof(work)
        parent = self.user.GetAncestor(parent_hwnd, 2)  # GA_ROOT
        monitor = self.user.MonitorFromWindow(parent, 2)  # nearest monitor
        if not self.user.GetMonitorInfoW(monitor, ctypes.byref(work)):
            raise ctypes.WinError(ctypes.get_last_error())
        bounds = (work.work.left, work.work.top, work.work.right, work.work.bottom)
        pixel = max(12, round(config['font_size'] * dpi / 72))
        scale = dpi / 96
        width = min(round(560 * scale), max(1, bounds[2] - bounds[0]))
        if (pixel, family) != self.font_key:
            new_font = self.gdi.CreateFontW(-pixel, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, family)
            if not new_font:
                raise ctypes.WinError(ctypes.get_last_error())
            if self.font:
                self.gdi.DeleteObject(self.font)
            self.font, self.font_key = new_font, (pixel, family)
        colours = tuple(sorted(getattr(text, 'line_colours', {}).items()))
        if (text, colours, width, pixel, family) != self.measure_key:
            dc = self.gdi.CreateCompatibleDC(None)
            if not dc:
                raise ctypes.WinError(ctypes.get_last_error())
            previous = self.gdi.SelectObject(dc, self.font)
            try:
                self.runs = []
                for index, line in enumerate(text.splitlines()):
                    rectangle = w.RECT(0, 0, max(1, width - 28), 0)
                    self.user.DrawTextW(dc, line or ' ', -1, ctypes.byref(rectangle), 0x400 | 0x10 | 0x800 | 0x40)
                    self.runs.append((line, dict(colours).get(index), rectangle.bottom - rectangle.top))
                self.text_height = sum(run[2] for run in self.runs)
                self.measure_key = (text, colours, width, pixel, family)
            finally:
                self.gdi.SelectObject(dc, previous)
                self.gdi.DeleteDC(dc)
        height = self.text_height + 24
        geometry = placement(bounds, (width, height), config)
        key = (text, colours, tuple(sorted(config.items())), palette['surface'], palette['text'], geometry, pixel, family)
        if key != self.key:
            self.text, self.background, self.foreground = text, palette['surface'], palette['text']
            if not self.user.SetLayeredWindowAttributes(self.hwnd, 0, round(config['opacity'] * 255 / 100), 2):
                raise ctypes.WinError(ctypes.get_last_error())
            # HWND_TOPMOST, SWP_NOACTIVATE | SWP_SHOWWINDOW.
            if not self.user.SetWindowPos(self.hwnd, w.HWND(-1), *geometry, 0x10 | 0x40):
                raise ctypes.WinError(ctypes.get_last_error())
            self.user.InvalidateRect(self.hwnd, None, False)
            self.key = key
        else:
            self.user.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE, never Tk lift/focus.

    def hide(self):
        if self.hwnd:
            self.user.ShowWindow(self.hwnd, 0)

    def paint(self):
        ps, rectangle = PAINTSTRUCT(), w.RECT()
        dc = self.user.BeginPaint(self.hwnd, ctypes.byref(ps))
        brush, previous = None, None
        try:
            self.user.GetClientRect(self.hwnd, ctypes.byref(rectangle))
            brush = self.gdi.CreateSolidBrush(_colour(self.background))
            self.user.FillRect(dc, ctypes.byref(rectangle), brush)
            if self.font:
                previous = self.gdi.SelectObject(dc, self.font)
            self.gdi.SetBkMode(dc, 1)  # TRANSPARENT text background.
            rectangle.left += 14
            rectangle.top += 10
            rectangle.right -= 14
            rectangle.bottom -= 10
            bottom = rectangle.bottom
            for line, colour, height in self.runs:
                if rectangle.top >= bottom:
                    break
                rectangle.bottom = min(bottom, rectangle.top + height)
                self.gdi.SetTextColor(dc, _colour(colour or self.foreground))
                self.user.DrawTextW(dc, line, -1, ctypes.byref(rectangle), 0x10 | 0x800 | 0x40)
                rectangle.top += height
        finally:
            if previous:
                self.gdi.SelectObject(dc, previous)
            if brush:
                self.gdi.DeleteObject(brush)
            self.user.EndPaint(self.hwnd, ctypes.byref(ps))

    def close(self):
        if self.hwnd:
            handle = self.hwnd
            self.user.DestroyWindow(handle)
            _windows.pop(handle, None)
            self.hwnd = None
        if self.font:
            self.gdi.DeleteObject(self.font)
            self.font = None


class OverlayController:
    """Main-window controls and main-thread refresh; overlay has no controls."""
    def __init__(self, parent, app, get_text, native_factory=NativeOverlay):
        self.app, self.parent, self.get_text, self.factory = app, parent, get_text, native_factory
        self.native, self.timer, self.closed = None, None, False
        self.enabled = tk.BooleanVar(parent, value=False)
        self.notice = tk.StringVar(parent)
        self.variables = {key: tk.StringVar(parent, value=(CORNERS[value] if key == 'corner' else str(value)))
                          for key, value in app.overlay_settings.items()}
        frame = ttk.LabelFrame(parent, text='只读信息悬浮窗', padding=8)
        frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=8)
        ttk.Checkbutton(frame, text='显示悬浮窗（鼠标穿透）', variable=self.enabled,
                        command=self.refresh, state='normal' if sys.platform == 'win32' else 'disabled').grid(
                            row=0, column=0, columnspan=4, sticky='w')
        for column, (key, label) in enumerate((('corner', '屏幕位置'), ('font_size', '字号'), ('opacity', '不透明度 %'))):
            ttk.Label(frame, text=label).grid(row=1, column=column * 2, sticky='w')
            widget = (ttk.Combobox(frame, textvariable=self.variables[key], values=list(CORNERS.values()),
                                   state='readonly', width=14) if key == 'corner' else
                      ttk.Entry(frame, textvariable=self.variables[key], width=8))
            widget.grid(row=1, column=column * 2 + 1, padx=6, pady=4, sticky='w')
        for column, (key, label) in enumerate((('margin_x', '水平边距 px'), ('margin_y', '垂直边距 px'))):
            ttk.Label(frame, text=label).grid(row=2, column=column * 2, sticky='w')
            ttk.Entry(frame, textvariable=self.variables[key], width=8).grid(row=2, column=column * 2 + 1,
                                                                           padx=6, pady=4, sticky='w')
        ttk.Button(frame, text='应用悬浮窗设置', command=self.apply).grid(row=2, column=4, columnspan=2, padx=6)
        ttk.Label(frame, text='位置以主窗口所在屏幕为准；悬浮窗不可点击或拖动。仅窗口化／无边框模式可用，独占全屏不保证显示。',
                  wraplength=1000, style='Muted.TLabel').grid(row=3, column=0, columnspan=6, sticky='w')
        ttk.Label(frame, textvariable=self.notice, wraplength=1000, style='Warning.TLabel').grid(
            row=4, column=0, columnspan=6, sticky='w')
        app.localizer.register(self.refresh)
        self.timer = parent.after(500, self.tick)

    def apply(self):
        try:
            config = {key: int(variable.get()) for key, variable in self.variables.items() if key != 'corner'}
            config['corner'] = next(key for key, value in CORNERS.items() if value == self.variables['corner'].get())
            if settings(config) != config:
                raise ValueError
        except (ValueError, StopIteration):
            self.notice.set(self.app.localizer.tr('悬浮窗设置无效：字号 10–28，不透明度 35–100，边距 0–2000。'))
            return
        self.app.overlay_settings = config
        self.notice.set('')
        self.refresh()

    def refresh(self):
        if self.closed:
            return
        if not self.enabled.get():
            if self.native is not None:
                self.native.hide()
            return
        try:
            if self.native is None:
                self.native = self.factory()
            text = self.get_text()
            if text is None:
                self.native.hide()
                return
            family = font.nametofont('TkDefaultFont', root=self.app.root).actual('family')
            dpi = min(384, max(72, self.app.root.winfo_fpixels('1i')))
            self.native.show(text, self.app.overlay_settings, self.app.appearance_manager.palette,
                             self.app.root.winfo_id(), dpi, family)
        except (OSError, AttributeError, tk.TclError):
            # Fail closed: never fall back to a normal clickable Tk window.
            self.enabled.set(False)
            if self.native is not None:
                self.native.close()
                self.native = None
            self.notice.set(self.app.localizer.tr('无法创建安全的鼠标穿透悬浮窗，已关闭。'))

    def tick(self):
        self.refresh()
        self.timer = self.parent.after(500, self.tick)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.parent.after_cancel(self.timer)
        self.app.localizer.callbacks.discard(self.refresh)
        if self.native is not None:
            self.native.close()
            self.native = None

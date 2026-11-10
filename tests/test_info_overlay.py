import ctypes
from ctypes import wintypes as w
import sys
import unittest

from info_overlay import DEFAULTS, EX_STYLES, HEALTH_COLOURS, NativeOverlay, OverlayText, health_colour, overlay_text, placement, settings
from appearance import PALETTES


class OverlayModelTests(unittest.TestCase):
    def test_health_thresholds_include_80_and_85_in_yellow(self):
        for value in (.85001, .99, 1):
            self.assertEqual(health_colour(value), HEALTH_COLOURS['green'])
        for value in (.8, .80001, .84, .85):
            self.assertEqual(health_colour(value), HEALTH_COLOURS['yellow'])
        for value in (0, .79999, .5):
            self.assertEqual(health_colour(value), HEALTH_COLOURS['red'])
        for value in (None, True, '85', -1, 85, float('nan')):
            self.assertIsNone(health_colour(value))

    def test_health_line_has_its_own_colour_and_snapshot_time(self):
        from journal_health import FsdHealth
        info = dict(complete=True, rows=[dict(name='A'), dict(name='B')])
        health = FsdHealth(.85, '2026-10-23T10:00:00Z', 1, 'asp')
        text = overlay_text(info, 0, True, '2026-10-23T12:00:00Z', lambda x: x, health)
        index = next(i for i, line in enumerate(text.splitlines()) if 'FSD 耐久' in line)
        self.assertIn('85%', text.splitlines()[index])
        self.assertEqual(text.line_colours, {index: HEALTH_COLOURS['yellow']})
        self.assertIn('耐久记录时间: 2026-10-23T10:00:00Z', text)
        unknown = overlay_text(info, 0, True, '', lambda x: x)
        self.assertIn('FSD 耐久（日志快照）: 情况未知', unknown)
        self.assertEqual(unknown.line_colours, {})
    def test_settings_are_bounded_and_never_restore_enabled(self):
        self.assertEqual(settings(None), DEFAULTS)
        self.assertEqual(settings(dict(enabled=True, font_size=True, opacity=0, corner='bad')), DEFAULTS)
        self.assertEqual(settings(dict(corner=[])), DEFAULTS)
        config = settings(dict(font_size=20, opacity=50, corner='bottom_left'))
        self.assertEqual(config['font_size'], 20)
        self.assertNotIn('enabled', config)

    def test_placement_handles_negative_monitors_and_clamps_large_margins(self):
        config = dict(DEFAULTS, corner='top_right', margin_x=20, margin_y=30)
        self.assertEqual(placement((-1920, 0, 0, 1080), (500, 200), config), (-520, 30, 500, 200))
        config.update(corner='bottom_left', margin_x=2000, margin_y=2000)
        self.assertEqual(placement((-1920, 0, 0, 1080), (500, 200), config), (-500, 0, 500, 200))
        self.assertEqual(placement((0, 0, 300, 200), (560, 400), DEFAULTS), (0, 0, 300, 200))

    def test_model_is_passive_uses_original_order_and_hides_unknown_position(self):
        info = dict(complete=True, rows=[dict(name='Z', departure_ship='Outbound ship', must_refuel=True),
                                         dict(name='B', distance=100), dict(name='A', distance=90)])
        text = overlay_text(info, 0, True, 'stamp', lambda x: x)
        self.assertIn('计划下一跳: B', text)
        self.assertIn('本段配船: Outbound ship', text)
        self.assertIn('需要补油', text)
        self.assertIn('100.00 ly', text)
        self.assertIn('日志时间: stamp', text)
        self.assertIsNone(overlay_text(info, None, True, '', lambda x: x))
        self.assertIn('请在主窗口开启', overlay_text(info, None, False, '', lambda x: x))

    def test_terminal_and_partial_import_warnings_never_invent_next_jump(self):
        info = dict(complete=False, imported=True, rows=[dict(name='Only row')])
        text = overlay_text(info, 0, True, '', lambda x: x)
        self.assertIn('CSV 文件末尾', text)
        self.assertNotIn('计划下一跳:', text)
        self.assertNotIn('已到达终点', text)
        info.update(imported=False)
        self.assertIn('路线未完成', overlay_text(info, 0, True, '', lambda x: x))
        info['complete'] = True
        self.assertIn('已到达终点', overlay_text(info, 0, True, '', lambda x: x))


@unittest.skipUnless(sys.platform == 'win32', 'Win32 overlay safety checks')
class NativeOverlayTests(unittest.TestCase):
    def test_visible_window_is_clickthrough_noactivate_unowned_and_disabled(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        overlay = NativeOverlay()
        user = overlay.user
        for name, args, result in (
                ('GetForegroundWindow', [], w.HWND), ('IsWindowVisible', [w.HWND], w.BOOL),
                ('IsWindowEnabled', [w.HWND], w.BOOL), ('IsWindow', [w.HWND], w.BOOL),
                ('GetWindowLongW', [w.HWND, ctypes.c_int], w.LONG),
                ('GetWindow', [w.HWND, w.UINT], w.HWND),
                ('GetWindowRect', [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
                ('WindowFromPoint', [w.POINT], w.HWND),
                ('SendMessageW', [w.HWND, w.UINT, w.WPARAM, w.LPARAM], ctypes.c_ssize_t)):
            function = getattr(user, name)
            function.argtypes, function.restype = args, result
        try:
            before = user.GetForegroundWindow()
            overlay.show('Native read-only test', DEFAULTS, PALETTES['dark'], root.winfo_id(), 96, 'Segoe UI')
            root.update()
            self.assertTrue(user.IsWindowVisible(overlay.hwnd))
            self.assertEqual(user.GetForegroundWindow(), before)
            self.assertEqual(user.GetWindowLongW(overlay.hwnd, -20) & EX_STYLES, EX_STYLES)
            self.assertFalse(user.IsWindowEnabled(overlay.hwnd))
            self.assertFalse(user.GetWindow(overlay.hwnd, 4))  # GW_OWNER: no minimize coupling.
            rectangle = w.RECT()
            self.assertTrue(user.GetWindowRect(overlay.hwnd, ctypes.byref(rectangle)))
            point = w.POINT((rectangle.left + rectangle.right) // 2, (rectangle.top + rectangle.bottom) // 2)
            self.assertNotEqual(user.WindowFromPoint(point), overlay.hwnd)
            self.assertEqual(user.SendMessageW(overlay.hwnd, 0x84, 0, 0), -1)  # HTTRANSPARENT
            self.assertEqual(user.SendMessageW(overlay.hwnd, 0x21, 0, 0), 3)  # MA_NOACTIVATE
            overlay.hide()
            self.assertFalse(user.IsWindowVisible(overlay.hwnd))
            overlay.show('Native read-only test', DEFAULTS, PALETTES['dark'], root.winfo_id(), 96, 'Segoe UI')
            self.assertTrue(user.IsWindowVisible(overlay.hwnd))
            overlay.show('Updated text', dict(DEFAULTS, opacity=50), PALETTES['light'], root.winfo_id(), 96, 'Segoe UI')
            overlay.show(OverlayText('Route\nFSD: 79%', {1: HEALTH_COLOURS['red']}),
                         DEFAULTS, PALETTES['dark'], root.winfo_id(), 96, 'Segoe UI')
            root.update()
            self.assertEqual(overlay.runs[1][1], HEALTH_COLOURS['red'])
            self.assertEqual(user.GetForegroundWindow(), before)
            handle = overlay.hwnd
            overlay.close()
            self.assertFalse(user.IsWindow(handle))
            overlay.close()
        finally:
            overlay.close()
            root.destroy()

"""Offline GUI, theme, settings restart and DPI verification for source/frozen builds."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

def run(report_path):
    from planner_app import App, tk
    import route_tool
    from ui_display import process_dpi_awareness
    from export_metadata import PROJECT_NAME, PROJECT_VERSION
    report = dict(ok=False, frozen=bool(getattr(sys, 'frozen', False)),
                  project=PROJECT_NAME, version=PROJECT_VERSION)
    previous = os.environ.get('ELITE_NEUTRON_DATA_DIR')
    root = None
    try:
        with tempfile.TemporaryDirectory() as directory, patch.object(route_tool.Favorites, 'load', return_value={}):
            os.environ['ELITE_NEUTRON_DATA_DIR'] = directory
            root = tk.Tk()
            root.withdraw()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(str(args[1]))
            app = App(root)
            win = app.route_window(as_root=True)
            assert win is root
            win.route_variables['destination'].set('Alpha Centauri')
            win.route_variables['cargo'].set('17')
            win.route_state['points'] = ['Lave']
            win.render_points()
            assert not win.waypoint_tree._sortable
            for mode in ('dark', 'light', 'system', 'dark'):
                app.set_appearance(mode)
            app.set_language('en')
            assert 'Neutron' in root.title()
            assert not errors, errors
            app.close()
            root = tk.Tk()
            root.withdraw()
            app = App(root)
            win = app.route_window(as_root=True)
            assert app.localizer.language == 'en'
            assert app.appearance_manager.mode == 'dark'
            assert win.route_variables['cargo'].get() == '17'
            assert win.route_variables['destination'].get() == 'Alpha Centauri'
            assert win.route_state['points'] == ['Lave']
            report['dpi_awareness'] = process_dpi_awareness()
            if sys.platform == 'win32':
                assert report['dpi_awareness'] in (1, 2)
            if report['frozen']:
                assert (Path(sys._MEIPASS) / 'LICENSE').is_file()
            report['ok'] = True
            app.close()
            root = None
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        if previous is None:
            os.environ.pop('ELITE_NEUTRON_DATA_DIR', None)
        else:
            os.environ['ELITE_NEUTRON_DATA_DIR'] = previous
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1

"""Standalone desktop host for the extracted neutron planner."""
import argparse
import tkinter as tk
from tkinter import filedialog
from appearance import Appearance, MODES
from export_metadata import PROJECT_VERSION
from i18n import Localizer
from localized_tk import ttk, messagebox
from runtime_paths import data_file
import session_store
from ui_display import initialize_display

class App:
    def __init__(self, root):
        self.root, self.window = root, None
        self.settings = session_store.load(data_file('settings.json'))
        self.localizer = Localizer(root, self.settings.get('language', 'zh'))
        self.appearance_manager = Appearance(root, self.settings.get('appearance', 'system'))
        header = ttk.Frame(root, padding=8)
        header.pack(fill='x')
        ttk.Label(header, text='中子星跳跃规划器', style='Header.TLabel').pack(side='left')
        ttk.Button(header, text='语言 / Language', command=lambda: self.set_language(
            'en' if self.localizer.language == 'zh' else 'zh')).pack(side='right', padx=4)
        self.appearance_choice = tk.StringVar(root, value=MODES[self.appearance_manager.mode])
        box = ttk.Combobox(header, textvariable=self.appearance_choice,
                           values=list(MODES.values()), state='readonly', width=12)
        box.pack(side='right', padx=4)
        box.bind('<<ComboboxSelected>>', lambda event: self.set_appearance(
            next(key for key, value in MODES.items() if value == self.appearance_choice.get())))
        ttk.Button(header, text='导入旧版舰船收藏', command=self.import_legacy).pack(side='right', padx=4)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.set_language(self.localizer.language)

    def set_language(self, language):
        self.localizer.set_language(language)
        self.root.title(self.localizer.tr('中子星跳跃规划器') + ' — v' + PROJECT_VERSION)

    def set_appearance(self, mode):
        self.appearance_manager.set_mode(mode)
        self.appearance_choice.set(MODES[self.appearance_manager.mode])

    def route_window(self, as_root=False):
        if self.window is not None and self.window.winfo_exists():
            return self.window
        from route_gui import open_window
        self.window = open_window(self, self.root if as_root else None)
        saved = self.settings.get('route', {})
        if isinstance(saved, dict):
            for key, variable in self.window.route_variables.items():
                if key in saved and isinstance(saved[key], (str, bool)):
                    variable.set(saved[key])
        points = self.settings.get('waypoints', [])
        if isinstance(points, list) and all(isinstance(name, str) for name in points):
            self.window.route_state['points'] = points[:100]
            self.window.render_points()
        if as_root:
            self.set_language(self.localizer.language)
        return self.window

    def import_legacy(self):
        path = filedialog.askopenfilename(parent=self.root,
            title=self.localizer.tr('导入旧版舰船收藏'), filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            from migration import import_favorites
            count = import_favorites(path)
            if self.window is not None:
                self.window.reload_favorites()
            messagebox.showinfo('导入完成', str(count), parent=self.root)
        except (ValueError, OSError) as exc:
            messagebox.showerror('操作失败', str(exc), parent=self.root)

    def close(self):
        settings = dict(language=self.localizer.language, appearance=self.appearance_manager.mode)
        if self.window is not None and self.window.winfo_exists():
            settings['route'] = {key: variable.get() for key, variable in self.window.route_variables.items()}
            settings['waypoints'] = list(self.window.route_state['points'])
        session_store.save(data_file('settings.json'), settings)
        self.root.destroy()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', metavar='REPORT')
    args = parser.parse_args()
    initialize_display()
    if args.smoke_test:
        from smoke_test import run
        return run(args.smoke_test)
    root = tk.Tk()
    app = App(root)
    app.route_window(as_root=True)
    root.mainloop()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

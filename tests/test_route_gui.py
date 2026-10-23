import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_route_tool import build, FSDS, Server
import route_tool as tool
import route_ship
from destination_favorites import DestinationFavorites
from route_history import RouteHistory


@unittest.skipUnless(sys.platform == 'win32' or os.environ.get('DISPLAY'), 'Requires a GUI display')
class RouteGuiTests(unittest.TestCase):
    def setUp(self):
        import planner_app as gui
        self.gui = gui
        self.root = gui.tk.Tk()
        self.root.withdraw()
        self.app = gui.App(self.root)
        self.app.settings = {}
        self.app.set_language('zh')
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args[1]))
        self.directory = tempfile.TemporaryDirectory()
        self.store = tool.Favorites(str(Path(self.directory.name) / 'ships.json'))
        self.factory = patch.object(tool, 'Favorites', return_value=self.store)
        self.factory.start()
        self.destinations = DestinationFavorites(str(Path(self.directory.name) / 'destinations.json'))
        self.destination_factory = patch('route_gui.DestinationFavorites', return_value=self.destinations)
        self.destination_factory.start()
        self.history_store = RouteHistory(str(Path(self.directory.name) / 'history.json'))
        self.history_factory = patch('route_gui.RouteHistory', return_value=self.history_store)
        self.history_factory.start()
        self.catalog = patch.object(route_ship, 'catalog', return_value=FSDS)
        self.catalog.start()

    def tearDown(self):
        import gc
        for callback in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            self.root.tk.call('after', 'cancel', callback)
        self.root.destroy()
        gc.collect()
        self.factory.stop()
        self.destination_factory.stop()
        self.history_factory.stop()
        self.catalog.stop()
        self.directory.cleanup()
        self.assertEqual(self.errors, [])

    def widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self.widgets(child)

    def test_single_page_reaches_results_at_smaller_sizes(self):
        window = self.app.route_window()
        for size in ('1400x850', '1100x700'):
            window.geometry(size)
            window.deiconify()
            self.root.update()
            self.assertTrue(window.page_canvas.winfo_ismapped())
            window.page_canvas.yview_moveto(1)
            self.root.update()
            self.assertTrue(window.result_tree.winfo_ismapped())
            self.assertGreater(window.result_tree.winfo_height(), 100)
            self.assertGreater(window.page_canvas.yview()[0], 0)
            self.assertFalse(window.waypoint_tree._sortable)
            window.page_canvas.yview_moveto(0)

    def test_single_page_structure_and_wheel_do_not_change_combobox_values(self):
        from types import SimpleNamespace
        win = self.app.route_window()
        self.assertFalse(any(isinstance(w, self.gui.ttk.Panedwindow) for w in self.widgets(win)))
        self.assertIs(win.page_form.master, win.page_content)
        self.assertIs(win.page_results.master, win.page_content)
        self.assertEqual(win.page_content.pack_slaves(), [win.page_form, win.page_results])
        combo = next(w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Combobox))
        tag = win.page_form.bindtags()[0]
        self.assertEqual(combo.bindtags()[0], tag)
        self.assertEqual(win.result_tree.bindtags()[0], tag)
        win.page_canvas.configure(scrollregion=(0, 0, 1000, 5000))
        win.page_canvas.yview_moveto(0)
        previous = combo.get()
        before = win.page_canvas.yview()[0]
        self.assertEqual(win.scroll_page(SimpleNamespace(widget=combo, delta=-120, state=0)), 'break')
        self.assertGreater(win.page_canvas.yview()[0], before)
        self.assertEqual(combo.get(), previous)
        before = win.page_canvas.yview()[0]
        win.scroll_page(SimpleNamespace(widget=win.result_tree, delta=-120, state=0))
        self.assertGreater(win.page_canvas.yview()[0], before)
        editor = win.build_editor()
        self.assertNotEqual(editor.json_text.bindtags()[0], tag)
        editor.destroy()

    def test_result_height_grows_but_long_routes_remain_bounded(self):
        from test_route_history import result
        win = self.app.route_window()
        info = result()
        info['rows'] = [dict(name=f'System {i}', full_tank_start=False) for i in range(15)]
        win.route_state['info'] = info
        win.render_results()
        self.assertEqual(int(win.result_tree.cget('height')), 15)
        info['rows'] *= 10
        win.render_results()
        self.assertEqual(int(win.result_tree.cget('height')), 25)
        self.assertEqual(len(win.result_tree.get_children()), 150)

    def wait_for(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.02)
        self.assertTrue(condition())

    def test_selection_shows_identity_ranges_cargo_and_language(self):
        data = build()
        data['data'].update(Ship='asp', ShipName='Explorer One', ShipIdent='AB-12')
        self.store.put('First', json.dumps(data))
        win = self.app.route_window()
        self.wait_for(lambda: win.ship_preview['params'] is not None)
        texts = win.ship_summary_variables
        self.assertIn('Asp Explorer', texts['identity'].get())
        self.assertIn('Explorer One', texts['identity'].get())
        self.assertNotIn('AB-12', texts['identity'].get())
        self.assertIn('普通满油跳距', texts['ranges'].get())
        self.assertNotIn('×', texts['ranges'].get())
        self.assertEqual(set(texts), {'identity', 'ranges'})
        before = texts['ranges'].get()
        win.route_variables['cargo'].set('25')
        self.assertNotEqual(before, texts['ranges'].get())
        win.route_variables['cargo'].set('bad')
        self.assertIn('无法计算', texts['ranges'].get())
        win.route_variables['cargo'].set('0')
        self.app.set_language('en')
        self.assertIn('Normal full-tank range', texts['ranges'].get())
        self.assertIn('Neutron-supercharged range', texts['ranges'].get())
        self.assertIn('Explorer One', texts['identity'].get())
        self.assertEqual(self.store.load()['First'], json.dumps(data))
        win.route_variables['selected'].set('missing')
        self.assertEqual(texts['ranges'].get(), '')

    def test_preview_failure_and_late_result_do_not_show_wrong_ship(self):
        first, second = build(), build()
        first['data'].update(Ship='asp', UnladenMass=300)
        second['data'].update(Ship='mandalay', UnladenMass=200)
        self.store.put('First', json.dumps(first))
        self.store.put('Second', json.dumps(second))
        started, release = threading.Event(), threading.Event()
        parse = route_ship.parse_ship
        def delayed(raw, fsds):
            if json.loads(raw)['data']['Ship'] == 'asp':
                started.set()
                release.wait(4)
            return parse(raw, fsds)
        with patch.object(route_ship, 'parse_ship', side_effect=delayed):
            win = self.app.route_window()
            try:
                self.wait_for(started.is_set)
                win.route_variables['selected'].set('Second')
                self.wait_for(lambda: win.ship_preview['params'] is not None)
                self.assertEqual(win.ship_preview['params']['base_mass'], 200.63)
            finally:
                release.set()
        self.wait_for(lambda: 'Mandalay' in win.ship_summary_variables['identity'].get())
        win.route_variables['selected'].set('First')
        self.wait_for(lambda: win.ship_preview['params'] is not None and win.ship_preview['params']['base_mass'] == 300.63)
        with patch.object(route_ship, 'parse_ship', side_effect=ValueError('Unsupported FSD')):
            win.route_variables['selected'].set('Second')
            self.wait_for(lambda: bool(win.ship_preview['error']))
        self.assertIn('Unsupported FSD', win.ship_summary_variables['ranges'].get())

    def test_build_editor_waypoint_order_and_bilingual_results(self):
        win = self.app.route_window()
        editor = win.build_editor()
        editor.name_variable.set('Explorer')
        editor.json_text.insert('1.0', json.dumps(build()))
        editor.save_build()
        self.assertEqual(win.route_variables['selected'].get(), 'Explorer')
        buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Button)}
        for point in ('C', 'B'):
            win.route_variables['waypoint'].set(point)
            buttons['添加途经点'].invoke()
        win.waypoint_tree.selection_set('1')
        buttons['上移'].invoke()
        self.assertEqual(win.route_state['points'], ['B', 'C'])
        buttons['删除途经点'].invoke()
        self.assertEqual(win.route_state['points'], ['C'])
        buttons['删除途经点'].invoke()
        win.route_variables['source'].set('A')
        win.route_variables['destination'].set('B')
        original = tool.plan
        def offline(raw, points, options, stop, progress):
            return original(raw, points, options, stop, progress, http=Server(), fsds=FSDS)
        with patch.object(tool, 'plan', side_effect=offline):
            buttons['规划航线'].invoke()
            deadline = time.monotonic() + 4
            while win.route_state['busy'] and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.02)
        self.assertTrue(win.route_state['info']['complete'])
        self.assertEqual(len(win.result_tree.get_children()), 2)
        win.result_tree.selection_set('1')
        buttons['复制星系名'].invoke()
        self.assertEqual(win.clipboard_get(), 'B')
        self.app.set_language('en')
        self.assertEqual(win.title(), 'Neutron jump planner')
        self.assertIn('full tank', win.result_tree.item('0', 'values')[-1])
        path = str(Path(self.directory.name) / 'route.csv')
        with patch('route_gui.filedialog.asksaveasfilename', return_value=path):
            buttons['导出 CSV'].invoke()
        self.assertIn('Jump distance ly', Path(path).read_text(encoding='utf-8-sig'))

    def test_editor_actions_have_fixed_row_and_pasted_replacement_is_saved(self):
        old = build()
        self.store.put('Explorer', json.dumps(old))
        win = self.app.route_window()
        editor = win.build_editor('Explorer')
        self.assertEqual(int(editor.action_frame.grid_info()['row']), 3)
        self.assertEqual(int(editor.json_frame.grid_info()['row']), 2)
        self.assertEqual(int(editor.grid_rowconfigure(2)['weight']), 1)
        self.assertEqual(int(editor.grid_rowconfigure(3)['weight']), 0)
        self.assertEqual(editor.json_text.cget('wrap'), 'none')
        for size in ('850x570', '640x400'):
            editor.geometry(size)
            self.root.update_idletasks()
            self.assertEqual(editor.action_frame.winfo_manager(), 'grid')
        new = build()
        new['data']['UnladenMass'] = old['data']['UnladenMass'] - 20
        editor.json_text.delete('1.0', 'end')
        editor.json_text.insert('1.0', json.dumps(new))
        with patch('route_gui.messagebox.askyesno', return_value=True):
            editor.save_build()
        self.assertEqual(json.loads(self.store.load()['Explorer'])['data']['UnladenMass'], new['data']['UnladenMass'])
        self.assertEqual(win.route_variables['selected'].get(), 'Explorer')

    def test_multileg_warning_can_cancel_before_network(self):
        self.store.put('Explorer', json.dumps(build()))
        win = self.app.route_window()
        win.route_variables['destination'].set('C')
        win.route_state['points'][:] = ['B']
        button = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '规划航线')
        with patch('route_gui.messagebox.askyesno', return_value=False) as warning, patch.object(tool, 'plan') as plan:
            button.invoke()
        warning.assert_called_once()
        plan.assert_not_called()
        self.assertFalse(win.route_state['busy'])

    def test_destination_favorites_save_reuse_rename_delete_and_language(self):
        win = self.app.route_window()
        buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Button)}
        win.route_variables['destination'].set(' Colonia ')
        with patch('route_gui.simpledialog.askstring', return_value='探索基地'), patch.object(tool, 'plan') as plan:
            buttons['收藏当前终点'].invoke()
            plan.assert_not_called()
        self.assertEqual(self.destinations.load(), {'探索基地': 'Colonia'})
        self.assertEqual(win.destination_favorite_variable.get(), '探索基地')
        win.route_variables['destination'].set('Sol')
        buttons['设为终点'].invoke()
        self.assertEqual(win.route_variables['destination'].get(), 'Colonia')
        self.app.set_language('en')
        self.assertEqual(buttons['收藏当前终点'].cget('text'), 'Save current destination')
        with patch('route_gui.simpledialog.askstring', return_value='Home'):
            buttons['重命名目的地'].invoke()
        self.assertEqual(self.destinations.load(), {'Home': 'Colonia'})
        # Reloading persisted favourites never replaces an edited destination.
        win.route_variables['destination'].set('Sirius')
        win.reload_destinations()
        self.assertEqual(win.route_variables['destination'].get(), 'Sirius')
        with patch('route_gui.messagebox.askyesno', return_value=False):
            buttons['删除目的地'].invoke()
        self.assertEqual(self.destinations.load(), {'Home': 'Colonia'})
        with patch('route_gui.messagebox.askyesno', return_value=True):
            buttons['删除目的地'].invoke()
        self.assertEqual(self.destinations.load(), {})
        self.assertEqual(win.destination_favorite_variable.get(), '')

    def test_destination_favorites_reject_conflict_and_cancel_save(self):
        self.destinations.put('Home', 'Sol')
        win = self.app.route_window()
        buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Button)}
        win.route_variables['destination'].set('Colonia')
        with patch('route_gui.simpledialog.askstring', return_value='home'), patch('route_gui.messagebox.showerror') as error:
            buttons['收藏当前终点'].invoke()
            error.assert_called_once()
        with patch('route_gui.simpledialog.askstring', return_value=None):
            buttons['收藏当前终点'].invoke()
        self.assertEqual(self.destinations.load(), {'Home': 'Sol'})

    def test_recent_results_duplicate_guard_and_restore_after_restart(self):
        from test_route_history import result
        self.store.put('Explorer', json.dumps(build()))
        win = self.app.route_window()
        win.route_variables['source'].set('A')
        win.route_variables['destination'].set('B')
        button = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '规划航线')
        with patch.object(tool, 'plan', side_effect=lambda *args: result()) as plan:
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            button.invoke()
            self.assertEqual(plan.call_count, 1)
            self.app.set_language('en')
            self.app.set_appearance('dark')
            button.invoke()
            self.assertEqual(plan.call_count, 1)
            win.route_variables['cargo'].set('1')
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            self.assertEqual(plan.call_count, 2)
            win.route_variables['cargo'].set('0')
            button.invoke()
            self.assertFalse(win.route_state['busy'])
            self.assertEqual(plan.call_count, 2)
            self.assertIsNotNone(win.route_state['cached_at'])
            win.route_variables['cargo'].set('1')
            button.invoke()
            self.assertFalse(win.route_state['busy'])
            self.assertEqual(plan.call_count, 2)
            # A build edited under the same name is a new request.
            data = build()
            data['data']['ShipName'] = 'Changed build'
            self.store.put('Explorer', json.dumps(data), replace=True)
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            self.assertEqual(plan.call_count, 3)
        self.assertEqual(len(self.history_store.load()), 3)
        win.destroy()
        win = self.app.route_window()
        self.assertEqual(len(win.history_chooser.cget('values')), 3)
        win.history_chooser.current(0)
        restore = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '查看历史结果')
        restore.invoke()
        self.assertEqual(win.route_variables['cargo'].get(), '1')
        self.assertEqual(win.route_variables['destination'].get(), 'B')
        self.assertTrue(win.route_state['info']['complete'])
        button = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '规划航线')
        with patch.object(tool, 'plan') as plan:
            button.invoke()
            plan.assert_not_called()

    def test_failed_request_can_retry_and_history_saves_submitted_not_edited_inputs(self):
        from test_route_history import result
        self.store.put('Explorer', json.dumps(build()))
        win = self.app.route_window()
        win.route_variables['destination'].set('B')
        button = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '规划航线')
        with patch.object(tool, 'plan', side_effect=lambda *args: result(False)) as plan:
            button.invoke()
            win.route_variables['destination'].set('edited while busy')
            self.wait_for(lambda: not win.route_state['busy'])
            self.assertEqual(self.history_store.load()[0]['parameters']['destination'], 'B')
            win.route_variables['destination'].set('B')
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            self.assertEqual(plan.call_count, 2)
        self.assertFalse(self.history_store.load()[0]['result']['complete'])

    def test_retry_of_incomplete_current_result_does_not_use_older_success(self):
        from test_route_history import result
        self.store.put('Explorer', json.dumps(build()))
        win = self.app.route_window()
        win.route_variables['destination'].set('B')
        button = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '规划航线')
        with patch.object(tool, 'plan', side_effect=lambda *args: result()) as plan:
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            # A displayed interrupted attempt must remain eligible for an actual
            # retry, even when the history contains a matching earlier success.
            win.route_state['info'] = result(False)
            button.invoke()
            self.wait_for(lambda: not win.route_state['busy'])
            self.assertEqual(plan.call_count, 2)

    def test_neutron_highlight_survives_sort_language_and_theme(self):
        from test_route_history import result
        win = self.app.route_window()
        info = result()
        info['rows'].extend([dict(name='B', has_neutron=False, full_tank_start=False),
                             dict(name='C', has_neutron=None, full_tank_start=False)])
        win.route_state['info'] = info
        win.render_results()
        for language, theme in (('zh', 'light'), ('en', 'dark')):
            self.app.set_language(language)
            self.app.set_appearance(theme)
            win.result_tree.sort_by('name')
            self.root.update()
            self.assertIn('neutron', win.result_tree.item('0', 'tags'))
            self.assertNotIn('neutron', win.result_tree.item('1', 'tags'))
            self.assertNotIn('neutron', win.result_tree.item('2', 'tags'))
            self.assertEqual(str(win.result_tree.tag_configure('neutron', 'background')),
                             self.app.appearance_manager.palette['neutron_bg'])

    def test_journal_button_is_explicit_local_and_preserves_other_route_inputs(self):
        from journal_location import JournalLocation
        suggest_patch = patch('suggestion_ui.suggest_systems', return_value=[])
        suggest = suggest_patch.start()
        self.addCleanup(suggest_patch.stop)
        with patch('journal_location.read_current_system') as read:
            win = self.app.route_window()
            self.root.update()
            read.assert_not_called()
        buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Button)}
        win.route_variables['destination'].set('Colonia')
        win.route_state['points'] = ['Sirius']
        source_box = next(w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Combobox)
                          and getattr(w, '_model', None) is win.route_variables['source'])
        found = JournalLocation('Achenar', '2026-10-23T12:00:00Z', 'Journal.test.01.log')
        with patch('journal_location.read_current_system', return_value=found) as read, \
                patch.object(tool, 'plan') as plan, patch.object(source_box, 'focus_get', return_value=source_box):
            buttons['使用当前星系'].invoke()
            self.wait_for(lambda: not win.journal_state['busy'])
            elapsed = []
            self.root.after(300, lambda: elapsed.append(True))
            self.wait_for(lambda: bool(elapsed))
            self.assertEqual(win.route_variables['source'].get(), 'Achenar')
            read.assert_called_once()
            plan.assert_not_called()
            suggest.assert_not_called()
        self.assertEqual(win.route_variables['destination'].get(), 'Colonia')
        self.assertEqual(win.route_state['points'], ['Sirius'])
        self.assertIn('2026-10-23', win.journal_status.get())
        self.app.set_language('en')
        self.assertEqual(buttons['使用当前星系'].cget('text'), 'Use current system')
        self.assertIn('Journal position', win.journal_status.get())

    def test_journal_folder_selection_cancel_and_errors_do_not_overwrite_source(self):
        from journal_location import JournalLocation
        win = self.app.route_window()
        buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win) if isinstance(w, self.gui.ttk.Button)}
        with patch('route_gui.filedialog.askdirectory', return_value=''), patch('journal_location.read_current_system') as read:
            buttons['选择游戏日志文件夹'].invoke()
            read.assert_not_called()
        original = win.route_variables['source'].get()
        with patch('route_gui.filedialog.askdirectory', return_value=self.directory.name), \
                patch('journal_location.read_current_system', side_effect=ValueError('No location')), \
                patch('route_gui.messagebox.showerror') as error:
            buttons['选择游戏日志文件夹'].invoke()
            self.wait_for(lambda: not win.journal_state['busy'])
            self.assertEqual(self.app.journal_directory, self.directory.name)
            self.assertEqual(win.route_variables['source'].get(), original)
            error.assert_called_once()
        with patch('journal_location.read_current_system', return_value=JournalLocation('Sol', 'time', 'file')):
            buttons['使用当前星系'].invoke()
            win.route_variables['source'].set('Edited while reading')
            self.wait_for(lambda: not win.journal_state['busy'])
            self.assertEqual(win.route_variables['source'].get(), 'Edited while reading')

    def follow_window(self, names, complete=True):
        from test_route_history import result
        win = self.app.route_window()
        info = result(complete)
        info['rows'] = [dict(name=name, full_tank_start=False, has_neutron=(index == 0))
                        for index, name in enumerate(names)]
        win.route_state['info'] = info
        win.render_results()
        return win

    def feed_position(self, win, system, timestamp='2026-10-23T12:00:00Z'):
        from journal_location import JournalLocation
        win.follow_state['location'] = JournalLocation(system, timestamp, 'Journal.synthetic.01.log')
        win.refresh_follow()

    def test_follow_markers_and_copy_use_canonical_order_without_repainting_or_scroll(self):
        win = self.follow_window(['Z', 'B', 'A'])
        self.assertFalse(win.follow_variables['enabled'].get())
        self.assertFalse(win.follow_variables['auto_copy'].get())
        win.follow_variables['enabled'].set(True)
        with patch.object(win, 'clipboard_clear') as clear, patch.object(win, 'clipboard_append') as append, \
                patch.object(win.result_tree, 'insert') as insert, patch.object(win.result_tree, 'see') as see, \
                patch.object(tool, 'plan') as plan:
            self.feed_position(win, 'Z')
            append.assert_not_called()
            self.assertIn('route_current', win.result_tree.item('0', 'tags'))
            win.follow_variables['auto_copy'].set(True)
            win.refresh_follow()
            append.assert_called_once_with('B')
            win.result_tree.sort_by('name')
            self.root.update_idletasks()
            self.assertEqual(win.result_tree.get_children()[0], '2')
            self.feed_position(win, 'B', '2026-10-23T12:01:00Z')
            self.assertEqual(append.call_args.args, ('A',))
            self.assertEqual(append.call_count, 2)
            self.assertNotIn('route_current', win.result_tree.item('0', 'tags'))
            self.assertIn('neutron', win.result_tree.item('0', 'tags'))
            self.assertIn('route_current', win.result_tree.item('1', 'tags'))
            self.feed_position(win, 'Not on route', '2026-10-23T12:02:00Z')
            self.assertEqual(win.follow_text.get(), '')
            self.assertFalse(any('route_current' in win.result_tree.item(i, 'tags') for i in ('0', '1', '2')))
            self.assertEqual(append.call_count, 2)
            self.feed_position(win, 'B', '2026-10-23T12:03:00Z')
            self.assertEqual(append.call_count, 2)
            self.feed_position(win, 'A', '2026-10-23T12:04:00Z')
            self.assertIn('已到达终点', win.follow_text.get())
            self.assertEqual(clear.call_count, 2)
            insert.assert_not_called()
            see.assert_not_called()
            plan.assert_not_called()
        self.app.set_language('en')
        self.app.set_appearance('dark')
        self.assertIn('Destination reached', win.follow_text.get())
        self.assertIn('route_current', win.result_tree.item('2', 'tags'))
        self.assertEqual(str(win.result_tree.tag_configure('route_current', 'background')),
                         self.app.appearance_manager.palette['current_bg'])

    def test_follow_ambiguous_position_needs_matching_selected_row(self):
        win = self.follow_window(['A', 'B', 'A', 'C'])
        win.follow_variables['enabled'].set(True)
        win.follow_variables['auto_copy'].set(True)
        confirm = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '确认所选位置')
        with patch.object(win, 'clipboard_clear'), patch.object(win, 'clipboard_append') as append:
            self.feed_position(win, 'A')
            self.assertIsNone(win.follow_position.index)
            append.assert_not_called()
            win.result_tree.selection_set('1')
            confirm.invoke()
            append.assert_not_called()
            win.result_tree.selection_set('2')
            confirm.invoke()
            self.assertEqual(win.follow_position.index, 2)
            append.assert_called_once_with('C')
            win.refresh_follow()
            self.assertEqual(append.call_count, 1)

    def test_follow_clipboard_failure_can_retry_and_partial_end_is_not_destination(self):
        win = self.follow_window(['A', 'B'], complete=False)
        win.follow_variables['enabled'].set(True)
        win.follow_variables['auto_copy'].set(True)
        with patch.object(win, 'clipboard_clear', side_effect=[self.gui.tk.TclError('busy'), None]), \
                patch.object(win, 'clipboard_append') as append:
            self.feed_position(win, 'A')
            self.assertFalse(win.follow_position.copied)
            append.assert_not_called()
            win.refresh_follow()
            append.assert_called_once_with('B')
            self.feed_position(win, 'B', '2026-10-23T12:01:00Z')
            self.assertIn('路线未完成', win.follow_text.get())
            self.assertNotIn('已到达终点', win.follow_text.get())
            self.assertEqual(append.call_count, 1)

    def test_follow_worker_requires_opt_in_and_stops_without_late_updates(self):
        from journal_location import JournalLocation
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        def blocked_poll():
            entered.set()
            release.wait(3)
            returned.set()
            return JournalLocation('A', '2026-10-23T12:00:00Z', 'Journal.synthetic.01.log')
        with patch('journal_location.JournalFollower') as factory:
            factory.return_value.poll.side_effect = blocked_poll
            win = self.follow_window(['A', 'B'])
            factory.assert_not_called()
            follow = next(w for w in self.widgets(win) if getattr(w, '_raw_text', '') == '跟随游戏位置')
            with patch.object(win, 'clipboard_clear') as clear, patch.object(win, 'clipboard_append') as append:
                try:
                    follow.invoke()
                    self.assertTrue(entered.wait(2))
                    old_stop = win.follow_state['stop']
                    follow.invoke()
                    self.assertTrue(old_stop.is_set())
                finally:
                    release.set()
                self.assertTrue(returned.wait(2))
                self.root.update()
                self.assertIsNone(win.follow_state['location'])
                self.assertEqual(win.follow_text.get(), '')
                clear.assert_not_called()
                append.assert_not_called()

    def test_follow_worker_delivers_confirmed_position_without_network(self):
        from journal_location import JournalLocation
        with patch('journal_location.JournalFollower') as factory, patch.object(tool, 'plan') as plan:
            factory.return_value.poll.return_value = JournalLocation('A', '2026-10-23T12:00:00Z', 'Journal.synthetic.01.log')
            win = self.follow_window(['A', 'B'])
            buttons = {getattr(w, '_raw_text', ''): w for w in self.widgets(win)}
            with patch.object(win, 'clipboard_clear'), patch.object(win, 'clipboard_append') as append:
                buttons['跟随游戏位置'].invoke()
                self.wait_for(lambda: win.follow_state['location'] is not None)
                append.assert_not_called()
                buttons['自动复制计划下一跳'].invoke()
                append.assert_called_once_with('B')
                stopped = win.follow_state['stop']
                buttons['跟随游戏位置'].invoke()
                self.assertTrue(stopped.is_set())
                self.assertEqual(append.call_count, 1)
            plan.assert_not_called()

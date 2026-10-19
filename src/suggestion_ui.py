"""Reusable autocomplete UI extracted from the filter, without filter dependencies."""
import queue
import sys
import threading
import tkinter as tk
from localized_tk import ttk, Toplevel
from system_names import suggest_systems

def ui_dispatcher(widget):
    """主线程初始化；后台线程只入队，所有 Tk 调用由主线程执行。"""
    root = widget._root()
    if hasattr(root, "_ui_post"):
        return root._ui_post
    pending = queue.Queue()

    def post(owner, callback, *args):
        pending.put((owner, callback, args))

    def drain():
        for _ in range(100):
            try:
                owner, callback, args = pending.get_nowait()
            except queue.Empty:
                break
            if owner.winfo_exists():
                try:
                    callback(*args)
                except Exception:
                    root.report_callback_exception(*sys.exc_info())
        root.after(30, drain)

    root._ui_post = post
    root.after(30, drain)
    return post


class SuggestPopup:
    """单例: 在输入框下方弹出候选列表 (Inara式联想)。
    焦点始终留在输入框, 上下键移动高亮, 回车/Tab/点击选中, Esc关闭。"""
    _inst = None

    @classmethod
    def inst(cls):
        if cls._inst is None:
            cls._inst = SuggestPopup()
        return cls._inst

    def __init__(self):
        self.win = None
        self.lb = None
        self.on_pick = None
        self.anchor = None

    def visible_for(self, widget):
        return self.win is not None and self.anchor is widget

    def show(self, widget, items, on_pick):
        self.hide()
        items = [i for i in items if i][:8]
        if not items or not widget.winfo_exists():
            return
        try:
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
        except tk.TclError:
            return
        self.on_pick = on_pick
        self.anchor = widget
        self.win = tk.Toplevel(widget)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry(f"+{x}+{y}")
        self.win.lift()
        self.lb = tk.Listbox(self.win, height=len(items),
                             width=max(16, min(44, max(len(s) for s in items) + 2)))
        self.lb.pack()
        for it in items:
            self.lb.insert("end", it)
        self.lb.selection_set(0)
        self.lb.bind("<ButtonPress-1>", self._pick)

    def _pick(self, event):
        """Select the clicked row before class bindings can move focus."""
        if self.lb is not None:
            index = self.lb.nearest(event.y)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(index)
            self.pick_current()
        return "break"

    def move(self, delta):
        if not self.lb or not self.win:
            return False
        sel = self.lb.curselection()
        i = (sel[0] if sel else (-1 if delta > 0 else self.lb.size())) + delta
        i = max(0, min(self.lb.size() - 1, i))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        return True

    def pick_current(self):
        if not self.lb or not self.win:
            return False
        sel = self.lb.curselection()
        vals = [self.lb.get(i) for i in (sel or (0,))]
        if not vals:
            return False
        cb, val = self.on_pick, vals[0]
        self.hide()
        if cb:
            cb(val)
        return True

    def hide(self, widget=None):
        if widget is not None and self.anchor is not widget:
            return
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self.lb = None
        self.on_pick = None
        self.anchor = None


def attach_system_suggest(cb, textvar, suggest=None, feedback=None):
    post = ui_dispatcher(cb)
    """给任意星系输入框接下方候选弹窗 (打字即弹, 上下选, 回车/点击确认)。"""
    state = {"seq": 0, "hits": [], "selecting": False, "last_text": textvar.get()}
    provider = suggest or suggest_systems
    pop = SuggestPopup.inst()

    def pick(val):
        cancel_timer()
        state["seq"] += 1
        state["selecting"] = True
        try:
            textvar.set(val)
            state["last_text"] = val
        finally:
            state["selecting"] = False
        if feedback:
            feedback.set("已选择完整名称")

    def cancel_timer():
        if state.get("timer"):
            try:
                cb.after_cancel(state["timer"])
            except tk.TclError:
                pass
            state["timer"] = None

    def on_key(event):
        if event.keysym in ("Down", "Up"):
            if pop.visible_for(cb):
                pop.move(1 if event.keysym == "Down" else -1)
                return
            if state["hits"]:
                pop.show(cb, state["hits"], pick)
            else:
                schedule()
            return
        if event.keysym in ("Return", "Tab"):
            if pop.visible_for(cb) and pop.pick_current():
                return
            return
        if event.keysym == "Escape":
            state["seq"] += 1
            pop.hide(cb)
            cancel_timer()
            return
        if textvar.get() != state["last_text"]:
            changed()

    def schedule():
        cancel_timer()
        state["seq"] += 1
        state["hits"] = []
        cb["values"] = []
        pop.hide(cb)
        text = textvar.get()
        state["last_text"] = text
        seq = state["seq"]
        if len(text.strip()) < 2:
            if feedback:
                feedback.set("输入至少两个字符联想；选择候选后使用完整名称。")
            return
        if feedback:
            feedback.set("正在查询名称候选…")

        def fire():
            state["timer"] = None

            def work():
                error = None
                try:
                    sug = provider(text)
                except Exception as exc:
                    sug, error = [], str(exc)

                def apply():
                    if seq != state["seq"] or text != textvar.get() or not cb.winfo_exists():
                        return
                    state["hits"] = sug
                    if feedback:
                        feedback.set("名称联想失败；可继续手动输入完整名称。" if error else
                                     ("输入至少两个字符联想；选择候选后使用完整名称。" if len(text.strip()) < 2 else
                                      ("请选择候选完整名称；不自动改写输入。" if sug else
                                       "未找到名称候选；不代表该派系不存在。")))
                    cb["values"] = sug
                    if sug:
                        try:
                            focused = cb.focus_get() == cb
                        except tk.TclError:
                            focused = False
                        if focused:
                            pop.show(cb, sug, pick)
                    else:
                        pop.hide(cb)
                post(cb, apply)
            threading.Thread(target=work, daemon=True).start()

        try:
            state["timer"] = cb.after(250, fire)
        except tk.TclError:
            pass

    def changed(*args):
        if state["selecting"] or textvar.get() == state["last_text"]:
            return
        state["last_text"] = textvar.get()
        state["seq"] += 1
        state["hits"] = []
        cancel_timer()
        if cb.focus_get() == cb:
            schedule()
        else:
            cb["values"] = []
            pop.hide(cb)

    trace = textvar.trace_add("write", changed)
    cb.bind("<KeyRelease>", on_key)
    cb.bind("<<ComboboxSelected>>", lambda e: pick(textvar.get()))
    def blur(event):
        def check():
            state["blur_timer"] = None
            if not cb.winfo_exists():
                return
            focus = cb.focus_get()
            if focus != cb and focus != pop.lb:
                pop.hide(cb)
        if state.get("blur_timer"):
            cb.after_cancel(state["blur_timer"])
        state["blur_timer"] = cb.after(100, check)
    cb.bind("<FocusOut>", blur)

    def destroyed(event):
        if event.widget is cb:
            state["seq"] += 1
            cancel_timer()
            if state.get("blur_timer"):
                cb.after_cancel(state["blur_timer"])
            textvar.trace_remove("write", trace)
            pop.hide(cb)
    cb.bind("<Destroy>", destroyed, add="+")
    cb.configure(postcommand=schedule)
    return state

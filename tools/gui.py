#!/usr/bin/env python3
"""Drag-and-drop patcher: drop a Tetris Party Deluxe disc image on the window, done.

Extracts the disc, patches its own main.dol for the options you tick, and
rebuilds the image in the same format.  The rebuilt image replaces the original
in place (USB loaders key off the `/wbfs/<Title> [ID6]/` layout) and the
untouched original is kept alongside as `<name>.bak`.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disc
import features

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except ImportError:                                    # fall back to click-to-browse
    HAVE_DND = False


def asset(name):
    if getattr(sys, 'frozen', False):
        return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'assets', name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', name)


BASE = TkinterDnD.Tk if HAVE_DND else tk.Tk


class App(BASE):
    def __init__(self):
        super().__init__()
        self.title('Tetris Party Deluxe Patcher')
        self.geometry('620x600')
        self.msgq = queue.Queue()
        self.busy = False

        try:
            from PIL import Image, ImageTk
            orig = Image.open(asset('logo.png'))
            target_w = 320
            target_h = int(orig.height * (target_w / orig.width))
            resized = orig.resize((target_w, target_h), Image.Resampling.LANCZOS)
            self.logo = ImageTk.PhotoImage(resized)
            tk.Label(self, image=self.logo).pack(pady=(10, 0))
        except Exception:
            try:
                img = tk.PhotoImage(file=asset('logo.png'))
                factor = max(1, img.width() // 320)
                self.logo = img.subsample(factor, factor)
                tk.Label(self, image=self.logo).pack(pady=(10, 0))
            except Exception:
                pass
        tk.Label(self, text='Tetris Party Deluxe  -  USA / Europe / Japan',
                 font=('Helvetica', 12, 'bold')).pack(pady=(4, 6))


        opts = tk.LabelFrame(self, text='Patches')
        opts.pack(fill='x', padx=10)
        self.gc = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text='GameCube controller (ports 1-4, Classic Controller mapping)',
                       variable=self.gc).pack(anchor='w')

        hint = ('Drop a .wbfs or .iso here\n\n(or click to choose one)'
                if HAVE_DND else 'Click to choose a .wbfs or .iso')
        self.drop = tk.Label(self, text=hint, relief='ridge', bd=2, padx=10, pady=24, cursor='hand2')
        self.drop.pack(fill='x', padx=10, pady=10)
        self.drop.bind('<Button-1>', lambda e: self.pick())
        if HAVE_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)

        tk.Label(self, text='The original is kept alongside as <name>.bak', fg='#666').pack()

        self.log = tk.Text(self, height=10, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        self.after(100, self.poll_queue)

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)          # handles {braced paths with spaces}
        if paths:
            self.start(paths[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(title='Select disc image',
                                       filetypes=[('Wii disc image', '*.wbfs *.iso'), ('All files', '*')])
        if p:
            self.start(p)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'done':
                    self.busy = False
                    self.drop.configure(state='normal')
                    good, msg = payload
                    if good:
                        messagebox.showinfo('Patched', 'Rebuilt successfully:\n' + msg)
                    else:
                        messagebox.showerror('Failed', msg)
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def start(self, image_path):
        if self.busy:
            return
        which = []
        if self.gc.get():
            which.append('gc')
        if not which:
            messagebox.showwarning('Nothing selected', 'Tick at least one patch to apply.')
            return

        self.busy = True
        self.drop.configure(state='disabled')
        self.append_log('--- %s ---' % os.path.basename(image_path))

        def worker():
            disc.run_patch(image_path,
                           lambda text: self.msgq.put(('log', text)),
                           lambda good, msg: self.msgq.put(('done', (good, msg))),
                           which=which)
        threading.Thread(target=worker, daemon=True).start()


def main():
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()

# The MIT License (MIT)
# 
# Copyright (c) 2015 Josef Gajdusek
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import tty
import termios
import sys
import io
import threading
import time
from functools import wraps
from wytch import view, canvas, input, builder

class WytchExitError(RuntimeError):
    pass

class FlushThread(threading.Thread):

    def __init__(self, fps, buffer):
        super(FlushThread, self).__init__()
        self.fps = fps
        self.buffer = buffer
        self.shouldrun = True
        self.daemon = True

    def run(self):
        nxt = 0
        while self.shouldrun:
            self.buffer.flush()
            now = time.time()
            if now < nxt:
                time.sleep(nxt - now)
            nxt = time.time() + 1 / self.fps

class Wytch:

    def __init__(self, debug = False, ctrlc = True, buffer = False, fps = 60):
        self.debug = debug
        self.ctrlc = ctrlc
        self.buffer = buffer
        self.fps = fps
        self.flushthread = None

    def __enter__(self):
        self.consolecanvas = canvas.ConsoleCanvas()
        if self.buffer:
            rootcanvas = canvas.BufferCanvas(self.consolecanvas)
            self.flushthread = FlushThread(self.fps, rootcanvas)
        else:
            rootcanvas = self.consolecanvas

        self.realroot = view.ContainerView()
        self.root = self.realroot
        self.realroot.canvas = rootcanvas
        if self.debug:
            console = view.Console(minheight = 10)
            self.root = view.ContainerView()
            with builder.Builder(self.realroot) as b:
                b.vertical() \
                    .box("Console").add(console).end() \
                    .add(self.root)

            def _print(*args, sep = " ", end = "\n", file = sys.stdout, flush = False):
                s = ""
                for x in args[:-1]:
                    s += str(x) + sep
                if args:
                    s += str(args[-1]) + "\n"
                else:
                    s += "\n"
                for li in s.split("\n")[:-1]:
                    console.push(li)
            self.origprint = print
            __builtins__["print"] = _print
        return self

    def _cleanup(self):
        if self.debug:
            __builtins__["print"] = self.origprint
        if self.buffer:
            self.flushthread.shouldrun = False
            self.flushthread.join()
        self.consolecanvas.destroy()
        print() # Newline

    def exit(self):
        raise WytchExitError

    def __exit__(self, extype, exval, trace):
        if extype is not None:
            self._cleanup()
            return False
        # Input loop
        try:
            self.realroot.recalc()
            if self.root.focusable:
                self.root.focused = True
            self.realroot.render()
            if self.buffer:
                self.flushthread.start()
            while True:
                mouse = False
                try:
                    c = sys.stdin.read(1)
                except UnicodeDecodeError as ude: # UGLY EVIL EVIL!
                    # Mouse click escape sequences can contain invalid Unicode
                    mc = ude.object
                    mouse = True
                if not mouse:
                    if self.ctrlc and ord(c[0]) == 3:
                        raise KeyboardInterrupt
                    elif c == "\x1b": # TODO: handle ESC key press
                        # TODO: Figure out how much is this broken on terminals other than xfce4-terminal...
                        c += sys.stdin.read(1)
                        if c[-1] in ["[", "O"]: # CSI and SS3
                            c += sys.stdin.read(1)
                            if c[-1] == "M":
                                c += sys.stdin.read(3)
                                # Encode to bytes as MouseEvent expects that
                                mc = c.encode("utf-8")
                                mouse = True
                            else:
                                while ord(c[-1]) in range(ord("0"), ord("9") + 1):
                                    c += sys.stdin.read(1)
                                if c[-1] == ";":
                                    c += sys.stdin.read(1)
                                    while c[-1] in range(ord("0"), ord("9") + 1):
                                        c += sys.stdin.read(1)
                if mouse:
                    # And it's worse and worse...
                    while mc:
                        me = input.MouseEvent(mc[:6])
                        self.root.onmouse(me)
                        mc = mc[6:]
                elif self.root.focused:
                    kc = input.KeyEvent(c)
                    self.root.onevent(kc)
        except WytchExitError:
            pass
        finally:
            self._cleanup()

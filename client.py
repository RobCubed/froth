from tkinter import *
from tkinter import ttk
import tkinter.filedialog
import tkinter.messagebox
from fuzzywuzzy import process, fuzz
import ttkwidgets
import froth
import re
import time
import socket
import select
import uuid
import enum
import os

import frothtests

styleLoader = """
set base_theme_dir awthemes

package ifneeded awthemes 10.3.0 \
    [list source [file join $base_theme_dir awthemes.tcl]]
package ifneeded colorutils 4.8 \
    [list source [file join $base_theme_dir colorutils.tcl]]
package ifneeded awdark 7.11 \
    [list source [file join $base_theme_dir awdark.tcl]]
package ifneeded awlight 7.6 \
    [list source [file join $base_theme_dir awlight.tcl]]
"""
_STYLE = None

class NetworkErrors(enum.IntEnum):
    SUCCESS = -1
    DESTINATION_DOESNT_EXIST = -2
    NO_DATA_AVAILABLE = -3

    NETWORK_ERROR = -99


def wordBounds(editor):
    lineNum, pos = editor.index(INSERT).split(".")
    begin = int(editor.index("insert -1c wordstart").split(".")[1])
    end = int(editor.index("insert wordend").split(".")[1])
    if end == 0:
        end = int(pos)
    else:
        end -= 1
    return lineNum, begin, end

def getCurrentWord(editor):
    line, begin, end = wordBounds(editor)
    return editor.get(f"{line}.{begin}", f"{line}.{end}")


class StackViewer(ttk.LabelFrame):
    def __init__(self, master, size, **kw):
        ttk.LabelFrame.__init__(self, master, **kw)
        self.stack = []

        self.labelstack = [
            ttk.Label(self, text="---", width=11) for _ in range(size)
        ]
        for pos in range(len(self.labelstack)):
            self.labelstack[pos].grid(row=pos, column=0, sticky="new")

    def Refresh(self):
        i = len(self.stack) - 1
        for pos in range(len(self.labelstack)):
            self.labelstack[pos].config(text=f"---")
            try:
                if i >= 0:
                    self.labelstack[pos].config(text=f"#{i}> {self.stack[i]}")
                    i -= 1
            except IndexError:
                pass


class OutputWindow(Text):
    def __init__(self, master, *args, **kw):
        Text.__init__(self, master, *args, **kw)
        self.bind("<Key>", self.OnKey)
        self.queue = []


    def OnKey(self, event):
        self.write(chr(event.keycode))
        self.queue.append(event.keycode)
        return "break"

    def read(self, vm):
        "( -- keysym)"
        if self.queue:
            vm.stack.append(self.queue.pop(0))
        else:
            vm.stack.append(-1)

    def delchr(self, vm):
        "( -- )"
        self.delete("end-2c", END)

    def write(self, data):
        self.insert(END, data)

    def flush(self):
        pass


class Display(Canvas):
    def __init__(self, master, *args, **kw):
        Canvas.__init__(self, master, *args, **kw)

    def drawline(self, vm):
        "( x1 y1 x2 y2 -- )"
        stack = vm.stack
        y2, x2, y1, x1 = stack.pop(), stack.pop(), stack.pop(), stack.pop()
        stack.append(self.create_line((x1, y1, x2, y2)))

    def deleteline(self, vm):
        "( id -- )"
        self.delete(vm.stack.pop())


class DummyNet(object):
    def recv(self, vm):
        "( -- ...data sender length/err )"
        pass

    def send(self, vm):
        "( ...data length target -- returnCode )"
        pass

    def tick(self):
        pass


class Network(object):
    def __init__(self, conn: str, key: str):
        self.sock = None
        self.queue = []
        self.host, self.port = conn.split(":")
        self.key = key

        self.id = ""

        self.buf = b""
        self.connect()

    def connect(self):
        self.sock = socket.socket()
        self.sock.connect((self.host, int(self.port)))
        self.Send(self.key)

    def tick(self):
        if not self.id and len(self.queue) > 0 and len(self.queue[0]) == 1:
            pop = self.queue.pop(0)[0]
            self.id = int(pop)
        sel = select.select((self.sock, ), (), (), 0)[0]
        if not sel: return
        try:
            data = self.sock.recv(2048)
            self.buf += data
            tmp = self.buf.split(b"\n")
            self.buf = tmp.pop()
            for line in tmp:
                line = line.split()
                if len(line) == 1:
                    self.queue.append(line)
                    continue
                sender = int(line[0])
                stack = map(int, line[1:])
                stack = list(stack)
                length = len(stack)

                stack.append(sender)
                stack.append(length)
                self.queue.append(stack)

        except:
            self.connect()

    def recv(self, vm):
        "( -- ...data sender length/err )"
        if not self.queue:
            vm.stack.append(NetworkErrors.NO_DATA_AVAILABLE.value)
            return
        vm.stack += self.queue.pop(0)

    def send(self, vm):
        "( ...data length target -- returnCode )"
        target = vm.stack.pop()
        length = vm.stack.pop() * -1
        data = vm.stack[length:]
        vm.stack = vm.stack[:length]
        self.sock.send((f"{target} "+" ".join(map(str, data))).encode("utf8") +b"\n")
        time.sleep(1)
        response = self.sock.recv(3).rstrip()

        if len(response) != 2:
            return NetworkErrors.NETWORK_ERROR
        vm.stack.append(int(response))

    def Send(self, data):
        self.sock.send(b"%s\n" % data.encode("utf8"))


class Tooltip(Toplevel):
    ActiveTooltip = None

    @staticmethod
    def Clear():
        if Tooltip.ActiveTooltip:
            Tooltip.ActiveTooltip.destroy()
            Tooltip.ActiveTooltip = None

    def __init__(self, master, editor: Text, matches: list, x: int, y: int):
        Toplevel.__init__(self, master)
        self.list = Listbox(self, height=len(matches), bd=0, bg=_STYLE.lookup('TFrame', 'background'), fg="white")
        self.list.pack()
        self.matches = matches
        self.editor = editor
        for match in matches:
            self.list.insert(END, f"{match[0]} - {match[1]}")

        self.list.config(width=0)
        self.overrideredirect(1)
        self.update()
        self.geometry(f"+{x}+{y+48}")

        self.bind("<Escape>", lambda e: (self.destroy(), editor.focus_set()))
        self.bind("<Return>", self.Complete)
        self.bind("<Double-Button-1>", self.Complete)


        if Tooltip.ActiveTooltip:
            Tooltip.ActiveTooltip.destroy()
        Tooltip.ActiveTooltip = self


    def Complete(self, _):
        line, begin, end = wordBounds(self.editor)
        self.editor.delete(f"{line}.{begin}", f"{line}.{end}")
        self.editor.insert(f"{line}.{begin}", self.matches[self.list.index(ACTIVE)][0])
        self.destroy()

    def focus(self, arrow):
        self.list.focus_set()
        if arrow == "Up":
            self.list.selection_set(END)
        else:
            self.list.selection_set(0)


class EventText(Text): # https://stackoverflow.com/a/16375233
    def __init__(self, *args, **kwargs):
        Text.__init__(self, *args, **kwargs)


        # create a proxy for the underlying widget
        self._orig = self._w + "_orig"
        self.tk.call("rename", self._w, self._orig)
        self.tk.createcommand(self._w, self._proxy)

    def _proxy(self, *args):
        # let the actual widget perform the requested action
        cmd = (self._orig,) + args
        result = self.tk.call(cmd)

        # generate an event if something was added or deleted,
        if (args[0] in ("insert", "replace", "delete") or
            args[0:3] == ("set", "insert")):
            self.event_generate("<<Change>>", when="tail")
        elif args[0:2] == ("yview", "moveto") or args[0:2] == ("yview", "scroll") \
            or args[0:2] == ('mark', 'set'):
            self.event_generate("<<Scroll>>", when="tail")

        # return what the actual widget returned
        return result

class IDE(Tk):
    def __init__(self):
        Tk.__init__(self)
        self.wm_title("Froth")

        self.style = ttk.Style(self)
        global _STYLE
        _STYLE = self.style
        self.tk.eval(styleLoader)
        self.tk.call("package", "require", 'awdark')
        self.tk.call("package", "require", 'awlight')
        self.style.theme_use("awdark")
        self.configure(bg=self.style.lookup('TFrame', 'background'))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.activefile = ""


        editFrame = ttk.Frame(self)
        editFrame.grid(row=0, column=0, sticky=NSEW, columnspan=2)
        editFrame.rowconfigure(0, weight=1)
        editFrame.columnconfigure(1, weight=1)
        self.linecount = Text(editFrame, font=("TkFixedFont", 12),  bg="#282a36", fg="#8be9fd", width=4, maxundo=-1)
        self.linecount.tag_configure('line', justify='right')
        self.linecount.grid(row=0, column=0, sticky=NSEW)
        self.linecount.insert("0.0", "0", "line")
        self.linecount.config(state=DISABLED, selectbackground=self.linecount.cget('bg'), inactiveselectbackground=self.linecount.cget('bg'))

        self.editor = EventText(editFrame, font=("TkFixedFont", 12), bg="#282a36", fg="#8be9fd", insertbackground="white",
                           highlightcolor="#282a36", wrap="none")
        self.editor.tag_configure("number", foreground="#ffb86c")
        self.editor.tag_configure("builtin", foreground="#bd93f9")
        self.editor.tag_configure("macro", foreground="#f1fa8c")
        self.editor.tag_configure("comment", foreground="#6272a4", font=("TkFixedFont", 11, "italic"))
        yscroll = ttk.Scrollbar(editFrame, command=self.editor.yview)
        yscroll.grid(row=0, column=2, sticky=NS)
        self.editor["yscrollcommand"] = yscroll.set

        xscroll = ttk.Scrollbar(editFrame, command=self.editor.xview, orient=HORIZONTAL)
        xscroll.grid(row=1, column=1, sticky=EW)
        self.editor["xscrollcommand"] = xscroll.set


        self.editor.tag_configure("highlight", background="#44475a")
        self.editor.tag_configure("error", background="#ff5555")

        self.editor.bind("<Key>", self.Autocomplete)
        self.editor.bind("<<Change>>", self.OnEntry)
        self.editor.bind("<<Scroll>>", self.OnScroll)
        self.editor.bind("<Button-1>", self.Autocomplete)
        self.autocompleteBuffer = ""

        self.tags = ["number", "builtin", "macro"]

        self.editor.grid(row=0, column=1, sticky=NSEW)
        self.editor.insert("0.0", frothtests.DEMO)

        self.sidebar = ttk.Frame(self)
        self.sidebar.grid(row=0, column=2, sticky=N, padx=3)

        self.runButton = ttk.Button(self.sidebar, text="Run", command=self.Run)
        self.runButton.grid(row=0,column=1, sticky=EW)

        self.delaybarframe = ttk.LabelFrame(self.sidebar, text="Delay - 0.0")
        self.delaybar = ttkwidgets.TickScale(self.delaybarframe, from_=0, to=2, orient=HORIZONTAL, digits=1, resolution=0.1,
                                             command=self.UpdateDelay, showvalue=0)
        self.delaybar.pack(fill=BOTH, expand=1)
        self.delaybarframe.grid(row=1, column=1, sticky="new")

        self.errorlabel = ttk.Label(self.sidebar, text="")
        self.errorlabel.grid(row=4, column=1)

        self.network = DummyNet()

        networkFrame = ttk.LabelFrame(self.sidebar, text="Network settings")
        networkFrame.grid(row=6, column=1)
        self.netstring = ttk.Entry(networkFrame)
        self.netstring.insert(END, "localhost:1971")
        self.netstring.grid(row=0, column=1, sticky=NSEW)

        self.netpass = ttk.Entry(networkFrame)
        self.netpass.insert(END, uuid.getnode())
        self.netpass.grid(row=1, column=1, sticky=NSEW)

        self.netid = ttk.Label(networkFrame)
        self.netid.grid(row=2, column=0, sticky=NSEW)

        self.netconnect = ttk.Button(networkFrame, text="Connect", command=self.Connect)
        self.netconnect.grid(row=3, column=0, columnspan=2, sticky=NSEW)

        ttk.Label(networkFrame, text="Host:").grid(row=0, column=0, sticky=W)
        ttk.Label(networkFrame, text="Key:").grid(row=1, column=0, sticky=W)



        ttk.Separator(self.sidebar, orient=HORIZONTAL).grid(row=3, column=1, sticky=EW, pady=3)

        saveload = ttk.LabelFrame(self.sidebar, text="Save/Load")
        saveload.grid(row=7, column=1, sticky=EW)
        saveload.columnconfigure(0, weight=1)
        ttk.Button(saveload, text="New", command=self.NewFile).grid(row=0, column=0, sticky=EW)
        ttk.Button(saveload, text="Open", command=self.OpenFile).grid(row=1, column=0, sticky=EW)
        ttk.Button(saveload, text="Save", command=self.SaveFile).grid(row=2, column=0, sticky=EW)
        ttk.Button(saveload, text="Save As...", command=self.SaveAsFile).grid(row=3, column=0, sticky=EW)



        self.stackviewer = StackViewer(self, 8, text="Stack")
        self.stackviewer.grid(row=10, column=2, sticky=NSEW)

        self.terminal = OutputWindow(self, foreground="white", background="black", height=10, width=80)
        self.terminal.grid(row=10, column=0, sticky=NSEW)

        self.display = Display(self, height=64)
        self.display.grid(row=10, column=1, sticky=NSEW)

        self.builtinre = re.compile(f"\\b({'|'.join(froth.tokenMap.keys())}|;)\\b")
        self.macrore = re.compile("")
        self.commentre = re.compile("\( .+? \)")
        self.words = {}
        self.variables = {}
        self.vm = None


        refreshtime = time.time()


        self.tickdelaytime = self.delaybar.get()
        self.tickdelay = time.time() + self.tickdelaytime
        self.ret = froth.Errors.UNDEFINED
        # quick refresh because why not
        self.realTokenMap = {}
        self.Run()
        self.Stop()

        while 1:
            t = time.time()+0.033
            self.update()
            self.network.tick()

            time.sleep(max(0, time.time() - t))
            if self.vm and self.tickdelay < time.time():
                self.ret = self.vm.tick()
                self.stackviewer.Refresh()
                self.editor.tag_remove("highlight", "0.0", END)
                self.editor.tag_add("highlight", f"{self.vm.pc+1}.0", f"{self.vm.pc+1}.end")

                if self.ret != froth.Errors.SUCCESS and self.ret != froth.Errors.END_OF_PROGRAM:
                    self.editor.tag_add("error", f"{self.vm.pc+1}.0", f"{self.vm.pc+1}.end")
                    self.editor.see("%d.0"%(self.vm.pc+1))
                    self.Stop()
                elif self.ret == froth.Errors.END_OF_PROGRAM: self.Stop()
                self.tickdelay = time.time() + self.tickdelaytime
            if time.time() > refreshtime:
                self.FullRefresh()
                refreshtime = time.time() + 3

                if isinstance(self.network, Network):
                    self.netid.config(text=f"ID: {self.network.id}")

    def NewFile(self):

        if tkinter.messagebox.askokcancel("New File", "Delete all changes and create a new file?"):
            self.editor.delete("0.0", END)
            self.activefile = ""
            self.wm_title("Froth")

    def RefreshTitle(self):
        if self.activefile:
            self.wm_title(f"Froth - {os.path.basename(self.activefile)}")
        else:
            self.wm_title("Froth")

    def OpenFile(self):
        f = tkinter.filedialog.askopenfile(filetypes=[("Froth file", "*.froth"), ("All files", "*")])
        if f is None:
            return
        self.editor.delete("0.0", END)
        self.editor.insert(END, f.read())
        f.close()
        self.activefile = f.name
        self.RefreshTitle()


    def SaveFile(self):
        if not self.activefile:
            f = tkinter.filedialog.asksaveasfile(filetypes=[("Froth file", "*.froth"), ("All files", "*")])
            if f is None: return
            self.activefile = f.name
            self.RefreshTitle()
        else:
            f = open(self.activefile, "w")
        data = self.editor.get("0.0", END)
        f.write(data)
        f.close()


    def SaveAsFile(self):
        f = tkinter.filedialog.asksaveasfile(filetypes=[("Froth file", "*.froth"), ("All files", "*")])
        if f is None: return
        self.activefile = f.name
        data = self.editor.get("0.0", END)
        f.write(data)
        f.close()
        self.RefreshTitle()

    def OnScroll(self, e=""):
        self.linecount.yview_moveto(self.editor.yview()[0])

    def OnEntry(self, e=""):
        self.linecount.config(state=NORMAL)
        self.Highlight(self.editor.index(INSERT).split(".")[0])
        size = int(float(self.editor.index(END)) - 1)
        curlines = int(float(self.linecount.index(END)) - 1)
        if size == curlines:
            pass
        elif size > curlines:
            self.linecount.insert(END, "\n"+ ("\n".join(map(str, range(curlines, size)))), ("line",))
        else:
            self.linecount.delete(f"{size+1}.0", END)

        self.linecount.config(state=DISABLED)


    def Autocomplete(self, event):
        self.update()
        if event.keysym in ("Down", "Up"):
            if Tooltip.ActiveTooltip:
                Tooltip.ActiveTooltip.focus(event.keysym)
                return "break"
        else:
            self.editor.after(1, lambda: self._Autocomplete(event))

    def _Autocomplete(self, event):
        if event.char in ("", " ", "\r", "\n", "\x1b", "\x08") or event.type == EventType.FocusOut or event.type == EventType.ButtonPress:
            Tooltip.Clear()
        else:
            x,y,width,height = self.editor.bbox(INSERT)
            if not getCurrentWord(self.editor):
                Tooltip.Clear()
                return
            matches = process.extractBests(getCurrentWord(self.editor),
                                           self.realTokenMap.keys() ^ self.words.keys(),
                                           limit=5,
                                           scorer=fuzz.token_sort_ratio)
            if matches:
                xroot, yroot = self.winfo_x(), self.winfo_y()
                Tooltip(self.editor, self.editor, [
                        (x[0], self.realTokenMap[x[0]][0].__doc__ if x[0] in self.realTokenMap else self.words[x[0]])
                            for x in matches],
                        xroot + x, yroot + y)
            else:
                Tooltip.Clear()

    def Connect(self):
        self.network = Network(self.netstring.get(), self.netpass.get())
        self.network.tick()



    def UpdateDelay(self, value):
        value = round(float(value), 1)
        self.delaybarframe.config(text=f"Delay - {value}")
        self.tickdelaytime = value

    def Run(self):
        self.display.delete(ALL)
        self.editor.tag_remove("error", "0.0", END)
        self.editor.configure(state=DISABLED)
        self.terminal.delete("0.0", END)
        self.terminal.queue = []
        self.vm = froth.VM(self.editor.get("0.0", END), output=self.terminal, customWords={
            "drawline": (self.display.drawline, 0),
            "deleteline": (self.display.deleteline, 0),
            "recv": (self.network.recv, 0),
            "send": (self.network.send, 0),
            "delchr": (self.terminal.delchr, 0),
            "read": (self.terminal.read, 0),
        })
        self.realTokenMap = self.vm.tokens

        self.builtinre = re.compile(f"\\b({'|'.join(self.vm.tokens.keys())}|;)\\b")

        self.stackviewer.stack = self.vm.stack
        self.runButton.config(text="Stop", command=self.Stop)

    def Stop(self):
        self.editor.tag_remove("highlight", "0.0", END)
        self.editor.configure(state=NORMAL)
        self.errorlabel.config(text=f"End Code:\n{self.ret.name}")
        self.vm = None
        self.runButton.config(text="Run", command=self.Run)

    def FullRefresh(self):
        self.words = {
            x.name:"variable" for x in froth.Errors
        }
        self.words.update({

        })
        for macromatch in re.finditer(r"macro (\w+) (\( .*? \))?", self.editor.get("0.0", END)):
            self.words[macromatch.group(1)] = macromatch.group(2) or "Macro"
        self.macrore = re.compile(f"\\b({'|'.join(self.words.keys())})\\b")

        for varmatch in re.finditer(r"var (\w+)", self.editor.get("0.0", END)):
            self.words[varmatch.group(1)] = "variable"

        for line in range(int(self.editor.index(END).split(".")[0])):
            self.Highlight(line)

    def Highlight(self, line):
        for tag in self.tags:
            self.editor.tag_remove(tag, f"{line}.0", f"{line}.end")
        text = self.editor.get(f"{line}.0", f"{line}.end")
        for match in re.finditer(r"\b[0-9]+\b", text):
            self.editor.tag_add("number", f"{line}.{match.start()}", f"{line}.{match.end()}")
        for match in self.builtinre.finditer(text):
            self.editor.tag_add("builtin", f"{line}.{match.start()}", f"{line}.{match.end()}")
        for match in self.macrore.finditer(text):
            self.editor.tag_add("macro", f"{line}.{match.start()}", f"{line}.{match.end()}")
        for match in self.commentre.finditer(text):
            self.editor.tag_add("comment", f"{line}.{match.start()}", f"{line}.{match.end()}")



if __name__ == '__main__':
    IDE()
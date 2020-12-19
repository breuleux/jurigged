import code
import fnmatch
import importlib.util
import logging
import os
import runpy
import sys
import time

import blessed
from _frozen_importlib_external import (  # Is it OK to import this?
    SourceFileLoader,
)
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .codefile import CodeFile

log = logging.getLogger(__name__)
T = blessed.Terminal()


class ImportSniffer:
    """A spec finder that simply sniffs for attempted imports.

    Basically we install this at the front of sys.meta_path so that
    importlib.util.find_spec calls it, then we call find_spec
    ourselves to locate the file that's going to be read so that we
    know we have to cache its contents and watch for changes.
    """

    def __init__(self, report):
        self.working = False
        self.report = report

    def find_module(self, spec, path):
        if not self.working:
            self.working = True
            try:
                # We call find_spec ourselves to find out where the file is.
                # This will not cause an infinite loop because self.working
                # is True and we will not enter the conditional. I'm not
                # sure if it's dangerous to call find_spec within find_spec,
                # but it seems to work, so whatever.
                mspec = importlib.util.find_spec(spec, path)
                if isinstance(mspec.loader, SourceFileLoader):
                    self.report(mspec.name, mspec.origin)
            except Exception as exc:
                self.working = False
                return None
            self.working = False
        return None


def glob_watcher(pattern):
    if pattern.startswith("~"):
        pattern = os.path.expanduser(pattern)
    elif not pattern.startswith("/"):
        pattern = os.path.abspath(pattern)

    def watcher(filename):
        return fnmatch.fnmatch(filename, pattern)

    return watcher


class Collector:
    def __init__(self, filter=glob_watcher("./*.py")):
        self.observer = Observer()
        self.filter = filter
        self.sniffer = ImportSniffer(self.acquire)
        self.cache = {}
        for name, module in sys.modules.items():
            filename = getattr(module, "__file__", None)
            self.acquire(name, filename)

    def acquire(self, module_name, filename):
        if filename is not None and self.filter(filename):
            if os.path.exists(filename):
                try:
                    with open(filename) as f:
                        self.cache[filename] = (module_name, f.read())
                    JuriggedHandler(self, filename).schedule(self.observer)
                except Exception as exc:
                    log.error(
                        f"jurigged: Could not read {filename}", exc_info=exc
                    )

    def log(self, codefile, op, defn, success):
        paths = []
        curr = defn
        while curr and curr.name is not None:
            paths.append(curr.name)
            curr = curr.parent
        paths.append(codefile.module.__name__)
        path = ".".join(reversed(paths))
        if not success:
            print(T.bold_red(f"FAILED: {op} {path} @L{defn.firstlineno}"))
        elif op == "update":
            print(T.bold_yellow(f"{op} {path} @L{defn.firstlineno}"))
        elif op == "add":
            if defn.type == "statement":
                print(
                    T.bold_green(
                        f"run {path} @L{defn.firstlineno}: {defn.source}"
                    )
                )
            else:
                print(T.bold_green(f"{op} {path} @L{defn.firstlineno}"))
        elif op == "delete":
            if defn.type != "statement":
                print(T.bold_red(f"{op} {path} @L{defn.firstlineno}"))
        else:
            print(f"{op} {path} @L{defn.firstlineno}")

    def modify(self, path):
        assert path in self.cache
        cached = self.cache[path]
        if isinstance(cached, tuple):
            module_name, cached_source = cached
            if module_name not in sys.modules:
                return
            cached = CodeFile(path, source=cached_source, logger=self.log)
            cached.discover(sys.modules[module_name])
            self.cache[path] = cached
        cached.refresh()

    def start(self):
        sys.meta_path.insert(0, self.sniffer)
        self.observer.start()

    def stop(self):
        sys.meta_path.remove(self.sniffer)
        self.observer.stop()

    def join(self):
        self.observer.join()


class JuriggedHandler(FileSystemEventHandler):
    def __init__(self, collector, filename):
        self.collector = collector
        self.filename = filename
        self.mtime = 0
        print("WATCH", self.filename)

    def on_modified(self, event):
        mtime = os.path.getmtime(event.src_path)
        # The modified event sometimes fires twice for no reason
        # even though the mtime is the same
        if mtime != self.mtime:
            self.collector.modify(event.src_path)
            self.mtime = mtime

    def schedule(self, observer):
        observer.schedule(self, self.filename)


def watch(pattern="./*.py"):
    collector = Collector(glob_watcher(pattern))
    collector.start()
    return collector


def cli():
    if len(sys.argv) > 1:
        _, filename, *argv = sys.argv
        filename = os.path.abspath(filename)
        del sys.modules["__main__"]
        collector = Collector()
        collector.acquire("__main__", filename)
        collector.start()
        runpy.run_path(filename, run_name="__main__")
    else:
        collector = Collector()
        collector.start()
        code.interact()

import code
import logging
import os
import runpy
import sys
import traceback
from dataclasses import dataclass

import blessed
from ovld import ovld
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import codefile
from .registry import registry

log = logging.getLogger(__name__)
T = blessed.Terminal()


@dataclass
class WatchOperation:
    filename: str

    def __str__(self):
        return f"Watch {self.filename}"


@ovld
def default_logger(event: codefile.UpdateOperation):
    print(T.bold_yellow(str(event)))


@ovld
def default_logger(event: codefile.FailedUpdateOperation):
    print(T.bold_red(str(event)))


@ovld
def default_logger(event: codefile.AddOperation):
    print(T.bold_green(str(event)))


@ovld
def default_logger(event: codefile.DeleteOperation):
    if event.definition.type != "statement":
        print(T.bold_red(str(event)))


@ovld
def default_logger(event: WatchOperation):
    print(T.bold(str(event)))


@ovld
def default_logger(exc: Exception):
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    print(T.bold_red("".join(lines)))


@ovld
def default_logger(exc: SyntaxError):
    lines = traceback.format_exception(
        type(exc), exc, exc.__traceback__, limit=0
    )
    print(T.bold_red("".join(lines)))


@ovld
def default_logger(event: object):
    print(event)


class Watcher:
    def __init__(self, registry):
        self.observer = Observer()
        self.registry = registry
        self.registry.add_listener(self.on_prepare)

    def on_prepare(self, module_name, filename):
        JuriggedHandler(self, filename).schedule(self.observer)
        self.registry.log(WatchOperation(filename))

    def refresh(self, path):
        cf = self.registry.get(path)
        try:
            cf.refresh()
        except Exception as exc:
            self.registry.log(exc)

    def start(self):
        self.observer.start()

    def stop(self):
        self.observer.stop()

    def join(self):
        self.observer.join()


class JuriggedHandler(FileSystemEventHandler):
    def __init__(self, watcher, filename):
        self.watcher = watcher
        self.filename = filename
        self.mtime = 0

    def on_modified(self, event):
        mtime = os.path.getmtime(event.src_path)
        # The modified event sometimes fires twice for no reason
        # even though the mtime is the same
        if mtime != self.mtime:
            self.watcher.refresh(event.src_path)
            self.mtime = mtime

    def schedule(self, observer):
        observer.schedule(self, self.filename)


def watch(pattern="./*.py", logger=default_logger):
    registry.auto_register()
    registry.set_logger(logger)
    watcher = Watcher(registry)
    watcher.start()
    return watcher


def cli():
    registry.auto_register()
    registry.set_logger(default_logger)
    if len(sys.argv) > 1:
        _, filename, *argv = sys.argv
        filename = os.path.abspath(filename)
        del sys.modules["__main__"]
        watcher = Watcher(registry)
        registry.prepare("__main__", filename)
        watcher.start()
        runpy.run_path(filename, run_name="__main__")
    else:
        watcher = Watcher(registry)
        watcher.start()
        code.interact()

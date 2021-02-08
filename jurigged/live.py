import argparse
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
from .register import registry
from .utils import glob_filter

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


def conservative_logger(event):
    if isinstance(event, Exception):
        default_logger(event)


class Watcher:
    def __init__(self, registry):
        self.observer = Observer()
        self.registry = registry
        self.registry.precache_activity.register(self.on_prepare)

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


def watch(
    pattern="./*.py", logger=default_logger, registry=registry, autostart=True
):
    registry.auto_register(
        filter=glob_filter(pattern) if isinstance(pattern, str) else pattern
    )
    registry.set_logger(logger)
    watcher = Watcher(registry)
    if autostart:
        watcher.start()
    return watcher


def cli():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="Run a Python script so that it is live-editable."
    )
    parser.add_argument(
        "path", metavar="PATH", help="Path to the script to run", nargs="?"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show watched files and changes as they happen",
    )
    parser.add_argument(
        "--watch",
        "-w",
        metavar="PATH",
        help="Wildcard path/directory for which files to watch",
    )
    parser.add_argument(
        "-m",
        dest="module",
        metavar="MODULE",
        help="Module or module:function to run",
    )
    parser.add_argument(
        "rest", metavar="...", nargs=argparse.REMAINDER, help="Script arguments"
    )
    opts = parser.parse_args()

    pattern = glob_filter(opts.watch or ".")
    watch_args = {
        "pattern": pattern,
        "logger": default_logger if opts.verbose else conservative_logger,
    }

    if opts.module:
        watcher = watch(**watch_args)
        new_args = list(opts.rest)
        if opts.path is not None:
            new_args.insert(0, opts.path)
        sys.argv[1:] = new_args

        if ":" in opts.module:
            module, func = opts.module.split(":", 1)
            __import__(module, fromlist=[])
            getattr(sys.modules[module], func)()
        else:
            runpy.run_module(opts.module, run_name="__main__")

    elif opts.path:
        path = os.path.abspath(opts.path)
        watcher = watch(**watch_args, autostart=False)
        if pattern(path):
            # It won't auto-trigger through runpy, probably some idiosyncracy of
            # module resolution
            watcher.registry.prepare("__main__", path)
        watcher.start()
        sys.argv[1:] = opts.rest
        runpy.run_path(path, run_name="__main__")

    else:
        watch(**watch_args)
        code.interact()

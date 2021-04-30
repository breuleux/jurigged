import argparse
import code
import importlib
import logging
import os
import sys
import threading
import traceback
from dataclasses import dataclass
from types import ModuleType

import blessed
from ovld import ovld
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import codetools, runpy
from .register import registry
from .utils import glob_filter
from .version import version

log = logging.getLogger(__name__)
T = blessed.Terminal()
DEFAULT_DEBOUNCE = 0.05


@dataclass
class WatchOperation:
    filename: str

    def __str__(self):
        return f"Watch {self.filename}"


@ovld
def default_logger(event: codetools.UpdateOperation):
    if isinstance(event.defn, codetools.FunctionDefinition):
        print(T.bold_yellow(str(event)))


@ovld
def default_logger(event: codetools.AddOperation):
    print(T.bold_green(str(event)))


@ovld
def default_logger(event: codetools.DeleteOperation):
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
    def __init__(self, registry, debounce=DEFAULT_DEBOUNCE):
        self.observer = Observer()
        self.registry = registry
        self.registry.precache_activity.register(self.on_prepare)
        self.debounce = debounce

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
        self.timer = None

    def _refresh(self):
        self.watcher.refresh(self.filename)
        self.timer = None

    def on_modified(self, event):
        mtime = os.path.getmtime(event.src_path)
        # The modified event sometimes fires twice for no reason
        # even though the mtime is the same
        if mtime != self.mtime:
            self.mtime = mtime
            if self.watcher.debounce:
                if self.timer is not None:
                    self.timer.cancel()
                self.timer = threading.Timer(
                    self.watcher.debounce, self._refresh
                )
                self.timer.start()
            else:
                self._refresh()

    def schedule(self, observer):
        observer.schedule(self, self.filename)


def watch(
    pattern="./*.py",
    logger=default_logger,
    registry=registry,
    autostart=True,
    debounce=DEFAULT_DEBOUNCE,
):
    registry.auto_register(
        filter=glob_filter(pattern) if isinstance(pattern, str) else pattern
    )
    registry.set_logger(logger)
    watcher = Watcher(registry, debounce=debounce)
    if autostart:
        watcher.start()
    return watcher


def find_runner(opts, pattern):  # pragma: no cover
    if opts.module:
        if opts.script is not None:
            opts.rest.insert(0, opts.script)
        sys.argv[1:] = opts.rest

        if ":" in opts.module:
            module_name, func = opts.module.split(":", 1)
            mod = importlib.import_module(module_name)
            return mod, getattr(mod, func)

        else:
            _, spec, code = runpy._get_module_details(opts.module)
            if pattern(spec.origin):
                registry.prepare("__main__", spec.origin)
            mod = ModuleType("__main__")

            def run():
                runpy.run_module(opts.module, module_object=mod)

            return mod, run

    elif opts.script:
        path = os.path.abspath(opts.script)
        if pattern(path):
            # It won't auto-trigger through runpy, probably some idiosyncracy of
            # module resolution
            registry.prepare("__main__", path)
        sys.argv[1:] = opts.rest
        mod = ModuleType("__main__")

        def run():
            runpy.run_path(path, module_object=mod)

        return mod, run

    else:
        mod = ModuleType("__main__")
        return mod, None


def cli():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="Run a Python script so that it is live-editable."
    )
    parser.add_argument(
        "script", metavar="SCRIPT", help="Path to the script to run", nargs="?"
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run an interactive session after the program ends",
    )
    parser.add_argument(
        "--watch",
        "-w",
        metavar="PATH",
        help="Wildcard path/directory for which files to watch",
    )
    parser.add_argument(
        "--debounce",
        "-d",
        type=float,
        dest="debounce",
        help="Interval to wait for to refresh a modified file, in seconds",
    )
    parser.add_argument(
        "-m",
        dest="module",
        metavar="MODULE",
        help="Module or module:function to run",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show watched files and changes as they happen",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version",
    )
    parser.add_argument(
        "rest", metavar="...", nargs=argparse.REMAINDER, help="Script arguments"
    )
    opts = parser.parse_args()

    pattern = glob_filter(opts.watch or ".")
    watch_args = {
        "pattern": pattern,
        "logger": default_logger if opts.verbose else conservative_logger,
        "debounce": opts.debounce or DEFAULT_DEBOUNCE,
    }

    banner = ""

    if opts.version:
        print(version)
        sys.exit()

    mod, run = find_runner(opts, pattern)
    watch(**watch_args)

    if run is None:
        banner = None
        opts.interactive = True
    else:
        banner = ""
        run()

    if opts.interactive:
        code.interact(banner=banner, local=vars(mod), exitmsg="")

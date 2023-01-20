import importlib.util
import logging
import os
import sys
from types import CodeType, FunctionType, ModuleType

from _frozen_importlib_external import SourceFileLoader
from ovld import OvldMC, ovld

from .codetools import CodeFile, FunctionDefinition
from .utils import EventSource, glob_filter

log = logging.getLogger(__name__)


class Registry(metaclass=OvldMC):
    def __init__(self):
        self.filename_to_module = {}
        # Cache of (module_name, file_contents, mtime)
        # A snapshot of the file contents may be saved before it might be modified
        self.precache = {}
        # Cache of CodeFile (lazy)
        self.cache = {}
        self.precache_activity = EventSource(save_history=True)
        self.activity = EventSource()
        self._log = None

    def set_logger(self, log):
        self._log = log

    def log(self, *args, **kwargs):
        if self._log is not None:
            self._log(*args, **kwargs)

    def prepare(self, module_name=None, filename=None):
        if filename is None:
            assert module_name is not None
            filename = sys.modules[module_name].__file__

        if filename not in self.precache and filename not in self.cache:
            if module_name is None:
                if filename in self.filename_to_module:
                    module_name = self.filename_to_module[filename]
                else:
                    for module_name, module in sys.modules.items():
                        fname = getattr(module, "__file__", None)
                        if fname:
                            self.filename_to_module[fname] = module_name
                            if fname == filename:
                                break
                    else:  # pragma: no cover
                        raise Exception(
                            f"Cannot find module that corresponds to {filename}"
                        )

            if os.path.exists(filename):
                with open(filename, "r", encoding="utf8") as f:
                    self.precache[filename] = (
                        module_name,
                        f.read(),
                        os.path.getmtime(filename),
                    )
                self.precache_activity.emit(module_name, filename)

        return module_name, filename

    def get(self, filename):
        if filename in self.cache:
            return self.cache[filename]

        if filename in self.precache:
            module_name, cached_source, mtime = self.precache[filename]
            if module_name not in sys.modules:
                return None
            cf = CodeFile(
                filename, source=cached_source, module_name=module_name
            )
            cf.associate(sys.modules[module_name])
            cf.activity.register(self.log)
            # Basic forwarding of the CodeFile's events
            cf.activity.register(self.activity.emit)
            self.cache[filename] = cf
            return cf

        return None

    def get_at(self, filename, lineno):
        cf = self.get(filename)
        if cf is None:
            return None, None
        for entry in cf.root.walk():
            if (
                isinstance(entry, FunctionDefinition)
                and entry.node is not None
                and (
                    (
                        entry.stashed.lineno == lineno
                        and entry.stashed.filename == filename
                    )
                    or (
                        entry.node.extent.lineno == lineno
                        and entry.node.extent.filename == filename
                    )
                )
            ):
                return cf, entry
        else:
            return cf, None

    def auto_register(self, filter=glob_filter("./*.py")):
        def prep(module_name, filename):
            if (
                filename is not None
                and module_name is not None
                and filter(filename)
            ):
                try:
                    self.prepare(module_name, filename)
                except (UnicodeDecodeError, OSError):  # pragma: no cover
                    pass

        for name, module in list(sys.modules.items()):
            filename = getattr(module, "__file__", None)
            module_name = getattr(module, "__name__", None)
            prep(module_name, filename)

        return add_sniffer(prep)

    @ovld
    def find(self, module: ModuleType):
        self.prepare(module.__name__, module.__file__)
        cf = self.get(module.__file__)
        return cf, cf.root

    @ovld
    def find(self, fn: FunctionType):
        co = fn.__code__
        self.prepare(fn.__module__, co.co_filename)
        return self.get_at(co.co_filename, co.co_firstlineno)

    @ovld
    def find(self, co: CodeType):
        self.prepare(filename=co.co_filename)
        return self.get_at(co.co_filename, co.co_firstlineno)

    @ovld
    def find(self, cls: type):
        _, filename = self.prepare(module_name=cls.__module__)
        cf = self.get(filename)
        key = f"{cls.__module__}.{cls.__qualname__}"
        for entry in cf.root.walk():
            if entry.dotpath() == key:
                return cf, entry
        else:
            return cf, None


registry = Registry()


class ImportSniffer:
    """A spec finder that simply sniffs for attempted imports.

    Basically we install this at the front of sys.meta_path so that
    importlib.util.find_spec calls it, then we call find_spec
    ourselves to locate the file that's going to be read so that we
    know we have to cache its contents and watch for changes.
    """

    def __init__(self):
        self.working = False

    def find_module(self, spec, path):
        if not _sniffer_callbacks:
            return None

        if not self.working:
            self.working = True
            # We call find_spec ourselves to find out where the file is.
            # This will not cause an infinite loop because self.working
            # is True and we will not enter the conditional. I'm not
            # sure if it's dangerous to call find_spec within find_spec,
            # but it seems to work, so whatever.
            mspec = importlib.util.find_spec(spec, path)
            if (
                mspec is not None
                and isinstance(mspec.loader, SourceFileLoader)
                and mspec.name is not None
                and mspec.origin is not None
            ):
                for report in _sniffer_callbacks:
                    try:
                        report(mspec.name, mspec.origin)
                    except Exception as exc:
                        log.error(
                            f"jurigged: Error processing spec {mspec.name}",
                            exc_info=exc,
                        )
            self.working = False
        return None


_main_sniffer = ImportSniffer()
sys.meta_path.insert(0, _main_sniffer)
_sniffer_callbacks = []


def add_sniffer(report):
    _sniffer_callbacks.append(report)
    report.uninstall = lambda: _sniffer_callbacks.remove(report)
    return report

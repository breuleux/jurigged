import ast
import inspect
import os
import sys
import tempfile
import time
from ast import NodeTransformer
from itertools import count
from textwrap import dedent

from _pytest.assertion.rewrite import AssertionRewriter


class AssertTransformer(NodeTransformer):
    def visit_FunctionDef(self, node):
        newfns = []
        for i, stmt in enumerate(node.body):
            if not isinstance(stmt, ast.Assert):
                raise Exception(
                    "@one_test_per_assert requires all statements to be asserts"
                )
            else:
                newfns.append(
                    ast.FunctionDef(
                        name=f"{node.name}_assert{i + 1}",
                        args=node.args,
                        body=[stmt],
                        decorator_list=node.decorator_list,
                        returns=node.returns,
                    )
                )
        return ast.Module(body=newfns, type_ignores=[])


def one_test_per_assert(fn):
    src = dedent(inspect.getsource(fn))
    filename = inspect.getsourcefile(fn)
    tree = ast.parse(src, filename)
    tree = tree.body[0]
    assert isinstance(tree, ast.FunctionDef)
    tree.decorator_list = []
    new_tree = AssertTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    _, lineno = inspect.getsourcelines(fn)
    ast.increment_lineno(new_tree, lineno - 1)
    # Use pytest's assertion rewriter for nicer error messages
    AssertionRewriter(filename, None, None).run(new_tree)
    new_fn = compile(new_tree, filename, "exec")
    glb = fn.__globals__
    exec(new_fn, glb, glb)
    return None


tmpcount = count()


class TemporaryModule:
    def __init__(self):
        d = os.path.realpath(tempfile.mkdtemp())
        sys.path.append(d)
        self.path = d

    def rel(self, name):
        return os.path.join(self.path, name)

    def write(self, name, contents):
        path = self.rel(name)
        with open(path, "w") as f:
            f.write(contents)
        # A small wait before we can import the file seems necessary under Linux but I don't know why
        if not os.environ.get("JURIGGED_FAST_TEST"):
            time.sleep(0.01)
        return path

    def transfer(self, name, mangle=True):
        orig = os.path.join(os.path.dirname(__file__), "snippets", f"{name}.py")
        if mangle is True:
            mname = f"{name}__{next(tmpcount)}"
        elif isinstance(mangle, str):
            mname = f"{name}{mangle}"
        else:
            mname = name
        filename = self.write(f"{mname}.py", open(orig).read())
        return mname, filename

    def imp(self, name, mangle=True):
        mname, _ = self.transfer(name, mangle=mangle)
        return __import__(mname)


def catalogue(root):
    cat = {}
    for entry in root.walk():
        if entry.node and entry.node.extent:
            typ = type(entry).__name__
            cat[typ, entry.filename, entry.stashed.lineno] = entry
            cat[entry.dotpath()] = entry
    return cat


def _blah(x, y):
    def inner():
        return x + y

    return inner

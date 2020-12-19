import ast
import inspect
import os
import sys
import tempfile
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
        d = tempfile.mkdtemp()
        sys.path.append(d)
        self.path = d

    def rel(self, name):
        return os.path.join(self.path, name)

    def write(self, name, contents):
        path = self.rel(name)
        open(path, "w").write(contents)
        return path

    def transfer(self, name):
        orig = os.path.join(os.path.dirname(__file__), "snippets", f"{name}.py")
        mname = f"{name}__{next(tmpcount)}"
        filename = self.write(f"{mname}.py", open(orig).read())
        return mname, filename

    def imp(self, name):
        mname, _ = self.transfer(name)
        return __import__(mname)

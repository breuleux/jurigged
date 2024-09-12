import ast
from dataclasses import dataclass, field, replace as dc_replace

from ovld import ovld, recurse


@dataclass
class Variables:
    assigned: set = field(default_factory=set)
    read: set = field(default_factory=set)
    closure: set = field(default_factory=set)

    @property
    def free(self):
        return self.read - self.assigned

    replace = dc_replace

    def __or__(self, other):
        return Variables(
            assigned=self.assigned | other.assigned,
            read=self.read | other.read,
        )


@ovld
def variables(seq: list, mapping):
    fvs = Variables()
    for node in seq:
        fvs = fvs | recurse(node, mapping)
    return fvs


@ovld
def variables(node: (ast.FunctionDef, ast.AsyncFunctionDef), mapping):
    fvs = (
        recurse(node.body, mapping)
        | recurse(node.args.args, mapping)
        | recurse(node.args.posonlyargs, mapping)
        | recurse(node.args.kwonlyargs, mapping)
        | recurse(node.args.kwarg, mapping)
        | recurse(node.args.vararg, mapping)
    )
    mapping[node] = fvs
    outer = (
        recurse(node.decorator_list, mapping)
        | recurse(node.args.defaults, mapping)
        | recurse(node.args.kw_defaults, mapping)
    )
    return outer | Variables(assigned={node.name}, read=fvs.free)


@ovld
def variables(node: ast.ClassDef, mapping):
    fvs = recurse(node.body, mapping) | Variables(assigned={"__class__"})
    mapping[node] = fvs
    outer = recurse(node.decorator_list, mapping)
    return outer | Variables(assigned={node.name}, read=fvs.free)


@ovld
def variables(node: ast.arg, mapping):
    return Variables(assigned={node.arg})


@ovld
def variables(node: ast.Name, mapping):
    if isinstance(node.ctx, ast.Load):
        read = {node.id}
        if node.id == "super":
            read.add("__class__")
        return Variables(read=read)
    elif isinstance(node.ctx, ast.Store):
        return Variables(assigned={node.id})
    else:
        return Variables(read={node.id})


@ovld
def variables(node: ast.AST, mapping):
    return recurse(list(ast.iter_child_nodes(node)), mapping)


@ovld  # pragma: no cover
def variables(thing: object, mapping):
    # Just in case
    return Variables()

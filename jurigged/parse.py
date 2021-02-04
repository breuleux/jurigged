import ast
from dataclasses import dataclass, field, replace as dc_replace

from ovld import ovld


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
def variables(self, seq: list, mapping):
    fvs = Variables()
    for node in seq:
        fvs = fvs | variables(node, mapping)
    return fvs


@ovld
def variables(self, node: (ast.FunctionDef, ast.AsyncFunctionDef), mapping):
    fvs = self(node.body, mapping) | Variables(assigned={node.name})
    mapping[node] = fvs
    outer = self(node.decorator_list, mapping)
    return outer | Variables(assigned={node.name}, read=fvs.free)


@ovld
def variables(self, node: ast.ClassDef, mapping):
    fvs = self(node.body, mapping) | Variables(
        assigned={node.name, "__class__"}
    )
    mapping[node] = fvs
    outer = self(node.decorator_list, mapping)
    return outer | Variables(assigned={node.name}, read=fvs.free)


@ovld
def variables(self, node: ast.Name, mapping):
    if isinstance(node.ctx, ast.Load):
        read = {node.id}
        if node.id == "super":
            read.add("__class__")
        return Variables(read=read)
    elif isinstance(node.ctx, ast.Store):
        return Variables(assigned={node.id})


@ovld
def variables(self, node: ast.AST, mapping):
    return self(list(ast.iter_child_nodes(node)), mapping)


@ovld  # pragma: no cover
def variables(self, thing: object, mapping):
    # Just in case
    return Variables()
import ast
import io
import types


def split_script(script):  # pragma: no cover
    """Split code that comes after all function definitions.

    Essentially, we want to be able to instrument functions in the main script, which
    requires evaluating the functions, but we want to do this before executing the main
    code. So we split off code that comes after function definitions so that we can evaluate
    the module and then evaluate that code separately.

    Code between function definitions will be evaluated right away, but the bulk usually
    comes after these definitions (because they need to use them).
    """

    with io.open_code(script) as f:
        source_code = f.read()

    tree = ast.parse(source_code, mode="exec")

    last_def = 0
    for i, stmt in enumerate(tree.body):
        if isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            last_def = i + 1

    mod_before = ast.copy_location(
        ast.Module(
            body=tree.body[:last_def],
            type_ignores=[],
        ),
        tree,
    )

    mod_after = ast.copy_location(
        ast.Module(
            body=tree.body[last_def:],
            type_ignores=[],
        ),
        tree,
    )

    return (
        compile(mod_before, script, "exec"),
        compile(mod_after, script, "exec"),
    )


redirector = """
def {name}(*args, **kwargs):
    return ____jurigged_wrapped_{name}(*args, **kwargs)
"""


def redirector_code(name):
    """Return a code object that calls a global with a certain name.

    That code object is meant to be patched onto an existing function so that it
    can redirect to something else.
    """
    glb = {}
    exec(redirector.format(name=name), glb)
    fn = glb[name]
    return fn.__code__


def redirect(orig, transform):
    """Redirect a function to a transformed version of it.

    The __code__ pointer of the function will be patched to redirect to a decorated
    version of the function. That way, all existing pointers for the function will
    use the decorated version.
    """
    saved = types.FunctionType(
        orig.__code__,
        orig.__globals__,
        orig.__name__,
        orig.__defaults__,
        orig.__closure__,
    )
    name = orig.__name__
    new_code = redirector_code(name)
    orig.__code__ = new_code
    orig.__globals__[f"____jurigged_wrapped_{name}"] = transform(saved)


def redirect_code(code, transform):
    """Patch the function with the given code to a transformed/decorated version.

    The __code__ pointer of the function will be patched to redirect to a decorated
    version of the function. That way, all existing pointers for the function will
    use the decorated version.
    """
    import codefind

    fns = codefind.get_functions(code)
    if len(fns) != 1:
        raise Exception(
            f"Redecoration of {code} requires exactly one function to use it."
        )
    (fn,) = fns
    redirect(fn, transform)

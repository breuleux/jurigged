import itertools
import random
import textwrap
from dataclasses import dataclass, replace as dc_replace
from types import ModuleType, SimpleNamespace as NS

import pytest

from jurigged.codetools import CodeFile

from .common import TemporaryModule

ABSENT = object()


vowels = list("aeiou")
consonants = list("bdfgjklmnprstvz")
syllables = [
    "".join(letters) for letters in itertools.product(consonants, vowels)
]


@dataclass
class Parameters:
    rstate: random.Random
    body_range: int
    args_range: int
    line_range: int
    blank_range: int
    class_probability: float
    active_probability: float
    update_probability: float
    flip_probability: float
    commit_probability: float

    replace = dc_replace

    def longname(self):
        a = self.rstate.choice(syllables)
        b = self.rstate.choice(syllables)
        c = self.rstate.choice(syllables)
        d = self.rstate.choice(syllables)
        return a + b + c + d

    def shortname(self):
        return self.rstate.choice(syllables)

    def draw(self, prob):
        return self.rstate.random() < prob

    def randint(self, mi, ma):
        return self.rstate.randint(mi, ma)


@dataclass
class ModuleGen:
    name: str
    body: list

    @classmethod
    def create(cls, params):
        return cls(name=params.longname(), body=genplan(params))

    def gen(self):
        parts = [part.gen() for part in self.body]
        return "\n".join(parts)

    def imp(self, tmod):
        tmod.write(f"{self.name}.py", self.gen())
        return __import__(self.name)

    def impclone(self, tmod, params):
        filename = tmod.rel(f"{self.name}.py")
        tempname = params.longname()
        tmod.write(f"{tempname}.py", open(filename).read())
        return __import__(tempname)

    def codefile(self, tmod, imp=False):
        cf = CodeFile(
            filename=tmod.rel(f"{self.name}.py"),
            source=self.gen(),
            module_name=self.name,
        )
        if imp:
            module = self.imp(tmod)
            cf.associate(module)
        return cf

    def prune(self, module):
        keep = {defn.name for defn in self.body if defn.active}
        for k, v in dict(vars(module)).items():
            if not k.startswith("_") and k not in keep:
                delattr(module, k)
        for defn in self.body:
            if hasattr(module, defn.name):
                defn.prune(getattr(module, defn.name))

    def validate(self, module, require_all=True):
        for defn in self.body:
            if defn.active:
                if require_all:
                    assert hasattr(module, defn.name)
                obj = getattr(module, defn.name, ABSENT)
                if obj is not ABSENT:
                    defn.validate(obj, require_all=require_all)

    def change(self, params):
        new_body = list(self.body)
        params.rstate.shuffle(new_body)
        new_body = [stmt.change(params) for stmt in new_body]
        return ModuleGen(name=params.longname(), body=new_body)


@dataclass
class FunctionGen:
    name: str
    accname: str
    nargs: int
    nlines: int
    newlines_after: int
    active: bool

    def gen(self, inclass=False):
        if not self.active:
            return ""
        argnames = [chr(ord("a") + i) for i in range(self.nargs)]
        addition = " + ".join(argnames) if argnames else "0"
        # if inclass:
        #     argnames.insert(0, "self")
        args = ", ".join(argnames)
        if self.nlines > 1:
            lines = [f"{self.accname} = {addition}"]
            lines += [f"{self.accname} += {i}" for i in range(self.nlines - 2)]
            lines.append(f"return {self.accname}")
        else:
            lines = [f"return {addition}"]
        lines = [f"    {line}" for line in lines]
        lines += [""] * self.newlines_after
        lines = "\n".join(lines)
        return f"def {self.name}({args}):\n{lines}"

    def prune(self, _):
        pass

    def validate(self, fn, require_all=True):
        if not self.active:
            return
        # args = range(len(inspect.signature(fn).parameters))
        args = range(self.nargs)
        value = fn(*args)
        expected = sum(args)
        if self.nlines > 1:
            expected += ((self.nlines - 3) * (self.nlines - 2)) / 2
        # print("TEST", self.name, value, expected, self.nlines)
        if value != expected:
            raise AssertionError(f"{value} != {expected} in {self.name}")

    def change(self, params):
        if not params.draw(params.update_probability):
            return self
        else:
            return FunctionGen(
                name=self.name,
                accname=params.shortname(),
                nargs=params.randint(*params.args_range),
                nlines=params.randint(*params.line_range),
                newlines_after=params.randint(*params.blank_range),
                active=(
                    not self.active
                    if params.draw(params.flip_probability)
                    else self.active
                ),
            )


@dataclass
class ClassGen:
    name: str
    methods: list
    newlines_after: int = 0

    @property
    def active(self):
        return any(defn.active for defn in self.methods)

    def gen(self, inclass=False):
        if not self.active:
            return ""
        defns = [
            textwrap.indent(method.gen(inclass=True), " " * 4)
            for method in self.methods
        ]
        defns += [""] * self.newlines_after
        defns = "\n".join(defns)
        return f"class {self.name}:\n{defns}"

    def prune(self, kls):
        keep = {defn.name for defn in self.methods if defn.active}
        for k, v in dict(vars(kls)).items():
            if not k.startswith("_") and k not in keep:
                print("DELETE", k)
                delattr(kls, k)
        for defn in self.methods:
            if hasattr(kls, defn.name):
                defn.prune(getattr(kls, defn.name))

    def validate(self, kls, require_all=True):
        for defn in self.methods:
            if defn.active:
                if require_all:
                    assert hasattr(kls, defn.name)
                obj = getattr(kls, defn.name, ABSENT)
                if obj is not ABSENT:
                    defn.validate(obj, require_all=require_all)

    def change(self, params):
        new_body = list(self.methods)
        params.rstate.shuffle(new_body)
        new_body = [stmt.change(params) for stmt in new_body]
        return ClassGen(name=self.name, methods=new_body)


def make_shadow(obj):
    if isinstance(obj, (ModuleType, type)):
        new_members = {x: make_shadow(y) for x, y in vars(obj).items()}
        return NS(**new_members)
    else:
        return obj


def ordered_code(codefile):
    defns = [
        defn
        for defn in codefile.definitions
        if defn.type == "function" and defn.active
    ]
    defns.sort(key=lambda d: d.name)
    code = ""
    for defn in defns:
        code += textwrap.indent(defn.saved, " " * defn.indent) + "\n"
    lines = code.split("\n")
    return "\n".join([line for line in lines if line.strip()])


def gencode(plan):
    parts = [part.gen() for part in plan]
    return "\n".join(parts)


def genplan(params):
    nitems = params.rstate.randint(*params.body_range)
    items = []
    for i in range(nitems):
        if params.draw(params.class_probability):
            item = ClassGen(
                name=params.longname(),
                newlines_after=params.randint(*params.blank_range),
                methods=genplan(params.replace(body_range=(1, 3))),
            )
        else:
            item = FunctionGen(
                name=params.longname(),
                accname=params.shortname(),
                nargs=params.randint(*params.args_range),
                nlines=params.randint(*params.line_range),
                newlines_after=params.randint(*params.blank_range),
                active=params.draw(params.active_probability),
            )
        items.append(item)
    return items


@pytest.fixture(scope="module")
def rstate():
    r = random.Random()
    r.seed(1234)
    return r


# BAD: 1253
# BAD: 1390
# BAD: 1591
# BAD: 1857

# BAD: 981


@pytest.mark.parametrize("seed", range(100))
def test_edit_sequence(seed):
    rstate = random.Random()
    rstate.seed(seed)
    params = Parameters(
        rstate=rstate,
        body_range=(5, 5),
        args_range=(0, 3),
        line_range=(1, 7),
        blank_range=(0, 2),
        class_probability=0.2,
        active_probability=0.5,
        update_probability=0.3,
        flip_probability=0.1,
        commit_probability=0.5,
    )
    mod = ModuleGen.create(params)
    orig_mod = mod
    tmod = TemporaryModule()
    cf = mod.codefile(tmod, imp=True)
    module = cf.module

    shadow_module = make_shadow(module)
    mod.validate(module)
    for i in range(10):
        # Apply a bunch of random modifications
        mod = mod.change(params)
        # Merge the modified code with the main CodeFile
        cf2 = mod.codefile(tmod)

        order = "original" if rstate.random() < 0.5 else "new"

        cf.merge(cf2, order=order)

        # Commit sometimes
        if params.draw(params.commit_probability):
            cf.commit()

            # Copy the committed file under a different name, import it, and check
            # that it behaves the same
            cloned = orig_mod.impclone(tmod, params)
            mod.validate(cloned)
        # Check that the module was updated properly
        mod.validate(module)

        # Check that the shadow module still works
        mod.prune(shadow_module)
        mod.validate(shadow_module, require_all=False)

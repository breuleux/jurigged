
# jurigged

Jurigged lets you update your code while it runs. Using it is trivial:

1. `jurigged your_script.py`
2. Change some function or method with your favorite editor and save the file
3. Jurigged will hot patch the new function into the running script

Jurigged updates live code smartly: changing a function or method will fudge code pointers so that all existing instances are simultaneously modified to implement the new behavior. When modifying a module, only changed lines will be re-run.

![demo](https://user-images.githubusercontent.com/599820/113785377-ffab1e80-9704-11eb-9c82-6d866c9087a6.gif)

You can also optionally install the [develoop](#develoop), a terminal-based live development environment:

![develoop2](https://user-images.githubusercontent.com/599820/165631993-8c428e4b-51d2-48d7-ae15-93bfc09c70af.gif)

As seen above, `jurigged --loop <function_name> script.py` will "loop" on a particular function of the script. That funtion will be re-run every time the source code is modified, with changes hot-patched into the running process. The rest of the program is *not* re-run, so preprocessing is preserved and heavy modules do not have to be reloaded!

## Install

Jurigged requires Python version >= 3.8.

```bash
pip install jurigged
```

To also install the develoop feature, which lets you interactively develop functions:

```bash
pip install jurigged[develoop]
```

## Command line

The simplest way to use jurigged is to add `-m jurigged` to your script invocation, or to use `jurigged` instead of `python`. You can use `-v` to get feedback about what files are watched and what happens when you change a file.

```bash
python -m jurigged -v script.py

OR

jurigged -v script.py
```

With no arguments given, it will start a live REPL:

```bash
python -m jurigged

OR

jurigged
```

Full help:

```
usage: jurigged [-h] [--interactive] [--watch PATH] [--debounce DEBOUNCE] [--poll POLL] [-m MODULE] [--dev] [--verbose] [--version]
                [SCRIPT] ...

Run a Python script so that it is live-editable.

positional arguments:
  SCRIPT                Path to the script to run
  ...                   Script arguments

optional arguments:
  -h, --help            show this help message and exit
  --interactive, -i     Run an interactive session after the program ends
  --watch PATH, -w PATH
                        Wildcard path/directory for which files to watch
  --debounce DEBOUNCE, -d DEBOUNCE
                        Interval to wait for to refresh a modified file, in seconds
  --poll POLL           Poll for changes using the given interval
  -m MODULE             Module or module:function to run
  --dev                 Inject jurigged.loop.__ in builtins
  --verbose, -v         Show watched files and changes as they happen
  --version             Print version
```

## Develoop

Usage:

```bash
# Loop over a function
jurigged --loop function_name script.py
jurigged --loop module_name:function_name script.py

# Only stop on exceptions
jurigged --xloop function_name script.py
```

The "develoop" is an optional feature of Jurigged that provides a sort of live development environment for a function. If you run `jurigged --loop <function_name> <script>`, the function of that name in the script will be part of the "develoop". When it is entered, it will be run, its output will be captured and displayed, and the program will wait for input. If the source code is changed, the function will run again.

The `--xloop` or `-x` flag works the same, but the loop is only done if the function raises an exception. If it does not raise an exception, it will run like normal. Both `--loop` and `--xloop` can be used multiple times, if you want to loop over multiple functions.

The default interface allows a few commands:

* `r` to manually re-run the loop. This can be done in the middle of a run.
* `a` to abort the current run (e.g. if you get stuck in an infinite loop).
* `c` to exit the loop and continue the program normally.
* `q` to quit the program altogether.

### Using with stdin

The default develoop interface does not play well with stdin. If you want to read from stdin or set a `breakpoint()`, use the decorator `@__.loop(interface="basic")`. The interface will be cruder, but stdin/pdb will work.

## Troubleshooting

First, if there's a problem, use the verbose flag (`jurigged -v`) to get more information. It will output a `Watch <file>` statement for every file that it watches and `Update/Add/Delete <function>` statements when you update, add or delete a function in the original file and then save it.

**The file is not being watched.**

By default, scripts are watched in the current working directory. Try `jurigged -w <file>` to watch a specific file, or `jurigged -w /` to watch all files.

**The file is watched, but nothing happens when I change the function.**

You can try using the `--poll <INTERVAL>` flag to use polling instead of the OS's native mechanisms. If that doesn't work, try and see if it works with a different editor: it might have to do with the way the editor saves. For example, some editors such as vi save into a temporary swap file and moves it into place, which used to cause issues (this should be fixed starting with `v0.3.5`).

**Jurigged said it updated the function but it's still running the old code.**

If you are editing the body of a for loop inside a function that's currently running, the changes will only be in effect the next time that function is called. A workaround is to extract the body of the for loop into its own helper function, which you can then edit. Alternatively, you can use [reloading](https://github.com/julvo/reloading) alongside Jurigged.

Similarly, updating a generator or async function will not change the behavior of generators or async functions that are already running.

**I can update some functions but not others.**

There may be issues updating some functions when they are decorated or stashed in some data structure that Jurigged does not understand. Jurigged does have to find them to update them, unfortunately.


## API

You can call `jurigged.watch()` to programmatically start watching for changes. This should also work within IPython or Jupyter as an alternative to the `%autoreload` magic.

```python
import jurigged
jurigged.watch()
```

By default all files in the current directory will be watched, but you can use `jurigged.watch("script.py")` to only watch a single file, or `jurigged.watch("/")` to watch all modules.


### Recoders

Functions can be programmatically changed using a Recoder. Make one with `jurigged.make_recoder`. This can be used to implement hot patching or mocking. The changes can also be written back to the filesystem.

```python
from jurigged import make_recoder

def f(x):
    return x * x

assert f(2) == 4

# Change the behavior of the function, but not in the original file
recoder = make_recoder(f)
recoder.patch("def f(x): return x * x * x")
assert f(2) == 8

# Revert changes
recoder.revert()
assert f(2) == 4

# OR: write the patch to the original file itself
recoder.commit()
```

`revert` will only revert up to the last `commit`, or to the original contents if there was no commit.

A recoder also allows you to add imports, helper functions and the like to a patch, but you have to use `recoder.patch_module(...)` in that case.


## Caveats

Jurigged works in a surprisingly large number of situations, but there are several cases where it won't work, or where problems may arise:

* **Functions that are already running will keep running with the existing code.** Only the next invocations will use the new code.
  * When debugging with a breakpoint, functions currently on the stack can't be changed.
  * A running generator or async function won't change.
  * You can use [reloading](https://github.com/julvo/reloading) in addition to Jurigged if you want to be able to modify a running for loop.
* **Changing initializers or attribute names may cause errors on existing instances.**
  * Jurigged modifies all existing instances of a class, but it will not re-run `__init__` or rename attributes on existing instances, so you can easily end up with broken objects (new methods, but old data).
* **Updating the code of a decorator or a closure may or may not work.** Jurigged will do its best, but it is possible that some closures will be updated but not others.
* **Decorators that look at/tweak function code will probably not update properly.**
  * Wrappers that try to compile/JIT Python code won't know about jurigged and won't be able to redo their work for the new code.
  * They can be made to work using a `__conform__` method (see below).


## Customizing behavior

In order to update a transform of a Python function, for example a transform that generates a new code object based on the original source code, you need to do something like this:

```python
class Custom:
    __slots__ = ("code",)

    def __init__(self, transformed_fn, code):
        self.code = code
        self.transformed_fn = transformed_fn

    def __conform__(self, new_code):
        if new_code is None:
            # Function is being deleted
            ...

        if isinstance(new_code, types.FunctionType):
            new_code = new_code.__code__

        do_something(new_code)
        self.code = new_code

...
transformed_fn.somefield = Custom(transformed_fn, orig_fn.__code__)
```

Basically, when the original code is changed, jurigged will use the `gc` module to find objects that point to it, and if they have a `__conform__` method it will be called with the new code so that the transformed function can be updated. The original code must be in a slot on that object (it is important that it is in `__slots__`, otherwise the referrer is a dictionary). Multiple transformed functions may exist.


## How it works

In a nutshell, jurigged works as follows:

1. Inventory existing modules and functions:
  a. Insert an import hook that collects and watches source files.
  b. Look at all existing functions using `gc.get_objects()`.
  c. Add an audit hook that watches calls to `exec` in order to inventory any new functions.
2. Parse source files into sets of definitions.
3. When a file is modified, re-parse it into a set of definitions and match them against the original, yielding a set of changes, additions and deletions.
4. When a function's code has changed:
  a. Strip out the decorators
  b. Execute the new code
  c. Use `gc.get_referrers()` to find all functions that use the old code
  d. Replace their internal `__code__` pointers
5. If the replacement fails or if brand new code is added, execute the new code in the module namespace.


## Comparison

The two most comparable implementations of Jurigged's feature set that I could find (but it can be a bit difficult to find everything comparable) are **%autoreload** in IPython and **[limeade](https://github.com/CFSworks/limeade)**. Here are the key differences:

* They both re-execute the entire module when its code is changed. Jurigged, by contrast, surgically extracts changed functions from the parse tree and only replaces these. It only executes new or changed statements in a module.
  
  Which is better is somewhat situation-dependent: on one hand, re-executing the module will pick up more changes. On the other hand, it will reinitialize module variables and state, so certain things might break. Jurigged's approach is more conservative and will only pick up on modified functions, but it will not touch anything else, so I believe it is less likely to have unintended side effects. It also tells you what it is doing :)

* They will re-execute decorators, whereas Jurigged will instead dig into them and update the functions it finds inside.
  
  Again, there's no objectively superior approach. `%autoreload` will properly re-execute changed decorators, but these decorators will return new objects, so if a module imports an already decorated function, it won't update to the new version. If you only modify the function's code and not the decorators, however, Jurigged will usually be able to change it inside the decorator, so all the old instances will use the new behavior.

* They rely on synchronization points, whereas Jurigged can be run in its own thread.

  This is a double-edged sword, because even though Jurigged can add live updates to existing scripts with zero lines of additional code, it is not thread safe at all (code could be executed in the middle of an update, which is possibly an inconsistent state).

Other similar efforts:

* [reloading](https://github.com/julvo/reloading) can wrap an iterator to make modifiable for loops. Jurigged cannot do that, but you can use both packages at the same time.

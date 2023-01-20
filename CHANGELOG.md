
## 0.5.4 (2023-01-20)

* Develoop: Wrap text printed to the rich develoop
* Develoop: Remove hrepr dependency
* Better file watching for unnormalized source filenames

## 0.5.3 (2022-09-20)

Add pre- and post-run callback support

## 0.5.2 (2022-05-24)

Fix the -m option to take remainder arguments

## 0.5.1 (2022-05-16)

Make the watchdog dependency less strict

## 0.5.0 (2022-04-27)

* Change the develoop command line interface
* Turn off using the code cache when shifting line numbers (it's buggy)

## 0.4.1 (2021-11-11)

Fix develoop on methods.

## 0.4.0 (2021-11-10)

Add the "develoop", an optional live development system.

## 0.3.6 (2021-10-26)

Bugfix

## 0.3.5 (2021-10-22)

* Improve file watching, which should fix issues with vi and other editors.
* Add `--poll <INTERVAL>`.

## 0.3.4 (2021-07-20)

Fix a bug with `sys.path` resolution.

## 0.3.3 (2021-06-21)

Fix to a dependency.

## 0.3.2 (2021-05-21)

Move some internal functionality to a new `codefind` package so it can be used separately.

## 0.3.1 (2021-05-10)

Fix bugs in function collection and the way existing functions or objects accept new code.

## 0.3.0 (2021-05-07)

Updated the methodology for finding the functions to patch. The new method is a bit less performant, but it is more thorough.

## 0.2.4 (2021-05-07)

Added an `--interactive` or `-i` flag to the CLI to automatically go into the interpreter after running a script.

## 0.2.3 (2021-04-20)

Added a `--debounce` flag to the CLI, defaulting to 0.05s, to improve the behavior of jurigged in the case where a file is changed multiple times in a small time interval.

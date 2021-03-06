
## 0.2.3 (2021-04-20)

Added a `--debounce` flag to the CLI, defaulting to 0.05s, to improve the behavior of jurigged in the case where a file is changed multiple times in a small time interval.

## 0.2.4 (2021-05-07)

Added an `--interactive` or `-i` flag to the CLI to automatically go into the interpreter after running a script.

## 0.3.0 (2021-05-07)

Updated the methodology for finding the functions to patch. The new method is a bit less performant, but it is more thorough.

## 0.3.1 (2021-05-10)

Fix bugs in function collection and the way existing functions or objects accept new code.

## 0.3.2 (2021-05-21)

Move some internal functionality to a new `codefind` package so it can be used separately.

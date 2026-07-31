![version](https://img.shields.io/badge/version-19%2B-5682DF)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-rename)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-rename/total)

# 4d-plugin-rename

RENAME exposes a single command that renames or moves a file on disk by calling the operating system's native rename function directly — `_wrename` on Windows, `rename` on macOS — bypassing 4D's document/folder objects entirely. The command's only output is a raw Longint status code; it does not raise a 4D error or return a `Picture`, `Blob`, or object.

| Command | Returns (via parameter) | Purpose |
|---|---|---|
| [RENAME](#rename) | `Result` : Longint (OS status code) | Rename or move a file at the OS level |

**Platforms:** Windows, macOS

---

## Requirements & platform notes

- `RENAME` takes **3 mandatory parameters** — there is no optional/shorter form. Both path parameters are read unconditionally by the plugin, whether or not they contain a valid path.
- **Failure is silent, not a 4D error.** The command never raises an alert or a catchable 4D error. You must check `Result` after every call.
- **Path handling diverges by platform at the code level**, and the exact contract isn't fully pinned down by the provided source (see [Description](#description) below) — treat this as the single most important thing to test on your target platform before relying on this command in production.
- The plugin performs **no existence check, no permission check, and no path validation** before handing the strings straight to the OS call.
- This is a **synchronous, blocking OS call** — if either path resolves to a slow, removable, or network volume, the call blocks until the OS completes or times out.

---

## RENAME

### Syntax

```4d
RENAME ( Old path : Text ; New path : Text ; Result : Longint )
```

| Parameter | Type | Description |
|---|---|---|
| `Old path` | Text | Path of the existing file to rename. Read unconditionally — passing an empty string is not checked before use. |
| `New path` | Text | Destination path (including file name) to rename/move the file to. Read unconditionally — same caveat as `Old path`. |
| `Result` | Longint | **Out.** Raw OS return code from `_wrename`/`rename`: `0` on success, non-zero on failure. Never populated from a 4D-level error — it is the literal C return value. |

### Description

`RENAME` reads `Old path` and `New path` as plain 4D `Text` values and passes them to the platform's native rename call, then writes that call's raw return value into `Result`.

- **On Windows**, the plugin calls `_wrename` with the UTF-16 pointer obtained directly from the `Text` value (`getUTF16StringPtr`) — there is no path-syntax conversion step in this code path. The string you pass is handed to the OS essentially as-is.
- **On macOS**, the plugin first converts each `Text` value through `copyPath` into a `CUTF8String` before calling `rename`. This is a real, code-level divergence from the Windows path: macOS goes through a path-conversion step that Windows does not.
  - What exactly `copyPath` normalizes (e.g. 4D's standard POSIX-style document path syntax vs. some other internal representation) is implemented inside the plugin SDK's `C_TEXT` class, which isn't part of the provided source — **don't assume a specific path syntax is required on either platform without testing**. As a starting point, use 4D's standard POSIX-style path syntax (forward-slash separators) on both platforms and verify.
- **Exceptions are swallowed silently at the top level.** `PluginMain`'s `catch(...)` block is empty. If anything inside `RENAME` throws (e.g. a parameter-marshaling failure), the exception is discarded and `Result` is **never written** — the 4D variable you passed keeps whatever value it held *before* the call (commonly `0` if freshly declared, or a stale value from a prior call if reused in a loop). Don't treat `Result=0` after a call as proof of success unless you also independently verified the call actually reached the OS layer (e.g. by pre-initializing `Result` to a sentinel value you know can't be a real OS code).
- The command does not distinguish failure causes (missing source file, permission denied, destination on a different volume, destination folder missing) — all of these surface only as "some non-zero `Result`."
- No check is made for an existing file at `New path` before the OS call; overwrite behavior in that case is determined entirely by the OS's `rename`/`_wrename` semantics, not by the plugin.

### Example

```4d
// Basic rename, same folder
C_TEXT($oldPath;$newPath)
C_LONGINT($result)

$oldPath:="/Users/me/Desktop/draft.txt"
$newPath:="/Users/me/Desktop/final.txt"

$result:=-1  // sentinel: distinguishes "never written" from a genuine 0
RENAME ($oldPath;$newPath;$result)

If ($result=0)
	ALERT("File renamed successfully.")
Else
	ALERT("Rename failed or did not run. Code: "+String($result))
End if
```

```4d
// Guard against empty/missing paths before calling RENAME,
// since the plugin itself performs no such check
C_TEXT($oldPath;$newPath)
C_LONGINT($result)

$oldPath:="/Users/me/Desktop/invoice.txt"
$newPath:="/Users/me/Desktop/Archive/invoice.txt"

If (($oldPath="") | ($newPath=""))
	ALERT("Paths cannot be empty.")
Else
	$result:=-1
	RENAME ($oldPath;$newPath;$result)
	If ($result#0)
		ALERT("Rename failed with code: "+String($result))
	End if
End if
```

> The exact commands for testing whether a file exists at a path, or for constructing paths from 4D's `Folder`/`File` objects, vary by 4D version — check your Language Reference for the syntax available on your release rather than assuming the forms above are the only option.

---

## Error handling & troubleshooting

- **A non-zero `Result` is your only signal of failure.** `RENAME` never raises a 4D error or alert; always branch on `Result` after every call.
- **`Result` can be left completely untouched on an internal exception.** Because `PluginMain`'s catch block is empty, a thrown exception inside the command means `Result` is never written at all. Pre-set the variable to a sentinel value before calling `RENAME` if you need to reliably detect "the call didn't run" versus "the call ran and returned 0."
- **Path-syntax expectations differ by platform at the code level.** Windows passes your `Text` straight through to `_wrename` with no conversion; macOS converts it via `copyPath` first. If a rename works on one platform and silently fails on the other with the same-looking path string, this divergence is the first thing to check.
- **No existence, permission, or emptiness check happens before the OS call.** An empty string, a missing source file, or a destination in a non-existent folder all just produce some non-zero `Result` — none of them are checked or reported individually.
- **No overwrite protection.** If a file already exists at `New path`, whether it gets overwritten or the call fails depends entirely on the OS's native rename semantics, not on anything the plugin does. Check for an existing destination yourself first if you need guaranteed non-destructive behavior.
- **Cross-volume moves are not guaranteed.** Native rename calls are generally restricted to a single disk/volume; moving across volumes typically requires a copy-then-delete instead.
- **This call blocks.** A source or destination on a slow, removable, or network volume can stall the calling process until the OS times out.

---

## Quick reference

```4d
C_TEXT($old;$new)
C_LONGINT($result)

$old:="/path/to/source.txt"
$new:="/path/to/destination.txt"

$result:=-1
RENAME ($old;$new;$result)

If ($result=0)
	 // success
Else
	 // $result=-1 → call never completed; otherwise → OS-level failure code
End if
```

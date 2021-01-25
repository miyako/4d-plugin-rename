![version](https://img.shields.io/badge/version-16%2B-8331AE)
![platform](https://img.shields.io/static/v1?label=platform&message=osx-64%20|%20win-32%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-rename)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-rename/total)

# 4d-plugin-rename
Wrapper of standard C [rename](https://msdn.microsoft.com/en-us/library/zw5t957f.aspx) function

## Syntax

```
RENAME (old;new;error)
```

Parameter|Type|Description
------------|------------|----
old|TEXT|old path of file or folder
new|TEXT|new path of file or folder
error|LONGINT|

## Examples

```
$path:=System folder(Desktop)+Generate UUID+Folder separator

CREATE FOLDER($path;*)

RENAME ($path;System folder(Desktop)+Generate UUID;$error)
```

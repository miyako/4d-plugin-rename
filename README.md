# 4d-plugin-rename
Wrapper of standard C [rename](https://msdn.microsoft.com/en-us/library/zw5t957f.aspx) function

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
| |<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" /> |<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" /> |<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" /> 

### Version

<img src="https://user-images.githubusercontent.com/1725068/41266195-ddf767b2-6e30-11e8-9d6b-2adf6a9f57a5.png" width="32" height="32" />

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

"""Commit one fixed 64 MiB block, recording actual Windows allocation refusal.

VirtualAlloc MEM_COMMIT charges commitment, unlike reservation alone:
https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/
nf-memoryapi-virtualalloc
"""
import ctypes as C
import json
import sys
from pathlib import Path

api = C.WinDLL("kernel32", use_last_error=True)
allocate = api.VirtualAlloc
allocate.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong, C.c_ulong]
allocate.restype = C.c_void_p
release = api.VirtualFree
release.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong]
release.restype = C.c_int
pointer = allocate(None, 64 * 1024 * 1024, 0x3000, 4)
error = C.get_last_error() if not pointer else 0
if pointer and not release(pointer, 0, 0x8000):
    raise C.WinError(C.get_last_error())
Path(sys.argv[1]).write_text(json.dumps({"allocated": bool(pointer),
                                       "error": error}), encoding="utf-8")

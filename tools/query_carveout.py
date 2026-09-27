#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Query NVIDIA RM region metadata; allocate handles, never memory buffers."""
import ctypes as C
import fcntl
import json
import os


class Alloc(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('root', 'parent', 'new', 'cls')] + [
        ('params', C.c_void_p), ('size', C.c_uint32), ('status', C.c_uint32)]


class Control(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('client', 'object', 'cmd', 'flags')] + [
        ('params', C.c_void_p), ('size', C.c_uint32), ('status', C.c_uint32)]


class Device(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('id', 'share', 'targetclient', 'targetdevice', 'flags')] + [
        (n, C.c_uint64) for n in ('vasize', 'start', 'limit')] + [('mode', C.c_uint32)]


class Region(C.Structure):
    _fields_ = [('base', C.c_uint64), ('size', C.c_uint64), ('kind', C.c_uint32)]


class Regions(C.Structure):
    _fields_ = [('count', C.c_uint32), ('regions', Region * 8)]


def call(fd, number, argument):
    fcntl.ioctl(fd, 0xc0000000 | (C.sizeof(argument) << 16) | (ord('F') << 8) | number, argument)
    if argument.status:
        raise RuntimeError(f'RM operation {number:#x}: status {argument.status:#x}')


def query():
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('64-bit userspace required')
    fd = os.open('/dev/nvidiactl', os.O_RDWR)
    try:
        gpu = os.open('/dev/nvidia0', os.O_RDWR)
        try:
            fcntl.ioctl(gpu, 0xc00446c9, C.c_int(fd))
            a = Alloc(0, 0, 0, 0x41, None, 0, 0)
            call(fd, 0x2b, a)
            root = a.new
            d = Device()
            call(fd, 0x2b, Alloc(root, root, 0x80000001, 0x80, C.addressof(d), C.sizeof(d), 0))
            subdevice = C.c_uint32(0)
            call(fd, 0x2b, Alloc(root, 0x80000001, 0x80000002, 0x2080, C.addressof(subdevice), 4, 0))
            regions = Regions()
            call(fd, 0x2a, Control(root, 0x80000002, 0x20801360, 0, C.addressof(regions), C.sizeof(regions), 0))
            if regions.count > 8:
                raise RuntimeError('Invalid region count')
            return [dict(base=r.base, size=r.size, type=r.kind) for r in regions.regions[:regions.count]]
        finally:
            os.close(gpu)
    finally:
        os.close(fd)


if __name__ == '__main__':
    print(json.dumps(query(), indent=2))

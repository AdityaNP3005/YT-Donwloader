"""Capture only a known X11 app window; developer helper, requires Pillow."""
import ctypes as c
import ctypes.util
from pathlib import Path
import sys
from PIL import Image


class XImage(c.Structure):
    _fields_ = [('width', c.c_int), ('height', c.c_int), ('xoffset', c.c_int),
                ('format', c.c_int), ('data', c.c_void_p), ('byte_order', c.c_int),
                ('bitmap_unit', c.c_int), ('bitmap_bit_order', c.c_int),
                ('bitmap_pad', c.c_int), ('depth', c.c_int),
                ('bytes_per_line', c.c_int), ('bits_per_pixel', c.c_int)]


def main():
    window, width, height = map(int, sys.argv[1:4])
    destination = Path(sys.argv[4])
    x = c.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes = [c.c_char_p]; x.XOpenDisplay.restype = c.c_void_p
    x.XGetImage.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_ulong, c.c_int]
    x.XGetImage.restype = c.POINTER(XImage)
    x.XDestroyImage.argtypes = [c.POINTER(XImage)]
    x.XCloseDisplay.argtypes = [c.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 display unavailable')
    try:
        image = x.XGetImage(display, window, 0, 0, width, height, c.c_ulong(-1).value, 2)
        if not image:
            raise RuntimeError('Cannot capture app window')
        try:
            info = image.contents
            if info.bits_per_pixel != 32 or info.byte_order != 0:
                raise RuntimeError(f'Unsupported X11 pixel format: {info.bits_per_pixel}')
            data = c.string_at(info.data, info.bytes_per_line * info.height)
            screenshot = Image.frombytes('RGB', (info.width, info.height), data, 'raw', 'BGRX', info.bytes_per_line)
            destination.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(destination)
            print(destination)
        finally:
            x.XDestroyImage(image)
    finally:
        x.XCloseDisplay(display)


if __name__ == '__main__':
    main()

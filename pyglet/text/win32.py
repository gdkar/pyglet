#!/usr/bin/env python

'''
'''

from ctypes import *

from pyglet.GL.VERSION_1_1 import *
from pyglet.text import *
from pyglet.window.win32.constants import *
from pyglet.window.win32.types import *
from pyglet.window.win32 import _gdi32 as gdi32, _user32 as user32
from pyglet.window.win32 import _kernel32 as kernel32
from pyglet.window.win32 import _check

HFONT = HANDLE
HBITMAP = HANDLE
HDC = HANDLE
HGDIOBJ = HANDLE
gdi32.CreateFontIndirectA.restype = HFONT
gdi32.CreateCompatibleBitmap.restype = HBITMAP
gdi32.CreateCompatibleDC.restype = HDC
user32.GetDC.restype = HDC
gdi32.GetStockObject.restype = HGDIOBJ
gdi32.CreateDIBSection.restype = HBITMAP

class LOGFONT(Structure):
    _fields_ = [
        ('lfHeight', c_long),
        ('lfWidth', c_long),
        ('lfEscapement', c_long),
        ('lfOrientation', c_long),
        ('lfWeight', c_long),
        ('lfItalic', c_byte),
        ('lfUnderline', c_byte),
        ('lfStrikeOut', c_byte),
        ('lfCharSet', c_byte),
        ('lfOutPrecision', c_byte),
        ('lfClipPrecision', c_byte),
        ('lfQuality', c_byte),
        ('lfPitchAndFamily', c_byte),
        ('lfFaceName', (c_char * LF_FACESIZE))  # Use ASCII
    ]
    __slots__ = [f[0] for f in _fields_]

class TEXTMETRIC(Structure):
    _fields_ = [
        ('tmHeight', c_long),
        ('tmAscent', c_long),
        ('tmDescent', c_long),
        ('tmInternalLeading', c_long),
        ('tmExternalLeading', c_long),
        ('tmAveCharWidth', c_long),
        ('tmMaxCharWidth', c_long),
        ('tmWeight', c_long),
        ('tmOverhang', c_long),
        ('tmDigitizedAspectX', c_long),
        ('tmDigitizedAspectY', c_long),
        ('tmFirstChar', c_char),  # Use ASCII 
        ('tmLastChar', c_char),
        ('tmDefaultChar', c_char),
        ('tmBreakChar', c_char),
        ('tmItalic', c_byte),
        ('tmUnderlined', c_byte),
        ('tmStruckOut', c_byte),
        ('tmPitchAndFamily', c_byte),
        ('tmCharSet', c_byte)
    ]
    __slots__ = [f[0] for f in _fields_]

class ABC(Structure):
    _fields_ = [
        ('abcA', c_int),
        ('abcB', c_uint),
        ('abcC', c_int)
    ]
    __slots__ = [f[0] for f in _fields_]

class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ('biSize', c_uint32),
        ('biWidth', c_int),
        ('biHeight', c_int),
        ('biPlanes', c_short),
        ('biBitCount', c_short),
        ('biCompression', c_uint32),
        ('biSizeImage', c_uint32),
        ('biXPelsPerMeter', c_long),
        ('biYPelsPerMeter', c_long),
        ('biClrUser', c_uint32),
        ('biClrImportant', c_uint32)
    ]
    __slots__ = [f[0] for f in _fields_]

class RGBQUAD(Structure):
    _fields_ = [
        ('rgbBlue', c_byte),
        ('rgbGreen', c_byte),
        ('rgbRed', c_byte),
        ('rgbReserved', c_byte)
    ]

    def __init__(self, r, g, b):
        self.rgbRed = r
        self.rgbGreen = g
        self.rgbBlue = b


class BITMAPINFO(Structure):
    _fields_ = [
        ('bmiHeader', BITMAPINFOHEADER),
        ('bmiColors', RGBQUAD * 256)
    ]

def str_ucs2(text):
    if byteorder == 'big':
        text = text.encode('utf_16_be')
    else:
        text = text.encode('utf_16_le')   # explicit endian avoids BOM
    return create_string_buffer(text + '\0')

class Win32GlyphTextureAtlas(GlyphTextureAtlas):
    pass

class Win32GlyphRenderer(GlyphRenderer):
    _bitmap = None
    _bitmap_dc = None
    _bitmap_rect = None

    def __init__(self, font):
        super(Win32GlyphRenderer, self).__init__(font)
        self.font = font
        self._create_bitmap_dc(font.max_glyph_width, font.ascent - font.descent) 
        self._black = gdi32.GetStockObject(BLACK_BRUSH)
        self._white = gdi32.GetStockObject(WHITE_BRUSH)

    def __del__(self):
        if self._bitmap_dc:
            gdi32.DeleteDC(self._bitmap_dc)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)

    def render(self, text):
        gdi32.SelectObject(self._bitmap_dc, self._bitmap)
        gdi32.SelectObject(self._bitmap_dc, self.font.hfont)
        gdi32.SetBkColor(self._bitmap_dc, 0)
        gdi32.SetTextColor(self._bitmap_dc, 0x00ffffff)

        # Attempt to get ABC widths (only for TrueType)
        abc = ABC()
        if gdi32.GetCharABCWidthsW(self._bitmap_dc, 
            ord(text), ord(text), byref(abc)):
            width = abc.abcB 
            lsb = abc.abcA
            advance = abc.abcA + abc.abcB + abc.abcC
        else:
            width_buf = c_int()
            gdi32.GetCharWidth32(self._bitmap_dc, 
                ord(text), ord(text), byref(width_buf))
            width = width_buf.value
            lsb = 0
            advance = width

        # Can't get glyph-specific dimensions, use whole line-height.
        height = self._bitmap_rect.bottom

        # Draw to DC
        user32.FillRect(self._bitmap_dc, byref(self._bitmap_rect), self._black)
        gdi32.ExtTextOutA(self._bitmap_dc, -lsb, 0, 0, c_void_p(), text,
            len(text), c_void_p())
        gdi32.GdiFlush()

        # Create glyph object and copy bitmap data to texture
        glyph = self.font.allocate_glyph(width, height)
        glyph.set_bearings(-self.font.descent, lsb, advance)

        # Bizareness: GL_TEXTURE must be enabled for TexImage...?
        # --> This seems to be a Win32 issue only.  Move into pyglet.image?
        glPushAttrib(GL_ENABLE_BIT)
        glBindTexture(GL_TEXTURE_2D, glyph.texture.id)
        glEnable(GL_TEXTURE_2D)
        glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT)
        glPixelStorei(GL_UNPACK_ROW_LENGTH, self._bitmap_rect.right)
        glTexSubImage2D(GL_TEXTURE_2D, 0,
            glyph.x, glyph.y,
            glyph.width, glyph.height,
            GL_ALPHA,
            GL_UNSIGNED_BYTE,
            self._bitmap_data)
        glPopClientAttrib()
        glPopAttrib()

        return glyph
        
    def _create_bitmap_dc(self, width, height):
        if self._bitmap_dc:
            gdi32.ReleaseDC(self._bitmap_dc)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)

        pitch = width
        data = POINTER(c_byte * (height * pitch))()
        info = BITMAPINFO()
        info.bmiHeader.biSize = sizeof(info.bmiHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 8
        info.bmiHeader.biCompression = BI_RGB
        info.bmiColors[:] = [RGBQUAD(i, i, i) for i in range(256)]

        self._bitmap_dc = gdi32.CreateCompatibleDC(c_void_p())
        self._bitmap = gdi32.CreateDIBSection(c_void_p(),
            byref(info), DIB_RGB_COLORS, byref(data), c_void_p(),
            0)
        # Spookiness: the above line causes a "not enough storage" error,
        # even though that error cannot be generated according to docs,
        # and everything works fine anyway.  Call SetLastError to clear it.
        kernel32.SetLastError(0)

        self._bitmap_data = data.contents
        self._bitmap_rect = RECT()
        self._bitmap_rect.left = 0
        self._bitmap_rect.right = width
        self._bitmap_rect.top = 0
        self._bitmap_rect.bottom = height

class Win32Font(BaseFont):
    glyph_renderer_class = Win32GlyphRenderer
    glyph_texture_atlas_class = Win32GlyphTextureAtlas

    def __init__(self, name, size, bold=False, italic=False):
        super(Win32Font, self).__init__()

        self.hfont = self.get_hfont(name, size, bold, italic)

        # Create a dummy DC for coordinate mapping
        dc = user32.GetDC(0)
        logpixelsy = gdi32.GetDeviceCaps(dc, LOGPIXELSY)

        metrics = TEXTMETRIC()
        gdi32.SelectObject(dc, self.hfont)
        gdi32.GetTextMetricsA(dc, byref(metrics))
        self.ascent = metrics.tmAscent
        self.descent = -metrics.tmDescent
        self.max_glyph_width = metrics.tmMaxCharWidth

    @staticmethod
    def get_hfont(name, size, bold, italic):
        # Create a dummy DC for coordinate mapping
        dc = user32.GetDC(0)
        logpixelsy = gdi32.GetDeviceCaps(dc, LOGPIXELSY)

        logfont = LOGFONT()
        # Conversion of point size to device pixels
        logfont.lfHeight = int(-size * logpixelsy / 72)
        if bold:
            logfont.lfWeight = FW_BOLD
        else:
            logfont.lfWeight = FW_NORMAL
        logfont.lfItalic = italic
        logfont.lfFaceName = name
        logfont.lfQuality = ANTIALIASED_QUALITY
        hfont = gdi32.CreateFontIndirectA(byref(logfont))
        return hfont

    @classmethod
    def have_font(cls, name):
        # CreateFontIndirect always returns a font... have to work out
        # something with EnumFontFamily... TODO
        return True

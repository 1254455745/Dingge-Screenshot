from html import escape
import ctypes
import ctypes.util
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    from pynput import keyboard as pynput_keyboard
except ImportError:
    pynput_keyboard = None

try:
    from PySide6.QtCore import (
        QByteArray,
        QBuffer,
        QEvent,
        QIODevice,
        QPoint,
        QRect,
        QSettings,
        QSize,
        QTimer,
        Qt,
        QUrl,
        Signal,
    )
    from PySide6.QtGui import (
        QAction,
        QColor,
        QCursor,
        QDesktopServices,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractSpinBox,
        QButtonGroup,
        QCheckBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGraphicsOpacityEffect,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QAbstractScrollArea,
        QScrollArea,
        QSystemTrayIcon,
        QSizePolicy,
        QDoubleSpinBox,
        QStackedWidget,
        QTimeEdit,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    message = "缺少界面依赖 PySide6_Essentials。\n\n请先运行：python -m pip install PySide6_Essentials"
    if platform.system() == "Darwin":
        applescript = (
            f'display dialog "{message}" '
            'buttons {"知道了"} default button "知道了" with title "定格截图"'
        )
        subprocess.run(["osascript", "-e", applescript], check=False)
    else:
        print(message, file=sys.stderr)
    raise SystemExit("Missing PySide6_Essentials")


PYOBJC_AVAILABLE = False
if platform.system() == "Darwin":
    try:
        import objc
        from AppKit import (
            NSApp,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
            NSImageOnly,
            NSImageScaleProportionallyDown,
            NSMenu,
            NSMenuItem,
            NSStatusBar,
            NSEventMaskLeftMouseUp,
            NSEventMaskRightMouseUp,
            NSEventTypeRightMouseUp,
            NSImage,
        )
        from Foundation import NSData, NSObject

        PYOBJC_AVAILABLE = True
    except ImportError:
        PYOBJC_AVAILABLE = False


SETTINGS_ORGANIZATION = "Anzhen"
SETTINGS_APPLICATION = "TimedScreenshotTool"
SETTINGS_LAYOUT_VERSION = 7
APP_DISPLAY_NAME = "定格截图"
APP_VERSION = "1.0.2"
DEFAULT_CAPTURE_SHORTCUT = "Ctrl+Shift+1"


def app_base_dir() -> Path:
    frozen_dir = getattr(sys, "_MEIPASS", None)
    if frozen_dir:
        return Path(frozen_dir)
    return Path(__file__).resolve().parent


def default_save_dir() -> Path:
    documents_dir = Path.home() / "Documents"
    if not documents_dir.exists():
        documents_dir = Path.home()
    return documents_dir / "Dingge-Screenshot" / "screenshots"


APP_DIR = app_base_dir()
LOGO_PATH = APP_DIR / "assets" / "定格截图logo.png"
STATUSBAR_ICON_SVG_PATH = APP_DIR / "assets" / "statusbar-icon.svg"
GITHUB_URL = "https://github.com/1254455745/Dingge-Screenshot"
GITHUB_RELEASES_URL = f"{GITHUB_URL}/releases"
GITHUB_LATEST_RELEASE_URL = f"{GITHUB_RELEASES_URL}/latest"
AUTHOR_NAME = "zhenan"
MAX_CAPTURE_IMAGES_PER_RUN = 10000

DEFAULT_WINDOW_WIDTH = 1030
DEFAULT_WINDOW_HEIGHT = 760
MIN_WINDOW_WIDTH = 920
MIN_WINDOW_HEIGHT = 660
SECTION_LABEL_HEIGHT = 24

TIME_CHIP_WIDTH = 88
TIME_CHIP_HEIGHT = 38
TIME_GRID_SPACING = 8
DEFAULT_TIME_ROWS = 4
MIN_TIME_ROWS = 2

RULE_BUTTON_HEIGHT = 42
INTERVAL_CONTROL_WIDTH = 130
UNIT_BUTTON_WIDTH = 68
MAC_STATUS_ICON_SIZE = 16
MAC_STATUS_ITEM_LENGTH = 22

CAPTURE_TARGET_FULLSCREEN = 0
CAPTURE_TARGET_CUSTOM = 1
CAPTURE_TARGET_BROWSER = 2

CLOSE_BEHAVIOR_ASK = "ask"
CLOSE_BEHAVIOR_TRAY = "tray"
CLOSE_BEHAVIOR_QUIT = "quit"

TRAY_STATE_IDLE = "idle"
TRAY_STATE_ACTIVE = "active"
TRAY_STATE_ERROR = "error"

MAC_CARBON_AVAILABLE = False
MAC_HOTKEY_EVENT_CLASS = int.from_bytes(b"keyb", "big")
MAC_HOTKEY_EVENT_KIND_PRESSED = 5
MAC_HOTKEY_SIGNATURE = int.from_bytes(b"DGSC", "big")
MAC_HOTKEY_ID_CAPTURE_ONCE = 1


class MacEventTypeSpec(ctypes.Structure):
    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


class MacEventHotKeyID(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


MacEventHandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


if platform.system() == "Darwin":
    try:
        _CARBON_PATH = ctypes.util.find_library("Carbon")
        if _CARBON_PATH:
            MAC_CARBON = ctypes.cdll.LoadLibrary(_CARBON_PATH)
            MAC_CARBON.GetEventDispatcherTarget.argtypes = []
            MAC_CARBON.GetEventDispatcherTarget.restype = ctypes.c_void_p
            MAC_CARBON.InstallEventHandler.argtypes = [
                ctypes.c_void_p,
                MacEventHandlerProc,
                ctypes.c_uint32,
                ctypes.POINTER(MacEventTypeSpec),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            MAC_CARBON.InstallEventHandler.restype = ctypes.c_int32
            MAC_CARBON.RemoveEventHandler.argtypes = [ctypes.c_void_p]
            MAC_CARBON.RemoveEventHandler.restype = ctypes.c_int32
            MAC_CARBON.RegisterEventHotKey.argtypes = [
                ctypes.c_uint32,
                ctypes.c_uint32,
                MacEventHotKeyID,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            MAC_CARBON.RegisterEventHotKey.restype = ctypes.c_int32
            MAC_CARBON.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
            MAC_CARBON.UnregisterEventHotKey.restype = ctypes.c_int32
            MAC_CARBON_AVAILABLE = True
        else:
            MAC_CARBON = None
    except Exception:
        MAC_CARBON = None
        MAC_CARBON_AVAILABLE = False
else:
    MAC_CARBON = None

MAC_CARBON_CMD = 1 << 8
MAC_CARBON_SHIFT = 1 << 9
MAC_CARBON_OPTION = 1 << 11
MAC_CARBON_CONTROL = 1 << 12

MAC_CARBON_KEYCODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "return": 36,
    "enter": 36,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "tab": 48,
    "space": 49,
    "`": 50,
    "backspace": 51,
    "esc": 53,
    "delete": 117,
    "home": 115,
    "end": 119,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "pgup": 116,
    "pgdown": 121,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
    "f13": 105,
    "f14": 107,
    "f15": 113,
    "f16": 106,
    "f17": 64,
    "f18": 79,
    "f19": 80,
    "f20": 90,
}

BROWSER_APPS = (
    ("Google Chrome", "Chrome"),
    ("Safari", "Safari"),
    ("Microsoft Edge", "Edge"),
    ("Brave Browser", "Brave"),
    ("Arc", "Arc"),
)

WINDOWS_BROWSER_TAB_SAFETY_LIMIT = 80
WINDOWS_BROWSER_PAGE_DELAY_SECONDS = 0.45
WINDOWS_BROWSER_EXECUTABLES = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "opera_gx.exe": "OperaGX",
}


def logo_pixmap(size: int) -> QPixmap:
    if not LOGO_PATH.exists():
        return QPixmap()
    return QPixmap(str(LOGO_PATH)).scaled(
        size,
        size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def app_icon_pixmap(size: int) -> QPixmap:
    base = QPixmap(size, size)
    base.fill(QColor(0, 0, 0, 0))

    logo = logo_pixmap(round(size * 0.72))
    if logo.isNull():
        return logo

    painter = QPainter(base)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    x = (size - logo.width()) // 2
    y = (size - logo.height()) // 2
    painter.drawPixmap(x, y, logo)
    painter.end()
    return base


def image_based_template_pixmap(source_path: Path, size: int) -> QPixmap:
    source = QPixmap(str(source_path))
    if source.isNull():
        return QPixmap()

    normalized = trim_transparent_image(normalize_template_image(source.toImage()))
    return QPixmap.fromImage(normalized).scaled(
        size,
        size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def normalize_template_image(image: QImage) -> QImage:
    normalized = image.convertToFormat(QImage.Format.Format_ARGB32)
    width = normalized.width()
    height = normalized.height()

    for y in range(height):
        for x in range(width):
            color = normalized.pixelColor(x, y)
            if color.alpha() == 0:
                continue

            brightness = (color.red() + color.green() + color.blue()) / 3
            if brightness < 80:
                color.setAlpha(0)
            else:
                color.setRed(255)
                color.setGreen(255)
                color.setBlue(255)
                color.setAlpha(255)
            normalized.setPixelColor(x, y, color)

    return normalized


def trim_transparent_image(image: QImage) -> QImage:
    left = image.width()
    top = image.height()
    right = -1
    bottom = -1

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return image
    return image.copy(left, top, right - left + 1, bottom - top + 1)


def svg_file_pixmap(source_path: Path, size: int) -> QPixmap:
    if not source_path.exists():
        return QPixmap()

    render_size = size * 2 if platform.system() == "Darwin" else size
    pixmap = QPixmap(render_size, render_size)
    pixmap.fill(QColor(0, 0, 0, 0))

    renderer = QSvgRenderer(str(source_path))
    if not renderer.isValid():
        return QPixmap()

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    normalized_image = normalize_template_image(pixmap.toImage())
    normalized = QPixmap.fromImage(
        normalized_image.scaled(
            render_size,
            render_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
    )
    if platform.system() == "Darwin":
        normalized.setDevicePixelRatio(2.0)
    return normalized


def mac_tray_template_pixmap(size: int) -> QPixmap:
    if STATUSBAR_ICON_SVG_PATH.exists():
        pixmap = svg_file_pixmap(STATUSBAR_ICON_SVG_PATH, size)
        if not pixmap.isNull():
            return pixmap

    canvas_size = max(24, size * 2)
    pixmap = QPixmap(canvas_size, canvas_size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    outer_pen = QPen(QColor("#ffffff"), canvas_size * 0.085, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    inner_pen = QPen(QColor("#ffffff"), canvas_size * 0.066, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setBrush(Qt.NoBrush)

    body_path = QPainterPath()
    body_path.addRoundedRect(
        canvas_size * 0.31,
        canvas_size * 0.16,
        canvas_size * 0.50,
        canvas_size * 0.68,
        canvas_size * 0.11,
        canvas_size * 0.11,
    )
    painter.setPen(outer_pen)
    painter.drawPath(body_path)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(
        canvas_size * 0.72,
        canvas_size * 0.35,
        canvas_size * 0.10,
        canvas_size * 0.10,
        canvas_size * 0.03,
        canvas_size * 0.03,
    )

    bolt = QPainterPath()
    bolt.moveTo(canvas_size * 0.12, canvas_size * 0.18)
    bolt.lineTo(canvas_size * 0.27, canvas_size * 0.18)
    bolt.lineTo(canvas_size * 0.21, canvas_size * 0.35)
    bolt.lineTo(canvas_size * 0.34, canvas_size * 0.35)
    bolt.lineTo(canvas_size * 0.17, canvas_size * 0.63)
    bolt.lineTo(canvas_size * 0.22, canvas_size * 0.44)
    bolt.lineTo(canvas_size * 0.10, canvas_size * 0.44)
    bolt.closeSubpath()
    painter.drawPath(bolt)

    painter.setPen(inner_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(
        QRect(
            round(canvas_size * 0.20),
            round(canvas_size * 0.24),
            round(canvas_size * 0.46),
            round(canvas_size * 0.46),
        )
    )

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    play = QPainterPath()
    play.moveTo(canvas_size * 0.31, canvas_size * 0.33)
    play.lineTo(canvas_size * 0.31, canvas_size * 0.61)
    play.lineTo(canvas_size * 0.55, canvas_size * 0.47)
    play.closeSubpath()
    painter.drawPath(play)
    painter.end()

    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def tray_status_icon(state: str, size: int = 22) -> QIcon:
    if platform.system() == "Darwin":
        pixmap = mac_tray_template_pixmap(size)
    else:
        pixmap = app_icon_pixmap(size)
        if pixmap.isNull():
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#f5f5f7"))
            painter.setPen(QPen(QColor("#5f6368"), 1.4))
            painter.drawEllipse(2, 2, size - 4, size - 4)
            painter.end()

    if state != TRAY_STATE_IDLE:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor("#30d158") if state == TRAY_STATE_ACTIVE else QColor("#ff3b30")
        badge_size = max(7, round(size * 0.32))
        badge_x = size - badge_size - 1
        badge_y = size - badge_size - 1
        painter.setBrush(color)
        painter.setPen(QPen(QColor("white"), 1.6))
        painter.drawEllipse(badge_x, badge_y, badge_size, badge_size)
        painter.end()

    icon = QIcon(pixmap)
    if platform.system() == "Darwin" and state == TRAY_STATE_IDLE:
        icon.setIsMask(True)
    return icon


def settings_icon_pixmap(size: int) -> QPixmap:
    return svg_icon_pixmap(
        size,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
          <path d="M12.22 2h-.44a2 2 0 0 0-1.94 1.5l-.24.9a2 2 0 0 1-2.45 1.41l-.9-.24a2 2 0 0 0-2.38 1l-.22.38a2 2 0 0 0 .73 2.73l.76.44a2 2 0 0 1 0 3.46l-.76.44a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.38 1l.9-.24a2 2 0 0 1 2.45 1.41l.24.9a2 2 0 0 0 1.94 1.5h.44a2 2 0 0 0 1.94-1.5l.24-.9a2 2 0 0 1 2.45-1.41l.9.24a2 2 0 0 0 2.38-1l.22-.38a2 2 0 0 0-.73-2.73l-.76-.44a2 2 0 0 1 0-3.46l.76-.44a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.38-1l-.9.24a2 2 0 0 1-2.45-1.41l-.24-.9A2 2 0 0 0 12.22 2Z"
                stroke="#6e6e73" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="12" cy="12" r="3" stroke="#6e6e73" stroke-width="1.65"/>
        </svg>
        """,
    )


def svg_icon_pixmap(size: int, svg: str) -> QPixmap:
    render_size = size * 2 if platform.system() == "Darwin" else size
    icon = QPixmap(render_size, render_size)
    icon.fill(QColor(0, 0, 0, 0))
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(icon)
    renderer.render(painter)
    painter.end()
    if platform.system() == "Darwin":
        icon.setDevicePixelRatio(2.0)
    return icon


def github_icon_pixmap(size: int) -> QPixmap:
    return svg_icon_pixmap(
        size,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <path fill="#1d1d1f" d="M12 .297C5.37.297 0 5.67 0 12.297c0 5.303 3.438 9.8 8.207 11.387.6.113.82-.258.82-.578 0-.285-.01-1.04-.016-2.04-3.338.727-4.043-1.608-4.043-1.608-.547-1.387-1.336-1.758-1.336-1.758-1.09-.746.083-.73.083-.73 1.205.086 1.84 1.238 1.84 1.238 1.07 1.835 2.808 1.305 3.492.997.108-.775.418-1.305.762-1.605-2.665-.303-5.466-1.333-5.466-5.93 0-1.31.467-2.38 1.235-3.22-.124-.303-.535-1.523.117-3.176 0 0 1.008-.322 3.3 1.23a11.48 11.48 0 0 1 3.005-.404c1.02.005 2.047.138 3.006.404 2.29-1.552 3.296-1.23 3.296-1.23.654 1.653.243 2.873.12 3.176.77.84 1.233 1.91 1.233 3.22 0 4.61-2.805 5.624-5.477 5.92.43.37.814 1.103.814 2.222 0 1.605-.015 2.898-.015 3.293 0 .322.216.697.825.58C20.565 22.092 24 17.597 24 12.297c0-6.627-5.373-12-12-12"/>
        </svg>
        """,
    )


def close_mode_icon_pixmap(mode: str, size: int, color: str = "#1d1d1f") -> QPixmap:
    if mode == "tray":
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <rect x="4" y="5" width="16" height="11" rx="3" fill="none" stroke="{color}" stroke-width="2"/>
          <path d="M8 19.5h8" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
          <path d="M12 8v5" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
          <path d="m9.5 11 2.5 2.5L14.5 11" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        """
    elif mode == "quit":
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="8" fill="none" stroke="{color}" stroke-width="2"/>
          <path d="m9.2 9.2 5.6 5.6m0-5.6-5.6 5.6" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
        </svg>
        """
    else:
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="8" fill="none" stroke="{color}" stroke-width="2"/>
        </svg>
        """
    return svg_icon_pixmap(size, svg)


def settings_page_icon_pixmap(page: str, size: int, color: str = "#4b4b51") -> QPixmap:
    icons = {
        "general": f"""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <path d="M8 5h8a2 2 0 0 1 2 2v4H6V7a2 2 0 0 1 2-2Z" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>
              <path d="M6 11h12v2a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5v-2Z" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>
              <path d="M10 8h4" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
            </svg>
        """,
        "shortcut": f"""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <rect x="4" y="6" width="16" height="12" rx="3" fill="none" stroke="{color}" stroke-width="2"/>
              <path d="M8 10h2M12 10h4M8 14h8" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
            </svg>
        """,
        "updates": f"""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <path d="M12 5v8m0 0-3-3m3 3 3-3" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6 14a6 6 0 0 0 11.2 2M18 10A6 6 0 0 0 6.8 8" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
            </svg>
        """,
        "about": f"""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="9" fill="none" stroke="{color}" stroke-width="2"/>
              <circle cx="12" cy="8" r="1.4" fill="{color}"/>
              <path d="M12 11v5" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
            </svg>
        """,
    }
    return svg_icon_pixmap(size, icons.get(page, icons["general"]))


def nsimage_from_pixmap(pixmap: QPixmap):
    if not PYOBJC_AVAILABLE or pixmap.isNull():
        return None

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()

    image_data = NSData.dataWithBytes_length_(byte_array.data(), byte_array.size())
    return NSImage.alloc().initWithData_(image_data)


def mac_application_icon_image():
    if not PYOBJC_AVAILABLE:
        return None
    return nsimage_from_pixmap(app_icon_pixmap(256))


SHIFTED_SHORTCUT_KEYS = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
    "~": "`",
}


def normalize_shortcut_sequence(sequence: str) -> str:
    text = (sequence or "").strip()
    if not text:
        return ""
    key_sequence = QKeySequence.fromString(text, QKeySequence.PortableText)
    normalized = key_sequence.toString(QKeySequence.PortableText).strip()
    if not normalized:
        return ""
    if "," in normalized:
        normalized = normalized.split(",", 1)[0].strip()
    parts = [part.strip() for part in normalized.split("+") if part.strip()]
    if parts and parts[-1] in SHIFTED_SHORTCUT_KEYS:
        if "Shift" not in parts[:-1]:
            parts.insert(len(parts) - 1, "Shift")
        parts[-1] = SHIFTED_SHORTCUT_KEYS[parts[-1]]
        normalized = "+".join(parts)
    return normalized


def shortcut_display_text(sequence: str) -> str:
    normalized = normalize_shortcut_sequence(sequence)
    if not normalized:
        return "未设置"
    key_sequence = QKeySequence.fromString(normalized, QKeySequence.PortableText)
    return key_sequence.toString(QKeySequence.NativeText) or normalized


def shortcut_to_pynput(sequence: str) -> str:
    normalized = normalize_shortcut_sequence(sequence)
    if not normalized:
        return ""

    if platform.system() == "Darwin":
        modifier_map = {
            "Ctrl": "<cmd>",
            "Shift": "<shift>",
            "Alt": "<alt>",
            "Meta": "<ctrl>",
        }
    else:
        modifier_map = {
            "Ctrl": "<ctrl>",
            "Shift": "<shift>",
            "Alt": "<alt>",
            "Meta": "<cmd>",
        }
    key_map = {
        "Space": "<space>",
        "Tab": "<tab>",
        "Backtab": "<tab>",
        "Backspace": "<backspace>",
        "Return": "<enter>",
        "Enter": "<enter>",
        "Esc": "<esc>",
        "Del": "<delete>",
        "Delete": "<delete>",
        "Insert": "<insert>",
        "Home": "<home>",
        "End": "<end>",
        "Left": "<left>",
        "Right": "<right>",
        "Up": "<up>",
        "Down": "<down>",
        "PgUp": "<page_up>",
        "PgDown": "<page_down>",
    }

    parts = [part.strip() for part in normalized.split("+") if part.strip()]
    listener_parts: list[str] = []
    non_modifier_key = ""
    for part in parts:
        if part in modifier_map:
            listener_parts.append(modifier_map[part])
            continue
        if part in key_map:
            non_modifier_key = key_map[part]
            continue
        if re.fullmatch(r"F([1-9]|1\d|2[0-4])", part):
            non_modifier_key = f"<{part.lower()}>"
            continue
        if len(part) == 1:
            non_modifier_key = part.lower()
            continue
        raise ValueError("快捷键暂时只支持常见组合键，请换一个简单一点的组合。")

    if not non_modifier_key:
        raise ValueError("快捷键至少需要包含一个可触发的按键。")

    if listener_parts:
        listener_parts.append(non_modifier_key)
    else:
        listener_parts = [non_modifier_key]
    return "+".join(listener_parts)


def shortcut_to_mac_carbon(sequence: str) -> tuple[int, int]:
    normalized = normalize_shortcut_sequence(sequence)
    if not normalized:
        raise ValueError("快捷键为空。")

    modifier_map = {
        "Ctrl": MAC_CARBON_CMD,
        "Shift": MAC_CARBON_SHIFT,
        "Alt": MAC_CARBON_OPTION,
        "Meta": MAC_CARBON_CONTROL,
    }
    key_name_map = {
        "Space": "space",
        "Tab": "tab",
        "Backtab": "tab",
        "Backspace": "backspace",
        "Return": "return",
        "Enter": "enter",
        "Esc": "esc",
        "Del": "delete",
        "Delete": "delete",
        "Insert": "insert",
        "Home": "home",
        "End": "end",
        "Left": "left",
        "Right": "right",
        "Up": "up",
        "Down": "down",
        "PgUp": "pgup",
        "PgDown": "pgdown",
    }

    modifiers = 0
    keycode: Optional[int] = None
    for part in [item.strip() for item in normalized.split("+") if item.strip()]:
        if part in modifier_map:
            modifiers |= modifier_map[part]
            continue

        lookup = key_name_map.get(part, part.lower())
        if lookup == "insert":
            raise ValueError("Mac 全局快捷键暂时不支持 Insert 键。")
        if len(lookup) == 1 and lookup.isalpha():
            lookup = lookup.lower()
        if lookup not in MAC_CARBON_KEYCODES:
            raise ValueError("这个快捷键暂时无法注册为 Mac 全局快捷键，请换一个常见按键。")
        if keycode is not None:
            raise ValueError("快捷键只能包含一个主按键。")
        keycode = MAC_CARBON_KEYCODES[lookup]

    if keycode is None:
        raise ValueError("快捷键至少需要包含一个可触发的按键。")
    return keycode, modifiers


def portable_sequence_from_key_event(event) -> str:
    key = event.key()
    modifiers = event.modifiers()
    key_value = int(getattr(key, "value", key))
    modifier_value = int(getattr(modifiers, "value", modifiers))
    sequence = QKeySequence(modifier_value | key_value).toString(QKeySequence.PortableText)
    return normalize_shortcut_sequence(sequence)


def version_parts(version: str) -> list[int]:
    normalized = version.strip().lstrip("vV")
    normalized = re.split(r"[-+]", normalized, maxsplit=1)[0]
    parts = []
    for part in normalized.split("."):
        match = re.match(r"\d+", part)
        parts.append(int(match.group(0)) if match else 0)
    return parts or [0]


def compare_versions(left: str, right: str) -> int:
    left_parts = version_parts(left)
    right_parts = version_parts(right)
    size = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (size - len(left_parts)))
    right_parts.extend([0] * (size - len(right_parts)))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


@dataclass
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int


@dataclass
class BrowserTab:
    app_name: str
    display_name: str
    window_index: int
    tab_index: int
    title: str
    url: str


@dataclass
class CaptureRecord:
    captured_at: datetime
    filepath: Path
    capture_type: str
    page_title: str = ""
    url: str = ""
    browser_name: str = ""


class SelectionOverlay(QWidget):
    selection_made = Signal(object)
    selection_cancelled = Signal()

    def __init__(self, screen, background: QPixmap):
        super().__init__(None)
        self.screen = screen
        self.background = background
        self.origin = QPoint()
        self.current = QPoint()
        self.dragging = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setGeometry(screen.geometry())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        self.current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragging:
            return

        self.dragging = False
        self.current = event.position().toPoint()
        rect = QRect(self.origin, self.current).normalized()
        if rect.width() < 20 or rect.height() < 20:
            self.selection_cancelled.emit()
            self.close()
            return

        screen_geo = self.screen.geometry()
        ratio = self.screen.devicePixelRatio()
        region = CaptureRegion(
            x=round((screen_geo.x() + rect.x()) * ratio),
            y=round((screen_geo.y() + rect.y()) * ratio),
            width=round(rect.width() * ratio),
            height=round(rect.height() * ratio),
        )
        self.selection_made.emit(region)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(8, 12, 20, 118))

        rect = QRect(self.origin, self.current).normalized()
        if self.dragging and not rect.isNull():
            if self.background.isNull():
                painter.save()
                painter.setCompositionMode(QPainter.CompositionMode_Clear)
                painter.fillRect(rect, QColor(0, 0, 0, 0))
                painter.restore()
            else:
                painter.save()
                painter.setClipRect(rect)
                self.draw_background(painter)
                painter.restore()

            painter.setPen(QPen(QColor("#0A84FF"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -2, -2), 8, 8)

            painter.setPen(QColor("white"))
            painter.setFont(QFont("PingFang SC", 12, QFont.Medium))
            painter.drawText(
                rect.left(),
                max(24, rect.top() - 10),
                f"{rect.width()} x {rect.height()}",
            )

        hint_rect = QRect(20, 18, 236, 62)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawRoundedRect(hint_rect, 14, 14)

        painter.setPen(QColor("white"))
        painter.setFont(QFont("PingFang SC", 14, QFont.Bold))
        painter.drawText(28, 42, "拖拽选择截图区域")
        painter.setFont(QFont("PingFang SC", 11))
        painter.drawText(28, 66, "松开鼠标确认，按 Esc 取消")

    def draw_background(self, painter: QPainter):
        if self.background.isNull():
            painter.fillRect(self.rect(), QColor("#1d1d1f"))
            return
        painter.drawPixmap(self.rect(), self.background)


class RegionPreviewOverlay(QWidget):
    def __init__(self, screen, region: CaptureRegion):
        super().__init__(None)
        self.screen = screen
        self.region = region
        self.preview_rect = self.region_to_overlay_rect(region)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setGeometry(screen.geometry())

    def region_to_overlay_rect(self, region: CaptureRegion) -> QRect:
        screen_geo = self.screen.geometry()
        ratio = self.screen.devicePixelRatio()
        return QRect(
            round(region.x / ratio - screen_geo.x()),
            round(region.y / ratio - screen_geo.y()),
            round(region.width / ratio),
            round(region.height / ratio),
        )

    def mousePressEvent(self, _event):
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.preview_rect.normalized()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(10, 132, 255, 26))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        pen = QPen(QColor("#0A84FF"), 2)
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -2, -2), 8, 8)


class StatCard(QFrame):
    def __init__(self, title: str, value: str):
        super().__init__()
        self.setObjectName("StatCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("StatTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class CountSummaryCard(QFrame):
    def __init__(self, current_value: str, total_value: str):
        super().__init__()
        self.setObjectName("StatCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        current_section = self.build_section("本次截图张数", current_value)
        total_section = self.build_section("共截图张数", total_value)

        divider = QFrame()
        divider.setObjectName("StatDivider")
        divider.setFixedWidth(1)

        layout.addWidget(current_section, 1)
        layout.addWidget(divider)
        layout.addWidget(total_section, 1)

    def build_section(self, title: str, value: str) -> QWidget:
        section = QWidget()
        section.setObjectName("CountStatSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("StatTitle")
        value_label = QLabel(value)
        value_label.setObjectName("StatValue")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        if "本次" in title:
            self.current_value_label = value_label
        else:
            self.total_value_label = value_label
        return section

    def set_current_value(self, value: str):
        self.current_value_label.setText(value)

    def set_total_value(self, value: str):
        self.total_value_label.setText(value)


class ShortcutBindingRow(QWidget):
    hovered_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("SettingsBindingRow")
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.hovered = False

    def enterEvent(self, event):
        self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(0, self.refresh_hover_state)
        super().leaveEvent(event)

    def refresh_hover_state(self):
        self.set_hovered(self.rect().contains(self.mapFromGlobal(QCursor.pos())))

    def set_hovered(self, hovered: bool):
        if self.hovered == hovered:
            return
        self.hovered = hovered
        self.hovered_changed.emit(hovered)


class ShortcutKeycapsWidget(QFrame):
    edit_requested = Signal()
    sequence_captured = Signal(str)

    def __init__(self, sequence: str = ""):
        super().__init__()
        self.setObjectName("ShortcutKeycaps")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 0, 14, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setFixedHeight(34)
        self.recording = False
        self.set_sequence(sequence)

    def set_visual_state(self, state: str, minimum_width: int):
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        self.setMinimumWidth(minimum_width)

    def set_sequence(self, sequence: str):
        self.recording = False
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        is_empty = normalize_shortcut_sequence(sequence) == ""
        label = QLabel("未设置" if is_empty else shortcut_display_text(sequence))
        label.setObjectName("ShortcutKeycapText")
        label.setAlignment(Qt.AlignCenter)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.layout.addWidget(label)
        self.set_visual_state("empty" if is_empty else "ready", max(116, label.sizeHint().width() + 28))

    def start_recording(self):
        self.recording = True
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        placeholder = QLabel("按下新的快捷键")
        placeholder.setObjectName("ShortcutKeycapText")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.layout.addWidget(placeholder)
        self.set_visual_state("recording", max(136, placeholder.sizeHint().width() + 28))
        self.setFocus(Qt.OtherFocusReason)

    def cancel_recording(self, sequence: str = ""):
        self.recording = False
        self.set_sequence(sequence)

    def keyPressEvent(self, event):
        if not self.recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()
        if key == Qt.Key_Escape:
            self.recording = False
            self.set_sequence("")
            event.accept()
            return

        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return

        normalized = portable_sequence_from_key_event(event)
        if normalized:
            self.recording = False
            self.sequence_captured.emit(normalized)
            event.accept()
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.recording:
            self.setFocus(Qt.MouseFocusReason)
            self.edit_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self.recording:
            self.recording = False
            self.set_sequence("")
        super().focusOutEvent(event)


class TimeChip(QFrame):
    remove_requested = Signal(str)

    def __init__(self, value: str):
        super().__init__()
        self.value = value
        self.setObjectName("TimeChip")
        self.setFixedSize(88, 38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 7, 6)
        layout.setSpacing(6)

        label = QLabel(value)
        label.setObjectName("TimeChipText")
        remove_btn = QPushButton("×")
        remove_btn.setObjectName("ChipRemoveButton")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.value))

        layout.addWidget(label)
        layout.addWidget(remove_btn)


class TimePointScrollArea(QScrollArea):
    def __init__(self, preferred_height: int, minimum_height: int):
        super().__init__()
        self.preferred_height = preferred_height
        self.setMinimumHeight(minimum_height)

    def sizeHint(self):
        return QSize(0, self.preferred_height)

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())


if PYOBJC_AVAILABLE:
    class MacStatusItemTarget(NSObject):
        def initWithWindow_(self, window):
            self = objc.super(MacStatusItemTarget, self).init()
            if self is None:
                return None
            self.window = window
            return self

        def handleStatusItemClick_(self, _sender):
            event = NSApp.currentEvent()
            event_type = event.type() if event is not None else None
            if event_type == NSEventTypeRightMouseUp:
                QTimer.singleShot(0, self.window.show_tray_context_menu)
                return
            QTimer.singleShot(0, self.window.show_main_window)

        def toggleMainWindow_(self, _sender):
            QTimer.singleShot(0, self.window.toggle_main_window_visibility)

        def startCapture_(self, _sender):
            QTimer.singleShot(0, self.window.start_capture)

        def captureOnce_(self, _sender):
            QTimer.singleShot(0, self.window.capture_once)

        def stopCapture_(self, _sender):
            QTimer.singleShot(0, self.window.stop_capture)

        def requestQuit_(self, _sender):
            QTimer.singleShot(0, self.window.request_quit)


class ScreenshotWindow(QMainWindow):
    update_check_finished = Signal(object)
    hotkey_triggered = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(app_icon_pixmap(256)))
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self.system_name = platform.system()
        self.save_dir = default_save_dir()
        self.capture_count = 0
        self.total_capture_count = 0
        self.running = False
        self.overlay: Optional[SelectionOverlay] = None
        self.preview_overlay: Optional[RegionPreviewOverlay] = None
        self.next_capture_at: Optional[datetime] = None
        self.pending_manual_resume_at: Optional[datetime] = None
        self.restore_geometry: Optional[QRect] = None
        self.restore_window_state = None
        self.report_lock = threading.Lock()
        self.browser_capture_apps: list[tuple[str, str]] = []
        self.browser_capture_apps_ready = False
        self.update_check_running = False
        self.update_check_button: Optional[QPushButton] = None
        self.update_check_silent = False
        self.auto_check_updates = True
        self.capture_shortcut_sequence = DEFAULT_CAPTURE_SHORTCUT
        self.capture_once_shortcut_action = QAction(self)
        self.capture_once_shortcut_action.setShortcutContext(Qt.ApplicationShortcut)
        self.capture_once_shortcut_action.triggered.connect(self.on_hotkey_triggered)
        self.addAction(self.capture_once_shortcut_action)
        self.settings_dialog: Optional[QDialog] = None
        self.shortcut_binding_row: Optional[ShortcutBindingRow] = None
        self.shortcut_preview_caps: Optional[ShortcutKeycapsWidget] = None
        self.shortcut_reset_button: Optional[QPushButton] = None
        self.shortcut_cancel_button: Optional[QPushButton] = None
        self.shortcut_status_label: Optional[QLabel] = None
        self.hotkey_listener = None
        self.hotkey_listener_error = ""
        self.mac_hotkey_handler_ref = None
        self.mac_hotkey_ref = None
        self.mac_hotkey_callback = None
        self.settings_dialog_open = False
        self.latest_release_tag = ""
        self.latest_release_url = GITHUB_RELEASES_URL
        self.about_latest_version_label: Optional[QLabel] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.tray_menu: Optional[QMenu] = None
        self.tray_show_action: Optional[QAction] = None
        self.tray_start_action: Optional[QAction] = None
        self.tray_capture_once_action: Optional[QAction] = None
        self.tray_stop_action: Optional[QAction] = None
        self.native_status_item = None
        self.native_status_button = None
        self.native_status_target = None
        self.native_status_menu = None
        self.native_menu_show_item = None
        self.native_menu_start_item = None
        self.native_menu_capture_once_item = None
        self.native_menu_stop_item = None
        self.native_menu_quit_item = None
        self.tray_context_menu_timer = QTimer(self)
        self.tray_context_menu_timer.setSingleShot(True)
        self.tray_context_menu_timer.timeout.connect(self.show_tray_context_menu)
        self.last_tray_primary_click_at = 0.0
        self.close_behavior = CLOSE_BEHAVIOR_ASK
        self.settings_page_group: Optional[QButtonGroup] = None
        self.settings_page_stack: Optional[QStackedWidget] = None
        self.close_behavior_hint_label: Optional[QLabel] = None
        self.close_to_tray_button: Optional[QPushButton] = None
        self.close_to_quit_button: Optional[QPushButton] = None
        self.force_quit_requested = False
        self.tray_available = False
        self.last_runtime_error = ""
        self.capture_in_progress = False
        self.single_capture_mode = False
        self.capture_target = CAPTURE_TARGET_FULLSCREEN
        self.region_customized = False
        self.region = self.default_region()
        self.custom_region: Optional[CaptureRegion] = None
        self.daily_times: list[str] = []

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)
        self.update_check_finished.connect(self.on_update_check_finished)
        self.hotkey_triggered.connect(self.on_hotkey_triggered)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self.on_application_state_changed)
        self.sync_mac_application_icon()

        self.build_ui()
        self.apply_styles()
        self.setup_tray_icon()
        has_saved_times = self.settings.contains("daily/times")
        self.load_settings()
        if not has_saved_times:
            self.add_time(self.current_time_text(), silent=True)
        self.refresh_idle_note()
        QTimer.singleShot(0, self.reflow_dynamic_layouts)
        if self.system_name == "Darwin":
            QTimer.singleShot(400, self.warm_screen_recording_permission)
            QTimer.singleShot(600, self.warm_browser_capture_permissions)
        QTimer.singleShot(1400, self.check_for_updates_on_startup)

    def default_region(self) -> CaptureRegion:
        screen = QApplication.primaryScreen()
        if screen is None:
            return CaptureRegion(0, 0, 1440, 900)

        geometry = screen.geometry()
        ratio = screen.devicePixelRatio()
        return CaptureRegion(
            x=round(geometry.x() * ratio),
            y=round(geometry.y() * ratio),
            width=round(geometry.width() * ratio),
            height=round(geometry.height() * ratio),
        )

    def build_ui(self):
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        logo_label = QLabel()
        logo_label.setObjectName("HeaderLogo")
        logo_label.setFixedSize(30, 30)
        logo_label.setPixmap(logo_pixmap(30))
        logo_label.setAlignment(Qt.AlignCenter)
        header.addWidget(logo_label, 0, Qt.AlignVCenter)

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("WindowTitle")
        title.setFixedHeight(34)
        title.setAlignment(Qt.AlignVCenter)
        header.addWidget(title, 0, Qt.AlignVCenter)
        header.addStretch(1)

        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon(settings_icon_pixmap(18)))
        self.settings_button.setIconSize(QSize(16, 16))
        self.settings_button.setObjectName("SettingsButton")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.setToolTip("设置")
        self.settings_button.clicked.connect(self.show_settings_dialog)
        header.addWidget(self.settings_button)
        root.addLayout(header)

        main = QHBoxLayout()
        main.setSpacing(18)
        root.addLayout(main, 1)

        settings = QFrame()
        settings.setObjectName("Panel")
        settings.setMinimumWidth(520)
        self.settings_panel = settings
        self.settings_panel_effect = QGraphicsOpacityEffect(settings)
        self.settings_panel_effect.setOpacity(1.0)
        self.settings_panel.setGraphicsEffect(self.settings_panel_effect)
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(20, 18, 20, 18)
        settings_layout.setSpacing(14)
        main.addWidget(settings, 5)

        settings_layout.addLayout(self.build_path_section())
        settings_layout.addLayout(self.build_mode_section(), 1)
        settings_layout.addLayout(self.build_region_section())

        side = QFrame()
        side.setObjectName("SidePanel")
        side.setMinimumWidth(270)
        side.setMaximumWidth(330)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(20, 18, 20, 18)
        side_layout.setSpacing(14)
        main.addWidget(side, 3)

        self.status_card = StatCard("当前状态", "未开始")
        self.count_card = CountSummaryCard("0", "0")
        side_layout.addWidget(self.status_card)
        side_layout.addWidget(self.count_card)

        self.note_label = QLabel()
        self.note_label.setObjectName("NoteLabel")
        self.note_label.setWordWrap(True)
        side_layout.addWidget(self.note_label)
        side_layout.addStretch(1)

        self.start_button = self.make_button("开始截图", "primary")
        self.capture_once_button = self.make_button("单次截图", "secondary")
        self.stop_button = self.make_button("停止截图", "danger")
        self.start_button.clicked.connect(self.start_capture)
        self.capture_once_button.clicked.connect(self.capture_once)
        self.stop_button.clicked.connect(self.stop_capture)
        self.stop_button.setEnabled(False)
        side_layout.addWidget(self.start_button)
        side_layout.addWidget(self.capture_once_button)
        side_layout.addWidget(self.stop_button)

    def build_path_section(self):
        layout = QGridLayout()
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        layout.addWidget(self.make_label("保存位置"), 0, 0)

        self.path_value = QLabel()
        self.path_value.setObjectName("ValueBox")
        self.path_value.setWordWrap(True)
        self.path_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.choose_dir_button = self.make_button("选择", "secondary")
        self.choose_dir_button.setFixedSize(64, 42)
        self.choose_dir_button.clicked.connect(self.choose_directory)

        self.open_dir_button = self.make_button("打开", "secondary")
        self.open_dir_button.setFixedSize(64, 42)
        self.open_dir_button.clicked.connect(self.open_save_directory)

        layout.addWidget(self.path_value, 1, 0)
        layout.addWidget(self.choose_dir_button, 1, 1)
        layout.addWidget(self.open_dir_button, 1, 2)
        layout.setColumnStretch(0, 1)
        return layout

    def build_mode_section(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.addWidget(self.make_label("截图方式"))

        segment = QFrame()
        segment.setObjectName("Segment")
        segment_layout = QHBoxLayout(segment)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(3)

        self.interval_button = QPushButton("间隔")
        self.minute_button = QPushButton("分钟点")
        self.daily_button = QPushButton("指定时间")
        for button in (self.interval_button, self.minute_button, self.daily_button):
            button.setCheckable(True)
            button.setObjectName("SegmentButton")
            segment_layout.addWidget(button)

        self.interval_button.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.interval_button, 0)
        self.mode_group.addButton(self.minute_button, 1)
        self.mode_group.addButton(self.daily_button, 2)
        self.interval_button.clicked.connect(lambda: self.set_mode(0))
        self.minute_button.clicked.connect(lambda: self.set_mode(1))
        self.daily_button.clicked.connect(lambda: self.set_mode(2))
        self.mode_group.idToggled.connect(
            lambda index, checked: self.set_mode(index) if checked else None
        )
        layout.addWidget(segment)

        self.mode_stack = QStackedWidget()
        self.mode_stack.setObjectName("ModeStack")
        self.mode_stack.setMinimumHeight(160)
        self.mode_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.mode_stack.addWidget(self.build_interval_page())
        self.mode_stack.addWidget(self.build_minute_page())
        self.mode_stack.addWidget(self.build_daily_page())
        layout.addWidget(self.mode_stack, 1)
        return layout

    def build_interval_page(self):
        page = QWidget()
        page.setObjectName("ModePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        control_group = QFrame()
        control_group.setObjectName("ControlGroup")
        control_layout = QHBoxLayout(control_group)
        control_layout.setContentsMargins(12, 12, 12, 12)
        control_layout.setSpacing(10)

        prefix = QLabel("每隔")
        prefix.setObjectName("FieldLabel")
        control_layout.addWidget(prefix)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(1, 999999)
        self.interval_spin.setDecimals(0)
        self.interval_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.interval_spin.setFixedSize(INTERVAL_CONTROL_WIDTH, RULE_BUTTON_HEIGHT)
        self.interval_spin.setValue(60)
        self.interval_spin.valueChanged.connect(self.on_interval_rule_changed)
        control_layout.addWidget(self.interval_spin)

        unit_segment = QFrame()
        unit_segment.setObjectName("MiniSegment")
        unit_layout = QHBoxLayout(unit_segment)
        unit_layout.setContentsMargins(3, 3, 3, 3)
        unit_layout.setSpacing(3)

        self.unit_group = QButtonGroup(self)
        self.unit_group.setExclusive(True)
        for index, (text, seconds) in enumerate((("秒", 1), ("分钟", 60), ("小时", 3600))):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("UnitButton")
            button.setProperty("seconds", seconds)
            button.setFixedSize(UNIT_BUTTON_WIDTH, 36)
            button.clicked.connect(self.on_interval_rule_changed)
            self.unit_group.addButton(button, index)
            unit_layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        self.unit_group.idToggled.connect(
            lambda _index, checked: self.on_interval_rule_changed() if checked else None
        )
        control_layout.addWidget(unit_segment)

        control_layout.addStretch(1)
        layout.addWidget(control_group)

        self.interval_preview = QLabel()
        self.interval_preview.setObjectName("InlineHint")
        self.interval_preview.setWordWrap(True)
        layout.addWidget(self.interval_preview)
        layout.addStretch(1)
        return page

    def build_minute_page(self):
        page = QWidget()
        page.setObjectName("ModePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(12)

        self.minute_group = QButtonGroup(self)
        self.minute_group.setExclusive(True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.minute_rules_layout = grid
        for index, minutes in enumerate((1, 3, 5, 10, 30, 60)):
            text = f"{minutes} 分钟" if minutes < 60 else "每小时"
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("RuleButton")
            button.setProperty("minutes", minutes)
            button.setFixedHeight(RULE_BUTTON_HEIGHT)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.minute_group.addButton(button, index)
            grid.addWidget(button, index // 3, index % 3)
            if minutes == 5:
                button.setChecked(True)
        for column in range(3):
            grid.setColumnStretch(column, 1)

        self.minute_group.idToggled.connect(
            lambda _index, checked: self.on_minute_rule_changed() if checked else None
        )
        layout.addLayout(grid)

        self.minute_preview = QLabel()
        self.minute_preview.setObjectName("InlineHint")
        self.minute_preview.setWordWrap(True)
        layout.addWidget(self.minute_preview)
        layout.addStretch(1)
        return page

    def build_daily_page(self):
        page = QWidget()
        page.setObjectName("ModePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self.add_time_button = self.make_button("添加时间点", "secondary")
        self.add_time_button.setFixedWidth(120)
        self.add_time_button.setFixedHeight(42)
        self.add_time_button.clicked.connect(lambda: self.add_time(self.daily_time.time().toString("HH:mm")))
        add_row.addWidget(self.build_daily_time_control())
        add_row.addWidget(self.add_time_button)
        add_row.addStretch(1)
        layout.addLayout(add_row)

        self.time_box = QFrame()
        self.time_box.setObjectName("TimeBox")
        self.time_box.setAttribute(Qt.WA_StyledBackground, True)
        self.time_box.setMinimumHeight(
            self.grid_height(TIME_CHIP_HEIGHT, TIME_GRID_SPACING, MIN_TIME_ROWS)
        )
        self.time_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        time_box_layout = QVBoxLayout(self.time_box)
        time_box_layout.setContentsMargins(0, 0, 0, 0)
        time_box_layout.setSpacing(0)

        self.time_scroll = TimePointScrollArea(
            preferred_height=self.grid_height(
                TIME_CHIP_HEIGHT,
                TIME_GRID_SPACING,
                DEFAULT_TIME_ROWS,
            ),
            minimum_height=self.grid_height(
                TIME_CHIP_HEIGHT,
                TIME_GRID_SPACING,
                MIN_TIME_ROWS,
            ),
        )
        self.time_scroll.setObjectName("TimeScroll")
        self.time_scroll.setWidgetResizable(False)
        self.time_scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.time_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.time_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.time_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.time_list = QWidget()
        self.time_list.setObjectName("TimeList")
        self.time_list_layout = QGridLayout(self.time_list)
        self.time_list_layout.setContentsMargins(0, 0, 0, 0)
        self.time_list_layout.setHorizontalSpacing(8)
        self.time_list_layout.setVerticalSpacing(8)
        self.time_scroll.setWidget(self.time_list)
        time_box_layout.addWidget(self.time_scroll)
        layout.addWidget(self.time_box, 1)
        return page

    def build_daily_time_control(self):
        control = QFrame()
        control.setObjectName("TimeInputControl")
        control.setFixedSize(136, 42)

        layout = QHBoxLayout(control)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(6)

        self.daily_time = QTimeEdit()
        self.daily_time.setObjectName("TimeInputEdit")
        self.daily_time.setDisplayFormat("HH:mm")
        self.daily_time.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.daily_time.setFixedHeight(40)
        self.daily_time.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.daily_time.setTime(datetime.now().replace(second=0, microsecond=0).time())
        self.daily_time.lineEdit().returnPressed.connect(
            lambda: self.add_time(self.daily_time.time().toString("HH:mm"))
        )

        self.daily_time_step_buttons = []
        stepper = QFrame()
        stepper.setObjectName("TimeInputStepper")
        stepper.setFixedSize(24, 34)
        stepper_layout = QVBoxLayout(stepper)
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(2)

        for text, tip, minutes in (
            ("▲", "增加 1 分钟", 1),
            ("▼", "减少 1 分钟", -1),
        ):
            button = QPushButton(text)
            button.setObjectName("TimeInputStepButton")
            button.setFixedSize(24, 16)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, value=minutes: self.step_daily_time(value))
            stepper_layout.addWidget(button)
            self.daily_time_step_buttons.append(button)

        layout.addWidget(self.daily_time, 1)
        layout.addWidget(stepper)
        return control

    def build_region_section(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        region_label = self.make_label("截图选项")
        region_label.setFixedHeight(SECTION_LABEL_HEIGHT)
        region_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(region_label)

        segment = QFrame()
        segment.setObjectName("Segment")
        segment_layout = QHBoxLayout(segment)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(3)

        self.fullscreen_region_button = QPushButton("全屏截图")
        self.custom_region_button = QPushButton("选取区域")
        self.browser_pages_button = QPushButton("浏览器页面")
        for button in (
            self.fullscreen_region_button,
            self.custom_region_button,
            self.browser_pages_button,
        ):
            button.setCheckable(True)
            button.setObjectName("SegmentButton")
            segment_layout.addWidget(button)

        self.fullscreen_region_button.setChecked(True)
        self.region_group = QButtonGroup(self)
        self.region_group.setExclusive(True)
        self.region_group.addButton(self.fullscreen_region_button, CAPTURE_TARGET_FULLSCREEN)
        self.region_group.addButton(self.custom_region_button, CAPTURE_TARGET_CUSTOM)
        self.region_group.addButton(self.browser_pages_button, CAPTURE_TARGET_BROWSER)
        self.fullscreen_region_button.clicked.connect(self.use_fullscreen_region)
        self.custom_region_button.clicked.connect(self.use_custom_region)
        self.browser_pages_button.clicked.connect(self.use_browser_pages)
        layout.addWidget(segment)

        region_value_row = QFrame()
        region_value_row.setObjectName("RegionValueRow")
        region_value_layout = QHBoxLayout(region_value_row)
        region_value_layout.setContentsMargins(0, 0, 0, 0)
        region_value_layout.setSpacing(8)

        self.region_value = QLabel()
        self.region_value.setObjectName("ValueBox")
        self.region_value.setFixedHeight(42)
        self.region_value.setWordWrap(False)
        self.region_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        region_value_layout.addWidget(self.region_value, 1)

        self.preview_region_button = QPushButton("预览")
        self.preview_region_button.setObjectName("RegionPreviewButton")
        self.preview_region_button.setFixedSize(82, 42)
        self.preview_region_button.clicked.connect(self.preview_region)
        region_value_layout.addWidget(self.preview_region_button)

        self.reselect_region_button = QPushButton("重新选取")
        self.reselect_region_button.setObjectName("RegionReselectButton")
        self.reselect_region_button.setFixedSize(112, 42)
        self.reselect_region_button.clicked.connect(self.select_region)
        region_value_layout.addWidget(self.reselect_region_button)
        layout.addWidget(region_value_row)
        return layout

    def apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f5f7;
            }
            QWidget#Root {
                background: #f5f5f7;
                color: #1d1d1f;
                font-family: "PingFang SC", "SF Pro Text", sans-serif;
                font-size: 14px;
            }
            QLabel {
                background: transparent;
            }
            QLabel#WindowTitle {
                font-family: "Songti SC", "STSong", "SimSun", serif;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#HeaderLogo {
                background: transparent;
                border: none;
            }
            QPushButton#SettingsButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: #6e6e73;
                font-size: 15px;
                font-weight: 700;
                max-height: 32px;
                max-width: 32px;
                min-height: 32px;
                min-width: 32px;
                padding: 0;
            }
            QPushButton#SettingsButton:hover {
                background: rgba(29, 29, 31, 0.06);
                color: #1d1d1f;
            }
            QPushButton#SettingsButton:pressed {
                background: rgba(29, 29, 31, 0.10);
            }
            QFrame#Panel,
            QFrame#SidePanel,
            QFrame#StatCard {
                background: white;
                border: 1px solid #e4e4e8;
                border-radius: 12px;
            }
            QLabel#SectionLabel {
                background: white;
                color: #36363a;
                font-size: 13px;
                font-weight: 700;
                min-height: 22px;
                padding: 1px 2px;
            }
            QLabel#ValueBox,
            QLabel#NoteLabel {
                background: #f8f8fa;
                border: 1px solid #e2e2e7;
                border-radius: 10px;
                color: #1d1d1f;
                padding: 10px 12px;
            }
            QLabel#NoteLabel {
                color: #4b4b51;
                line-height: 1.4;
            }
            QLabel#StatTitle {
                color: #6e6e73;
                font-size: 12px;
            }
            QLabel#StatValue {
                color: #1d1d1f;
                font-size: 24px;
                font-weight: 700;
            }
            QFrame#StatDivider {
                background: #e6e6eb;
                border: none;
                border-radius: 0;
                min-width: 1px;
                max-width: 1px;
            }
            QFrame#Segment {
                background: #ebebef;
                border-radius: 10px;
            }
            QPushButton#SegmentButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #4b4b51;
                font-weight: 700;
                padding: 9px 14px;
            }
            QPushButton#SegmentButton:checked {
                background: white;
                color: #1d1d1f;
            }
            QFrame#RegionValueRow {
                background: transparent;
                border: none;
            }
            QPushButton#RegionPreviewButton,
            QPushButton#RegionReselectButton {
                background: #f1f1f4;
                border: 1px solid #ddddE3;
                border-radius: 10px;
                color: #4b4b51;
                font-weight: 700;
                padding: 0 8px;
            }
            QPushButton#RegionPreviewButton:hover,
            QPushButton#RegionReselectButton:hover {
                background: #eaeaee;
            }
            QPushButton#RegionPreviewButton:disabled,
            QPushButton#RegionReselectButton:disabled {
                background: #e9e9ee;
                color: #b0b0b5;
            }
            QStackedWidget#ModeStack {
                background: white;
            }
            QWidget#ModePage {
                background: white;
            }
            QDoubleSpinBox,
            QTimeEdit {
                background: #f8f8fa;
                border: 1px solid #e2e2e7;
                border-radius: 10px;
                color: #1d1d1f;
                padding: 10px 12px;
                min-height: 22px;
            }
            QFrame#TimeInputControl {
                background: #f8f8fa;
                border: 1px solid #e2e2e7;
                border-radius: 10px;
            }
            QFrame#TimeInputControl:hover {
                border-color: #d2d2da;
                background: #fbfbfc;
            }
            QTimeEdit#TimeInputEdit {
                background: transparent;
                border: none;
                border-radius: 0;
                color: #1d1d1f;
                padding: 0;
                min-height: 40px;
            }
            QFrame#TimeInputStepper {
                background: transparent;
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                font-weight: 700;
                min-height: 38px;
                padding: 0 16px;
            }
            QPushButton[role="primary"] {
                background: #0A84FF;
                color: white;
            }
            QPushButton[role="primary"]:hover {
                background: #0070dd;
            }
            QPushButton[role="secondary"] {
                background: #f1f1f4;
                border: 1px solid #ddddE3;
                color: #1d1d1f;
            }
            QPushButton[role="secondary"]:hover {
                background: #eaeaee;
            }
            QPushButton[role="danger"] {
                background: #fff1f0;
                border: 1px solid #ffd2cf;
                color: #ff3b30;
            }
            QPushButton[role="danger"]:hover {
                background: #ffe7e5;
            }
            QPushButton:disabled {
                background: #f4f4f6;
                border: 1px solid #e8e8ec;
                color: #b0b0b5;
            }
            QPushButton#TimeInputStepButton {
                background: #e9e9ef;
                border: none;
                border-radius: 5px;
                color: #55555c;
                font-size: 9px;
                font-weight: 700;
                max-height: 16px;
                max-width: 24px;
                min-height: 16px;
                min-width: 24px;
                padding: 0;
            }
            QPushButton#TimeInputStepButton:hover {
                background: #dedee6;
                color: #1d1d1f;
            }
            QPushButton#TimeInputStepButton:pressed {
                background: #d1d1da;
            }
            QFrame#ControlGroup {
                background: #fbfbfc;
                border: 1px solid #e4e4e9;
                border-radius: 12px;
            }
            QFrame#MiniSegment {
                background: #ebebef;
                border-radius: 10px;
            }
            QLabel#FieldLabel {
                color: #4b4b51;
                font-weight: 700;
                padding: 0 2px;
            }
            QPushButton#UnitButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #4b4b51;
                min-width: 48px;
                min-height: 34px;
                padding: 0 10px;
            }
            QPushButton#UnitButton:checked {
                background: #1d1d1f;
                color: white;
            }
            QPushButton#RuleButton {
                background: #f1f1f4;
                border: 1px solid #ddddE3;
                border-radius: 10px;
                color: #4b4b51;
                min-width: 0;
                min-height: 40px;
                padding: 0 12px;
            }
            QPushButton#RuleButton:checked {
                background: #1d1d1f;
                border-color: #1d1d1f;
                color: white;
            }
            QLabel#InlineHint {
                background: #f8f8fa;
                border: 1px solid #e7e7ec;
                border-radius: 9px;
                color: #6e6e73;
                font-size: 12px;
                padding: 8px 10px;
            }
            QScrollArea#TimeScroll {
                background: transparent;
                border: none;
            }
            QFrame#TimeBox {
                background: white;
                border: none;
            }
            QScrollArea#TimeScroll > QWidget > QWidget {
                background: transparent;
            }
            QWidget#TimeList {
                background: transparent;
            }
            QFrame#TimeChip {
                background: #f1f1f4;
                border: 1px solid #dfdfe5;
                border-radius: 12px;
            }
            QLabel#TimeChipText {
                color: #1d1d1f;
                font-weight: 700;
            }
            QPushButton#ChipRemoveButton {
                background: #dedee5;
                border: none;
                border-radius: 12px;
                color: #63636a;
                font-weight: 700;
                min-height: 24px;
                min-width: 24px;
                padding: 0;
            }
            QPushButton#ChipRemoveButton:hover {
                background: #d2d2da;
            }
            QScrollArea#TimeScroll QScrollBar:vertical {
                background: transparent;
                border: none;
                width: 12px;
                margin: 2px 0 2px 6px;
            }
            QScrollArea#TimeScroll QScrollBar::handle:vertical {
                background: #c9c9d1;
                border-radius: 4px;
                min-height: 34px;
            }
            QScrollArea#TimeScroll QScrollBar::handle:vertical:hover {
                background: #acacb7;
            }
            QScrollArea#TimeScroll QScrollBar::add-line:vertical,
            QScrollArea#TimeScroll QScrollBar::sub-line:vertical {
                background: transparent;
                border: none;
                height: 0;
                width: 0;
            }
            QScrollArea#TimeScroll QScrollBar::add-page:vertical,
            QScrollArea#TimeScroll QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollArea#TimeScroll QScrollBar:horizontal {
                height: 0;
            }
            """
        )

    def make_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def make_button(self, text: str, role: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("role", role)
        button.style().unpolish(button)
        button.style().polish(button)
        return button

    def make_settings_table_header(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SettingsTableHeaderLabel")
        return label

    def show_settings_dialog(self):
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.show()
                self.settings_dialog.raise_()
                self.settings_dialog.activateWindow()
                return
            except RuntimeError:
                self.settings_dialog = None

        dialog = QDialog(self)
        dialog.setObjectName("SettingsDialog")
        dialog.setWindowTitle("设置")
        dialog.setModal(True)
        dialog.resize(760, 520)
        dialog.setMinimumSize(760, 520)
        if LOGO_PATH.exists():
            dialog.setWindowIcon(QIcon(app_icon_pixmap(256)))
        self.settings_dialog = dialog
        dialog.finished.connect(self.on_settings_dialog_closed)
        self.settings_dialog_open = True
        self.stop_hotkey_listener()

        root = QVBoxLayout(dialog)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        root.addLayout(content, 1)

        sidebar = QFrame()
        sidebar.setObjectName("SettingsSidebar")
        sidebar.setFixedWidth(168)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 18)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("设置")
        sidebar_title.setObjectName("SettingsSidebarTitle")
        sidebar_layout.addWidget(sidebar_title)

        self.settings_page_group = QButtonGroup(dialog)
        self.settings_page_group.setExclusive(True)
        page_buttons: list[QPushButton] = []
        for index, (title, page_key) in enumerate((("关闭选项", "general"), ("快捷键", "shortcut"), ("更新", "updates"), ("关于", "about"))):
            button = QPushButton(title)
            button.setObjectName("SettingsPageButton")
            button.setCheckable(True)
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setIcon(QIcon(settings_page_icon_pixmap(page_key, 16)))
            button.setIconSize(QSize(16, 16))
            self.settings_page_group.addButton(button, index)
            sidebar_layout.addWidget(button)
            page_buttons.append(button)
        sidebar_layout.addStretch(1)
        content.addWidget(sidebar)

        body = QFrame()
        body.setObjectName("SettingsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 18)
        body_layout.setSpacing(18)

        self.settings_page_stack = QStackedWidget()
        self.settings_page_stack.setObjectName("SettingsPageStack")
        body_layout.addWidget(self.settings_page_stack, 1)

        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(14)
        general_title = QLabel("关闭选项")
        general_title.setObjectName("SettingsPageTitle")
        general_layout.addWidget(general_title)

        general_card = QFrame()
        general_card.setObjectName("SettingsCard")
        general_card_layout = QVBoxLayout(general_card)
        general_card_layout.setContentsMargins(18, 18, 18, 18)
        general_card_layout.setSpacing(12)

        general_desc = QLabel("点右上角关闭时，定格截图是缩小到图标里继续运行，还是直接退出。")
        general_desc.setObjectName("SettingsHintText")
        general_desc.setWordWrap(True)
        general_card_layout.addWidget(general_desc)

        self.close_to_tray_button = QPushButton("缩小到图标")
        self.close_to_quit_button = QPushButton("直接退出")
        self.close_behavior_group = QButtonGroup(dialog)
        self.close_behavior_group.setExclusive(True)
        self.close_behavior_group.addButton(self.close_to_tray_button, 0)
        self.close_behavior_group.addButton(self.close_to_quit_button, 1)
        for button in (self.close_to_tray_button, self.close_to_quit_button):
            button.setCheckable(True)
            button.setObjectName("SettingsSegmentButton")
            button.setMinimumHeight(46)
        close_segment = QFrame()
        close_segment.setObjectName("SettingsSegment")
        close_segment_layout = QHBoxLayout(close_segment)
        close_segment_layout.setContentsMargins(3, 3, 3, 3)
        close_segment_layout.setSpacing(3)
        close_segment_layout.addWidget(self.close_to_tray_button)
        close_segment_layout.addWidget(self.close_to_quit_button)
        self.close_to_tray_button.clicked.connect(lambda: self.set_close_behavior(CLOSE_BEHAVIOR_TRAY))
        self.close_to_quit_button.clicked.connect(lambda: self.set_close_behavior(CLOSE_BEHAVIOR_QUIT))
        general_card_layout.addWidget(close_segment)

        self.close_behavior_hint_label = QLabel()
        self.close_behavior_hint_label.setObjectName("SettingsHintBox")
        self.close_behavior_hint_label.setWordWrap(True)
        general_card_layout.addWidget(self.close_behavior_hint_label)
        general_layout.addWidget(general_card)
        general_layout.addStretch(1)

        shortcut_page = QWidget()
        shortcut_layout = QVBoxLayout(shortcut_page)
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.setSpacing(14)
        shortcut_title = QLabel("快捷键")
        shortcut_title.setObjectName("SettingsPageTitle")
        shortcut_layout.addWidget(shortcut_title)

        shortcut_card = QFrame()
        shortcut_card.setObjectName("SettingsCard")
        shortcut_card_layout = QVBoxLayout(shortcut_card)
        shortcut_card_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_card_layout.setSpacing(0)

        shortcut_header = QWidget()
        shortcut_header_layout = QHBoxLayout(shortcut_header)
        shortcut_header_layout.setContentsMargins(18, 14, 18, 10)
        shortcut_header_layout.setSpacing(16)
        shortcut_header_layout.addWidget(self.make_settings_table_header("命令"), 1)
        shortcut_header_layout.addWidget(self.make_settings_table_header("按键绑定"), 0, Qt.AlignLeft)
        shortcut_card_layout.addWidget(shortcut_header)

        shortcut_divider = QFrame()
        shortcut_divider.setObjectName("SettingsBindingDivider")
        shortcut_card_layout.addWidget(shortcut_divider)

        shortcut_row = ShortcutBindingRow()
        shortcut_row.hovered_changed.connect(self.on_shortcut_binding_row_hovered)
        self.shortcut_binding_row = shortcut_row
        shortcut_row_layout = QHBoxLayout(shortcut_row)
        shortcut_row_layout.setContentsMargins(18, 14, 18, 14)
        shortcut_row_layout.setSpacing(18)

        command_column = QVBoxLayout()
        command_column.setContentsMargins(0, 0, 0, 0)
        command_column.setSpacing(4)
        shortcut_command_title = QLabel("单次截图")
        shortcut_command_title.setObjectName("SettingsBindingTitle")
        command_column.addWidget(shortcut_command_title)
        shortcut_command_desc = QLabel("按下后立即执行一轮单次截图")
        shortcut_command_desc.setObjectName("SettingsBindingSubtitle")
        command_column.addWidget(shortcut_command_desc)
        shortcut_row_layout.addLayout(command_column, 1)

        shortcut_binding_row = QHBoxLayout()
        shortcut_binding_row.setContentsMargins(0, 0, 0, 0)
        shortcut_binding_row.setSpacing(10)
        self.shortcut_preview_caps = ShortcutKeycapsWidget(self.capture_shortcut_sequence)
        self.shortcut_preview_caps.edit_requested.connect(self.begin_capture_shortcut_change)
        self.shortcut_preview_caps.sequence_captured.connect(self.on_shortcut_sequence_captured)
        shortcut_binding_row.addWidget(self.shortcut_preview_caps, 0, Qt.AlignLeft)

        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("SettingsTextButton")
        cancel_button.clicked.connect(self.cancel_shortcut_capture)
        cancel_button.hide()
        self.shortcut_cancel_button = cancel_button
        shortcut_binding_row.addWidget(cancel_button, 0, Qt.AlignVCenter)

        reset_shortcut_button = QPushButton("恢复默认")
        reset_shortcut_button.setObjectName("SettingsTextButton")
        reset_shortcut_button.clicked.connect(self.reset_shortcut_to_default)
        self.shortcut_reset_button = reset_shortcut_button
        shortcut_binding_row.addWidget(reset_shortcut_button, 0, Qt.AlignVCenter)
        shortcut_row_layout.addLayout(shortcut_binding_row, 0)
        shortcut_card_layout.addWidget(shortcut_row)

        status_container = QWidget()
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(18, 0, 18, 18)
        status_layout.setSpacing(0)

        self.shortcut_status_label = QLabel()
        self.shortcut_status_label.setObjectName("SettingsHintBox")
        self.shortcut_status_label.setWordWrap(True)
        status_layout.addWidget(self.shortcut_status_label)
        shortcut_card_layout.addWidget(status_container)
        shortcut_layout.addWidget(shortcut_card)
        shortcut_layout.addStretch(1)

        updates_page = QWidget()
        updates_layout = QVBoxLayout(updates_page)
        updates_layout.setContentsMargins(0, 0, 0, 0)
        updates_layout.setSpacing(14)
        updates_title = QLabel("更新")
        updates_title.setObjectName("SettingsPageTitle")
        updates_layout.addWidget(updates_title)

        updates_card = QFrame()
        updates_card.setObjectName("SettingsCard")
        updates_card_layout = QVBoxLayout(updates_card)
        updates_card_layout.setContentsMargins(18, 18, 18, 18)
        updates_card_layout.setSpacing(10)

        current_version_line = QLabel(f"当前版本：v{APP_VERSION}")
        current_version_line.setObjectName("SettingsVersionLine")
        updates_card_layout.addWidget(current_version_line)

        latest_version_line = QLabel(self.latest_version_text())
        latest_version_line.setObjectName("SettingsVersionLine")
        self.about_latest_version_label = latest_version_line
        updates_card_layout.addWidget(latest_version_line)

        auto_update_checkbox = QCheckBox("启动时自动检查更新")
        auto_update_checkbox.setObjectName("SettingsCheckBox")
        auto_update_checkbox.setChecked(self.auto_check_updates)
        auto_update_checkbox.toggled.connect(self.set_auto_check_updates)
        updates_card_layout.addWidget(auto_update_checkbox)

        updates_button_row = QHBoxLayout()
        updates_button_row.setContentsMargins(0, 4, 0, 0)
        updates_button_row.setSpacing(10)

        update_button = QPushButton("检查更新")
        update_button.setObjectName("SettingsActionButton")
        update_button.clicked.connect(lambda: self.check_for_updates(update_button))
        updates_button_row.addWidget(update_button)

        release_button = QPushButton("打开发布页")
        release_button.setObjectName("SettingsGhostButton")
        release_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.latest_release_url)))
        updates_button_row.addWidget(release_button)
        updates_button_row.addStretch(1)
        updates_card_layout.addLayout(updates_button_row)
        updates_layout.addWidget(updates_card)
        updates_layout.addStretch(1)

        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(0, 0, 0, 0)
        about_layout.setSpacing(14)
        about_title = QLabel("关于")
        about_title.setObjectName("SettingsPageTitle")
        about_layout.addWidget(about_title)

        about_card = QFrame()
        about_card.setObjectName("SettingsCard")
        about_card_layout = QVBoxLayout(about_card)
        about_card_layout.setContentsMargins(20, 20, 20, 20)
        about_card_layout.setSpacing(10)

        logo_label = QLabel()
        logo_label.setFixedSize(80, 80)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setPixmap(logo_pixmap(80))
        about_card_layout.addWidget(logo_label, 0, Qt.AlignHCenter)

        title_label = QLabel(APP_DISPLAY_NAME)
        title_label.setObjectName("SettingsAboutTitle")
        title_label.setAlignment(Qt.AlignCenter)
        about_card_layout.addWidget(title_label)

        author_label = QLabel(f"作者：{AUTHOR_NAME}")
        author_label.setObjectName("SettingsAboutAuthor")
        author_label.setAlignment(Qt.AlignCenter)
        about_card_layout.addWidget(author_label)

        for text in (
            "轻量的定时截图小工具，用来按规则自动保存屏幕画面。",
            "支持间隔、分钟点、指定时间，以及全屏、选区、浏览器页面截图。",
            f"单次运行最多保存 {MAX_CAPTURE_IMAGES_PER_RUN:,} 张截图，达到上限后会自动停止。",
        ):
            line = QLabel(text)
            line.setObjectName("SettingsHintText")
            line.setWordWrap(False)
            line.setAlignment(Qt.AlignCenter)
            about_card_layout.addWidget(line)

        github_button = QPushButton()
        github_button.setObjectName("SettingsGithubButton")
        github_button.setFixedHeight(42)
        github_button.setCursor(QCursor(Qt.PointingHandCursor))
        github_button.clicked.connect(self.open_github)
        github_button_layout = QHBoxLayout(github_button)
        github_button_layout.setContentsMargins(0, 0, 0, 0)
        github_button_layout.setSpacing(8)
        github_button_layout.setAlignment(Qt.AlignCenter)
        github_icon = QLabel()
        github_icon.setFixedSize(18, 18)
        github_icon.setPixmap(github_icon_pixmap(18))
        github_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        github_text = QLabel("GitHub 项目主页")
        github_text.setObjectName("SettingsGithubText")
        github_text.setAttribute(Qt.WA_TransparentForMouseEvents)
        github_button_layout.addWidget(github_icon)
        github_button_layout.addWidget(github_text)
        about_card_layout.addWidget(github_button)
        about_layout.addWidget(about_card)
        about_layout.addStretch(1)

        self.settings_page_stack.addWidget(general_page)
        self.settings_page_stack.addWidget(shortcut_page)
        self.settings_page_stack.addWidget(updates_page)
        self.settings_page_stack.addWidget(about_page)

        def switch_page(index: int):
            self.settings_page_stack.setCurrentIndex(index)
            for button in page_buttons:
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

        for index, button in enumerate(page_buttons):
            button.clicked.connect(lambda _checked=False, value=index: switch_page(value))
        page_buttons[0].setChecked(True)
        switch_page(0)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)
        close_button = QPushButton("完成")
        close_button.setObjectName("SettingsActionButton")
        close_button.setFixedSize(96, 38)
        close_button.clicked.connect(dialog.accept)
        footer.addWidget(close_button)
        body_layout.addLayout(footer)
        content.addWidget(body, 1)

        dialog.setStyleSheet(
            """
            QDialog#SettingsDialog {
                background: #f5f5f7;
                color: #1d1d1f;
                font-family: "PingFang SC", "SF Pro Text", sans-serif;
                font-size: 14px;
            }
            QFrame#SettingsSidebar {
                background: #f0f1f4;
                border-right: 1px solid #e1e2e7;
            }
            QLabel#SettingsSidebarTitle {
                color: #1d1d1f;
                font-size: 20px;
                font-weight: 700;
                padding: 2px 2px 12px 2px;
            }
            QFrame#SettingsBody {
                background: #f7f7fa;
            }
            QPushButton#SettingsPageButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: #4b4b51;
                font-size: 14px;
                font-weight: 700;
                min-height: 40px;
                text-align: left;
                padding: 0 14px;
            }
            QPushButton#SettingsPageButton:checked {
                background: white;
                color: #1d1d1f;
                border: 1px solid #e1e2e7;
            }
            QPushButton#SettingsPageButton:hover {
                background: rgba(255, 255, 255, 0.72);
            }
            QLabel#SettingsPageTitle {
                color: #1d1d1f;
                font-size: 22px;
                font-weight: 700;
                padding: 4px 2px 0 2px;
            }
            QFrame#SettingsCard {
                background: white;
                border: 1px solid #e4e4e8;
                border-radius: 14px;
            }
            QFrame#SettingsSegment {
                background: #ebebef;
                border-radius: 11px;
            }
            QPushButton#SettingsSegmentButton {
                background: transparent;
                border: none;
                border-radius: 9px;
                color: #4b4b51;
                font-weight: 700;
                min-height: 42px;
                padding: 0 14px;
            }
            QPushButton#SettingsSegmentButton:checked {
                background: white;
                color: #1d1d1f;
            }
            QLabel#SettingsHintText {
                color: #5c5c63;
                font-size: 13px;
            }
            QLabel#SettingsTableHeaderLabel {
                color: #8b8b92;
                font-size: 12px;
                font-weight: 700;
                padding: 0 2px;
            }
            QWidget#SettingsBindingRow {
                background: transparent;
            }
            QWidget#SettingsBindingRow:hover {
                background: #fbfbfd;
            }
            QFrame#SettingsBindingDivider {
                background: #ededf1;
                border: none;
                min-height: 1px;
                max-height: 1px;
            }
            QLabel#SettingsBindingTitle {
                color: #1d1d1f;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#SettingsBindingSubtitle {
                color: #6e6e73;
                font-size: 13px;
            }
            QLabel#SettingsMiniLabel {
                color: #6e6e73;
                font-size: 12px;
                font-weight: 700;
                padding-left: 2px;
            }
            QLabel#SettingsHintBox {
                background: #f8f8fa;
                border: 1px solid #e7e7ec;
                border-radius: 10px;
                color: #6e6e73;
                font-size: 13px;
                padding: 10px 12px;
            }
            QFrame#ShortcutKeycaps {
                background: #f3f3f6;
                border: none;
                border-radius: 10px;
            }
            QFrame#ShortcutKeycaps[state="recording"] {
                background: #eef5ff;
            }
            QLabel#ShortcutKeycapText {
                background: transparent;
                border: none;
                color: #1d1d1f;
                font-size: 14px;
                font-weight: 700;
                min-height: 34px;
                padding: 0;
            }
            QFrame#ShortcutKeycaps[state="empty"] QLabel#ShortcutKeycapText {
                color: #8a8a92;
                font-weight: 600;
            }
            QFrame#ShortcutKeycaps[state="recording"] QLabel#ShortcutKeycapText {
                color: #0A84FF;
                font-weight: 700;
            }
            QPushButton#SettingsTextButton {
                background: transparent;
                border: none;
                border-radius: 0;
                color: #6e6e73;
                font-size: 13px;
                font-weight: 600;
                min-height: 30px;
                padding: 0 4px;
            }
            QPushButton#SettingsTextButton:hover {
                color: #1d1d1f;
            }
            QLabel#SettingsVersionLine {
                color: #1d1d1f;
                font-size: 14px;
                font-weight: 650;
            }
            QCheckBox#SettingsCheckBox {
                color: #5c5c63;
                font-size: 13px;
                spacing: 8px;
                padding: 2px 0 4px 0;
            }
            QPushButton#SettingsActionButton {
                background: #0A84FF;
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: 700;
                min-height: 38px;
                padding: 0 18px;
            }
            QPushButton#SettingsActionButton:hover {
                background: #0070dd;
            }
            QPushButton#SettingsActionButton:pressed {
                background: #0068cc;
            }
            QPushButton#SettingsActionButton:disabled {
                background: #c8ddf6;
                color: rgba(255, 255, 255, 0.85);
            }
            QPushButton#SettingsGhostButton,
            QPushButton#SettingsGithubButton {
                background: #f7f7fa;
                border: 1px solid #e1e2e7;
                border-radius: 10px;
                color: #1d1d1f;
                font-weight: 700;
                min-height: 38px;
                padding: 0 18px;
            }
            QPushButton#SettingsGhostButton:hover,
            QPushButton#SettingsGithubButton:hover {
                background: #efeff4;
            }
            QLabel#SettingsAboutTitle {
                color: #1d1d1f;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#SettingsAboutAuthor,
            QLabel#SettingsGithubText {
                color: #6e6e73;
                font-size: 13px;
                font-weight: 600;
            }
            """
        )

        self.refresh_close_behavior_ui()
        self.refresh_shortcut_ui()
        self.refresh_latest_version_label()
        dialog.exec()

    def on_settings_dialog_closed(self, _result=None):
        self.settings_dialog_open = False
        if self.shortcut_preview_caps is not None:
            try:
                if self.shortcut_preview_caps.recording:
                    self.shortcut_preview_caps.cancel_recording(self.capture_shortcut_sequence)
            except RuntimeError:
                pass
        self.settings_dialog = None
        self.about_latest_version_label = None
        self.close_behavior_hint_label = None
        self.close_to_tray_button = None
        self.close_to_quit_button = None
        self.shortcut_binding_row = None
        self.shortcut_preview_caps = None
        self.shortcut_reset_button = None
        self.shortcut_cancel_button = None
        self.shortcut_status_label = None
        self.settings_page_group = None
        self.settings_page_stack = None
        QTimer.singleShot(700, self.restart_hotkey_listener)

    def open_github(self):
        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def latest_version_text(self) -> str:
        if self.latest_release_tag:
            return f"最新版本：{self.latest_release_tag}"
        return "最新版本：尚未检查"

    def refresh_latest_version_label(self):
        if self.about_latest_version_label is None:
            return
        try:
            self.about_latest_version_label.setText(self.latest_version_text())
        except RuntimeError:
            self.about_latest_version_label = None

    def close_behavior_text(self) -> str:
        if self.close_behavior == CLOSE_BEHAVIOR_TRAY:
            target = "菜单栏图标" if self.system_name == "Darwin" else "托盘图标"
            return f"点击右上角关闭后会缩小到{target}，需要从图标里真正退出。"
        if self.close_behavior == CLOSE_BEHAVIOR_QUIT:
            return "点击右上角关闭后会直接退出软件。"
        return "首次点击右上角关闭会先询问一次，之后会按你的选择作为默认方式。"

    def refresh_close_behavior_ui(self):
        if self.close_behavior_hint_label is not None:
            try:
                self.close_behavior_hint_label.setText(self.close_behavior_text())
            except RuntimeError:
                self.close_behavior_hint_label = None

        if self.close_to_tray_button is None or self.close_to_quit_button is None:
            return

        try:
            self.close_behavior_group.setExclusive(False)
            self.close_to_tray_button.setChecked(self.close_behavior == CLOSE_BEHAVIOR_TRAY)
            self.close_to_quit_button.setChecked(self.close_behavior == CLOSE_BEHAVIOR_QUIT)
            self.close_to_tray_button.setEnabled(self.tray_available)
            self.close_behavior_group.setExclusive(True)
        except RuntimeError:
            self.close_to_tray_button = None
            self.close_to_quit_button = None

    def shortcut_status_text(self) -> str:
        if self.shortcut_preview_caps is not None:
            try:
                if self.shortcut_preview_caps.recording:
                    return "直接按下新的快捷键；如果不继续设置，快捷键就会保持关闭。"
            except RuntimeError:
                self.shortcut_preview_caps = None
        if not self.capture_shortcut_sequence:
            return "当前已关闭快捷键"
        if self.system_name == "Darwin":
            if self.hotkey_listener_error:
                return f"Mac 全局快捷键没有成功启用：{self.hotkey_listener_error}。当前仅前台可用。"
            return "按下后会立即执行一轮单次截图。如果没有反应，请到“系统设置 > 隐私与安全性 > 辅助功能”里允许。"
        if pynput_keyboard is None:
            return "当前环境缺少 pynput，暂时无法启用全局快捷键。"
        if self.hotkey_listener_error:
            return f"快捷键没有成功启用：{self.hotkey_listener_error}"
        return "按下后会立即执行一轮单次截图。"

    def refresh_shortcut_ui(self):
        if self.shortcut_preview_caps is not None:
            try:
                if not self.shortcut_preview_caps.recording:
                    self.shortcut_preview_caps.set_sequence(self.capture_shortcut_sequence)
            except RuntimeError:
                self.shortcut_preview_caps = None

        recording = self.shortcut_preview_caps is not None and self.shortcut_preview_caps.recording

        if self.shortcut_reset_button is not None:
            try:
                self.shortcut_reset_button.setVisible(not recording)
            except RuntimeError:
                self.shortcut_reset_button = None

        if self.shortcut_cancel_button is not None:
            try:
                self.shortcut_cancel_button.setVisible(recording)
            except RuntimeError:
                self.shortcut_cancel_button = None

        if self.shortcut_status_label is not None:
            try:
                self.shortcut_status_label.setText(self.shortcut_status_text())
            except RuntimeError:
                self.shortcut_status_label = None

    def on_shortcut_binding_row_hovered(self, _hovered: bool):
        return

    def stop_hotkey_listener(self):
        self.unregister_mac_hotkey()
        listener = self.hotkey_listener
        self.hotkey_listener = None
        if listener is None:
            return
        try:
            listener.stop()
        except Exception:
            pass

    def setup_mac_hotkey_handler(self):
        if self.mac_hotkey_handler_ref is not None:
            return
        if not MAC_CARBON_AVAILABLE or MAC_CARBON is None:
            raise RuntimeError("当前环境无法使用 macOS 原生快捷键。")

        def handler(_next_handler, _event, _user_data):
            try:
                QTimer.singleShot(0, self.emit_hotkey_trigger)
            except Exception:
                pass
            return 0

        self.mac_hotkey_callback = MacEventHandlerProc(handler)
        event_type = MacEventTypeSpec(
            MAC_HOTKEY_EVENT_CLASS,
            MAC_HOTKEY_EVENT_KIND_PRESSED,
        )
        handler_ref = ctypes.c_void_p()
        target = MAC_CARBON.GetEventDispatcherTarget()
        result = MAC_CARBON.InstallEventHandler(
            target,
            self.mac_hotkey_callback,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(handler_ref),
        )
        if result != 0:
            self.mac_hotkey_callback = None
            raise RuntimeError(f"注册 Mac 快捷键处理器失败：{result}")
        self.mac_hotkey_handler_ref = handler_ref

    def register_mac_hotkey(self, sequence: str):
        self.unregister_mac_hotkey()
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.refresh_shortcut_ui()
            return
        self.setup_mac_hotkey_handler()
        keycode, modifiers = shortcut_to_mac_carbon(sequence)
        hotkey_id = MacEventHotKeyID(MAC_HOTKEY_SIGNATURE, MAC_HOTKEY_ID_CAPTURE_ONCE)
        hotkey_ref = ctypes.c_void_p()
        target = MAC_CARBON.GetEventDispatcherTarget()
        result = MAC_CARBON.RegisterEventHotKey(
            keycode,
            modifiers,
            hotkey_id,
            target,
            0,
            ctypes.byref(hotkey_ref),
        )
        if result != 0:
            raise RuntimeError(f"注册 Mac 全局快捷键失败：{result}")
        self.mac_hotkey_ref = hotkey_ref
        self.capture_once_shortcut_action.setEnabled(False)

    def unregister_mac_hotkey(self):
        if self.mac_hotkey_ref is None or MAC_CARBON is None:
            self.mac_hotkey_ref = None
            return
        try:
            MAC_CARBON.UnregisterEventHotKey(self.mac_hotkey_ref)
        except Exception:
            pass
        self.mac_hotkey_ref = None

    def teardown_mac_hotkey_handler(self):
        self.unregister_mac_hotkey()
        if self.mac_hotkey_handler_ref is not None and MAC_CARBON is not None:
            try:
                MAC_CARBON.RemoveEventHandler(self.mac_hotkey_handler_ref)
            except Exception:
                pass
        self.mac_hotkey_handler_ref = None
        self.mac_hotkey_callback = None

    def restart_hotkey_listener(self):
        self.stop_hotkey_listener()
        self.hotkey_listener_error = ""
        self.refresh_app_shortcut()

        if self.settings_dialog_open:
            self.refresh_shortcut_ui()
            return

        if not self.capture_shortcut_sequence:
            self.refresh_shortcut_ui()
            return
        if self.system_name == "Darwin":
            try:
                self.register_mac_hotkey(self.capture_shortcut_sequence)
            except Exception as exc:  # noqa: BLE001
                self.hotkey_listener_error = str(exc)
            self.refresh_shortcut_ui()
            return
        if pynput_keyboard is None:
            self.hotkey_listener_error = "缺少快捷键依赖 pynput。"
            self.refresh_shortcut_ui()
            return

        try:
            hotkey_spec = shortcut_to_pynput(self.capture_shortcut_sequence)
            listener = pynput_keyboard.GlobalHotKeys({hotkey_spec: self.emit_hotkey_trigger})
            listener.start()
            self.hotkey_listener = listener
        except Exception as exc:  # noqa: BLE001
            self.hotkey_listener_error = str(exc)
            self.hotkey_listener = None

        self.refresh_shortcut_ui()

    def refresh_app_shortcut(self):
        sequence = normalize_shortcut_sequence(self.capture_shortcut_sequence)
        shortcut = QKeySequence.fromString(sequence, QKeySequence.PortableText) if sequence else QKeySequence()
        self.capture_once_shortcut_action.setShortcut(shortcut)
        self.capture_once_shortcut_action.setEnabled(bool(sequence))

    def update_capture_shortcut(self, sequence: str, persist: bool = True):
        normalized = normalize_shortcut_sequence(sequence)
        if normalized:
            if self.system_name == "Darwin":
                shortcut_to_mac_carbon(normalized)
            else:
                shortcut_to_pynput(normalized)
        self.capture_shortcut_sequence = normalized
        if persist:
            self.settings.setValue("hotkey/capture_once", normalized)
            self.settings.sync()
        self.restart_hotkey_listener()

    def begin_capture_shortcut_change(self):
        self.update_capture_shortcut("")
        if self.shortcut_preview_caps is not None:
            try:
                self.shortcut_preview_caps.start_recording()
            except RuntimeError:
                self.shortcut_preview_caps = None
        self.refresh_shortcut_ui()

    def cancel_shortcut_capture(self):
        if self.shortcut_preview_caps is not None:
            try:
                self.shortcut_preview_caps.cancel_recording("")
            except RuntimeError:
                self.shortcut_preview_caps = None
        self.refresh_shortcut_ui()

    def on_shortcut_sequence_captured(self, sequence: str):
        try:
            self.update_capture_shortcut(sequence)
        except ValueError as exc:
            QMessageBox.warning(self, "快捷键不可用", str(exc))
            self.refresh_shortcut_ui()

    def reset_shortcut_to_default(self):
        try:
            self.update_capture_shortcut(DEFAULT_CAPTURE_SHORTCUT)
        except ValueError as exc:
            QMessageBox.warning(self, "快捷键不可用", str(exc))
            return
        self.refresh_shortcut_ui()

    def emit_hotkey_trigger(self):
        self.hotkey_triggered.emit()

    def on_hotkey_triggered(self):
        if self.force_quit_requested or self.capture_in_progress or self.settings_dialog_open:
            return
        self.capture_once()

    def set_close_behavior(self, behavior: str, persist: bool = True):
        if behavior not in {CLOSE_BEHAVIOR_ASK, CLOSE_BEHAVIOR_TRAY, CLOSE_BEHAVIOR_QUIT}:
            return
        self.close_behavior = behavior
        if persist:
            self.settings.setValue("window/close_behavior", "" if behavior == CLOSE_BEHAVIOR_ASK else behavior)
            self.settings.sync()
        self.refresh_close_behavior_ui()

    def ask_close_behavior(self) -> Optional[str]:
        dialog = QDialog(self)
        dialog.setObjectName("CloseBehaviorDialog")
        dialog.setWindowTitle("关闭主窗口")
        dialog.setModal(True)
        dialog.setFixedSize(520, 330)

        selected_behavior = {"value": None}
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        title = QLabel("点击关闭后，希望定格截图怎么处理？")
        title.setObjectName("CloseDialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel("这次的选择会记住为默认方式，之后也可以在设置里修改。")
        subtitle.setObjectName("CloseDialogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        options = QHBoxLayout()
        options.setContentsMargins(0, 6, 0, 0)
        options.setSpacing(12)

        def choose_behavior(behavior: str):
            selected_behavior["value"] = behavior
            self.set_close_behavior(behavior)
            dialog.accept()

        def create_option_button(title_text: str, body_text: str, mode: str, enabled: bool = True) -> QPushButton:
            button = QPushButton(f"{title_text}\n{body_text}")
            button.setObjectName("CloseChoiceButton")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setEnabled(enabled)
            button.setMinimumHeight(164)
            button.setIcon(QIcon(close_mode_icon_pixmap(mode, 24)))
            button.setIconSize(QSize(24, 24))
            return button

        tray_label = "缩小到菜单栏" if self.system_name == "Darwin" else "缩小到托盘"
        tray_button = create_option_button(
            tray_label,
            "主窗口先收起，软件继续运行",
            "tray",
            enabled=self.tray_available,
        )
        tray_button.clicked.connect(lambda: choose_behavior(CLOSE_BEHAVIOR_TRAY))
        options.addWidget(tray_button, 1)

        quit_button = create_option_button(
            "直接退出",
            "关闭后软件会完全退出",
            "quit",
        )
        quit_button.clicked.connect(lambda: choose_behavior(CLOSE_BEHAVIOR_QUIT))
        options.addWidget(quit_button, 1)
        layout.addLayout(options)

        hint = QLabel("以后也可以在设置 > 通用 里重新改这个默认行为。")
        hint.setObjectName("CloseDialogHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("CloseCancelButton")
        cancel_button.setFixedSize(88, 36)
        cancel_button.clicked.connect(dialog.reject)
        footer.addWidget(cancel_button)
        layout.addLayout(footer)

        dialog.setStyleSheet(
            """
            QDialog#CloseBehaviorDialog {
                background: #f5f5f7;
                color: #1d1d1f;
                font-family: "PingFang SC", "SF Pro Text", sans-serif;
            }
            QLabel#CloseDialogTitle {
                color: #1d1d1f;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#CloseDialogSubtitle,
            QLabel#CloseDialogHint {
                color: #6e6e73;
                font-size: 13px;
            }
            QPushButton#CloseChoiceButton {
                background: white;
                border: 1px solid #e2e2e7;
                border-radius: 18px;
                color: #1d1d1f;
                font-size: 14px;
                font-weight: 650;
                padding: 18px 18px;
                text-align: left;
            }
            QPushButton#CloseChoiceButton:hover {
                background: #fbfbfc;
                border-color: #c9ccd4;
            }
            QPushButton#CloseChoiceButton:pressed {
                background: #efeff4;
            }
            QPushButton#CloseChoiceButton:disabled {
                background: #f1f1f4;
                color: #9e9ea5;
                border-color: #e3e4e8;
            }
            QPushButton#CloseCancelButton {
                background: #efeff4;
                border: 1px solid #dedee4;
                border-radius: 10px;
                color: #4b4b51;
                font-weight: 700;
            }
            QPushButton#CloseCancelButton:hover {
                background: #e7e7ed;
            }
            """
        )
        dialog.exec()
        return selected_behavior["value"]

    def setup_tray_icon(self):
        if self.system_name == "Darwin" and PYOBJC_AVAILABLE:
            self.tray_available = True
            self.setup_native_status_item()
            self.update_tray_ui()
            return

        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.tray_available:
            self.set_close_behavior(CLOSE_BEHAVIOR_QUIT, persist=False)
            if self.close_to_tray_button is not None:
                self.close_to_tray_button.setEnabled(False)
            return

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(tray_status_icon(TRAY_STATE_IDLE))
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

        menu = self.build_tray_menu()
        if self.system_name != "Darwin":
            self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        self.update_tray_ui()

    def build_tray_menu(self):
        menu = QMenu(self)
        self.tray_menu = menu

        self.tray_show_action = QAction("显示主界面", self)
        self.tray_show_action.triggered.connect(self.toggle_main_window_visibility)
        menu.addAction(self.tray_show_action)

        self.tray_start_action = QAction("开始截图", self)
        self.tray_start_action.triggered.connect(self.start_capture)
        menu.addAction(self.tray_start_action)

        self.tray_capture_once_action = QAction("单次截图", self)
        self.tray_capture_once_action.triggered.connect(self.capture_once)
        menu.addAction(self.tray_capture_once_action)

        self.tray_stop_action = QAction("停止截图", self)
        self.tray_stop_action.triggered.connect(self.stop_capture)
        menu.addAction(self.tray_stop_action)

        menu.addSeparator()
        exit_action = QAction("退出软件", self)
        exit_action.triggered.connect(self.request_quit)
        menu.addAction(exit_action)
        return menu

    def setup_native_status_item(self):
        if not PYOBJC_AVAILABLE:
            return

        self.native_status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            MAC_STATUS_ITEM_LENGTH
        )
        self.native_status_button = self.native_status_item.button()
        self.native_status_target = MacStatusItemTarget.alloc().initWithWindow_(self)
        self.build_native_status_menu()
        self.native_status_button.setTitle_("")
        self.native_status_button.setBordered_(False)
        self.native_status_button.setImagePosition_(NSImageOnly)
        self.native_status_button.setImageScaling_(NSImageScaleProportionallyDown)
        self.native_status_button.setTarget_(self.native_status_target)
        self.native_status_button.setAction_("handleStatusItemClick:")
        self.native_status_button.sendActionOn_(
            NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp
        )

    def build_native_status_menu(self):
        if not PYOBJC_AVAILABLE or self.native_status_target is None:
            return

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        self.native_menu_show_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "显示主界面",
            "toggleMainWindow:",
            "",
        )
        self.native_menu_show_item.setTarget_(self.native_status_target)
        menu.addItem_(self.native_menu_show_item)

        self.native_menu_start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "开始截图",
            "startCapture:",
            "",
        )
        self.native_menu_start_item.setTarget_(self.native_status_target)
        menu.addItem_(self.native_menu_start_item)

        self.native_menu_capture_once_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "单次截图",
            "captureOnce:",
            "",
        )
        self.native_menu_capture_once_item.setTarget_(self.native_status_target)
        menu.addItem_(self.native_menu_capture_once_item)

        self.native_menu_stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "停止截图",
            "stopCapture:",
            "",
        )
        self.native_menu_stop_item.setTarget_(self.native_status_target)
        menu.addItem_(self.native_menu_stop_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self.native_menu_quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出软件",
            "requestQuit:",
            "",
        )
        self.native_menu_quit_item.setTarget_(self.native_status_target)
        menu.addItem_(self.native_menu_quit_item)

        self.native_status_menu = menu

    def tray_state(self) -> str:
        if self.last_runtime_error:
            return TRAY_STATE_ERROR
        if self.running or self.capture_in_progress:
            return TRAY_STATE_ACTIVE
        return TRAY_STATE_IDLE

    def tray_tooltip_text(self) -> str:
        if self.last_runtime_error:
            return f"{APP_DISPLAY_NAME}：运行失败"
        if self.capture_in_progress and not self.running:
            return f"{APP_DISPLAY_NAME}：正在停止当前截图"
        if self.running:
            if self.single_capture_mode:
                return f"{APP_DISPLAY_NAME}：单次截图进行中"
            return f"{APP_DISPLAY_NAME}：截图任务运行中"
        return f"{APP_DISPLAY_NAME}：待机中"

    def update_tray_ui(self):
        if self.tray_icon is not None:
            self.tray_icon.setIcon(tray_status_icon(self.tray_state()))
            self.tray_icon.setToolTip(self.tray_tooltip_text())

        self.update_native_status_item()

        if self.tray_show_action is not None:
            self.tray_show_action.setText("显示主界面" if self.isHidden() else "隐藏主界面")
        if self.tray_start_action is not None:
            self.tray_start_action.setEnabled(not (self.running or self.capture_in_progress))
        if self.tray_capture_once_action is not None:
            self.tray_capture_once_action.setEnabled(not self.capture_in_progress and not self.single_capture_mode)
        if self.tray_stop_action is not None:
            self.tray_stop_action.setEnabled(self.running)

    def update_native_status_item(self):
        if self.native_status_button is None:
            return

        icon = tray_status_icon(self.tray_state(), MAC_STATUS_ICON_SIZE)
        pixmap = icon.pixmap(MAC_STATUS_ICON_SIZE, MAC_STATUS_ICON_SIZE)
        image = nsimage_from_pixmap(pixmap)
        if image is None:
            return

        image.setTemplate_(self.tray_state() == TRAY_STATE_IDLE)
        self.native_status_button.setImage_(image)
        self.native_status_button.setToolTip_(self.tray_tooltip_text())
        self.update_native_status_menu()

    def update_native_status_menu(self):
        if self.native_status_menu is None:
            return

        if self.native_menu_show_item is not None:
            self.native_menu_show_item.setTitle_("显示主界面" if self.isHidden() else "隐藏主界面")
            self.native_menu_show_item.setEnabled_(True)
        if self.native_menu_start_item is not None:
            self.native_menu_start_item.setEnabled_(not (self.running or self.capture_in_progress))
        if self.native_menu_capture_once_item is not None:
            self.native_menu_capture_once_item.setEnabled_(not self.capture_in_progress and not self.single_capture_mode)
        if self.native_menu_stop_item is not None:
            self.native_menu_stop_item.setEnabled_(self.running)
        if self.native_menu_quit_item is not None:
            self.native_menu_quit_item.setEnabled_(True)

    def on_tray_icon_activated(self, reason):
        if self.native_status_item is not None:
            return

        if self.system_name == "Darwin":
            if reason == QSystemTrayIcon.Context and self.tray_menu is not None:
                if time.monotonic() - self.last_tray_primary_click_at < 0.28:
                    return
                self.tray_context_menu_timer.start(0)
                return
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
                self.last_tray_primary_click_at = time.monotonic()
                self.tray_context_menu_timer.stop()
                self.show_main_window()
                return

        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_main_window_visibility()

    def show_tray_context_menu(self):
        if self.native_status_item is not None:
            self.update_tray_ui()
            if self.native_status_menu is not None:
                self.native_status_item.popUpStatusItemMenu_(self.native_status_menu)
            return
        if self.tray_menu is None:
            return
        if self.system_name != "Darwin":
            return
        if time.monotonic() - self.last_tray_primary_click_at < 0.28:
            return
        self.tray_menu.popup(QCursor.pos())

    def eventFilter(self, obj, event):
        if (
            self.system_name == "Darwin"
            and self.tray_available
            and event is not None
            and event.type() == QEvent.ApplicationActivate
        ):
            self.restore_window_from_app_activation()
        return super().eventFilter(obj, event)

    def on_application_state_changed(self, state):
        if self.system_name != "Darwin" or not self.tray_available:
            return
        if state != Qt.ApplicationActive:
            return
        self.restore_window_from_app_activation()

    def restore_window_from_app_activation(self):
        if self.force_quit_requested:
            return
        if self.overlay is not None or self.preview_overlay is not None:
            return
        if self.isHidden():
            QTimer.singleShot(0, self.show_main_window)

    def set_mac_activation_policy(self, show_in_dock: bool):
        if self.system_name != "Darwin" or not PYOBJC_AVAILABLE:
            return
        try:
            NSApp.setActivationPolicy_(
                NSApplicationActivationPolicyRegular
                if show_in_dock
                else NSApplicationActivationPolicyAccessory
            )
            self.sync_mac_application_icon()
        except Exception:
            return

    def sync_mac_application_icon(self):
        if self.system_name != "Darwin" or not PYOBJC_AVAILABLE:
            return
        try:
            image = mac_application_icon_image()
            if image is not None:
                NSApp.setApplicationIconImage_(image)
        except Exception:
            return

    def show_main_window(self):
        self.set_mac_activation_policy(True)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.system_name == "Darwin" and PYOBJC_AVAILABLE:
            NSApp.activateIgnoringOtherApps_(True)
        self.update_tray_ui()

    def hide_to_tray(self):
        self.hide()
        self.set_mac_activation_policy(False)
        self.update_tray_ui()

    def toggle_main_window_visibility(self):
        if self.isHidden():
            self.show_main_window()
        else:
            self.hide_to_tray()

    def teardown_tray_icon(self):
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if self.native_status_item is not None and PYOBJC_AVAILABLE:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.native_status_item)
            self.native_status_item = None
            self.native_status_button = None
            self.native_status_target = None
            self.native_status_menu = None
            self.native_menu_show_item = None
            self.native_menu_start_item = None
            self.native_menu_capture_once_item = None
            self.native_menu_stop_item = None
            self.native_menu_quit_item = None

    def request_quit(self):
        self.force_quit_requested = True
        self.save_settings()
        self.stop_hotkey_listener()
        self.teardown_tray_icon()
        self.close()
        QTimer.singleShot(0, QApplication.instance().quit)

    def set_auto_check_updates(self, checked: bool):
        self.auto_check_updates = checked
        self.settings.setValue("updates/auto_check", checked)
        self.settings.sync()

    def check_for_updates_on_startup(self):
        if self.auto_check_updates:
            self.check_for_updates(silent=True)

    def check_for_updates(self, button: Optional[QPushButton] = None, silent: bool = False):
        if self.update_check_running:
            return

        self.update_check_running = True
        self.update_check_button = button
        self.update_check_silent = silent
        if button is not None:
            button.setEnabled(False)
            button.setText("检查中...")

        thread = threading.Thread(target=self.fetch_latest_release_worker, daemon=True)
        thread.start()

    def fetch_latest_release_worker(self):
        try:
            request = Request(
                GITHUB_LATEST_RELEASE_URL,
                headers={
                    "User-Agent": f"Dingge-Screenshot/{APP_VERSION}",
                },
            )
            with urlopen(request, timeout=8) as response:
                latest_url = response.geturl()
                response.read(1)
            marker = "/releases/tag/"
            if marker not in latest_url:
                raise RuntimeError("没有读取到最新版本地址。")
            latest_tag = unquote(latest_url.rsplit(marker, 1)[1].split("?", 1)[0].split("#", 1)[0])
            self.update_check_finished.emit(
                {
                    "ok": True,
                    "tag_name": latest_tag,
                    "html_url": latest_url,
                }
            )
        except HTTPError as exc:
            if exc.code == 404:
                message = "还没有检测到已发布的版本。"
            else:
                message = f"GitHub 返回错误：HTTP {exc.code}"
            self.update_check_finished.emit({"ok": False, "message": message})
        except URLError as exc:
            self.update_check_finished.emit({"ok": False, "message": f"网络连接失败：{exc.reason}"})
        except TimeoutError:
            self.update_check_finished.emit({"ok": False, "message": "连接超时，请稍后再试。"})
        except Exception as exc:  # noqa: BLE001
            self.update_check_finished.emit({"ok": False, "message": f"检查更新失败：{exc}"})

    def on_update_check_finished(self, result: dict):
        self.update_check_running = False
        silent = self.update_check_silent
        self.update_check_silent = False
        button = self.update_check_button
        self.update_check_button = None
        if button is not None:
            try:
                button.setEnabled(True)
                button.setText("检查更新")
            except RuntimeError:
                pass

        if not result.get("ok"):
            if silent:
                return
            QMessageBox.warning(
                self,
                "检查更新失败",
                f"{result.get('message', '暂时无法检查更新。')}\n\n你也可以手动打开 GitHub 发布页查看最新版本。",
            )
            return

        latest_tag = result.get("tag_name") or ""
        latest_url = result.get("html_url") or GITHUB_RELEASES_URL
        if not latest_tag:
            if silent:
                return
            QMessageBox.information(self, "暂无更新", "没有读取到最新版本号。")
            return

        self.latest_release_tag = latest_tag
        self.latest_release_url = latest_url
        self.refresh_latest_version_label()

        if compare_versions(APP_VERSION, latest_tag) >= 0:
            if silent:
                return
            QMessageBox.information(
                self,
                "已是最新版本",
                f"当前版本：v{APP_VERSION}\n最新版本：{latest_tag}",
            )
            return

        message = QMessageBox(self)
        message.setIcon(QMessageBox.Information)
        message.setWindowTitle("发现新版本")
        message.setText(f"发现新版本：{latest_tag}")
        message.setInformativeText(f"当前版本：v{APP_VERSION}\n是否打开下载页面？")
        open_button = message.addButton("打开下载页面", QMessageBox.AcceptRole)
        message.addButton("稍后再说", QMessageBox.RejectRole)
        message.exec()
        if message.clickedButton() == open_button:
            QDesktopServices.openUrl(QUrl(latest_url))

    def current_time_text(self) -> str:
        return datetime.now().replace(second=0, microsecond=0).strftime("%H:%M")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "time_list_layout"):
            self.reflow_dynamic_layouts()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.update_tray_ui)

    def hideEvent(self, event):
        super().hideEvent(event)
        QTimer.singleShot(0, self.update_tray_ui)

    def reflow_dynamic_layouts(self):
        if hasattr(self, "time_list_layout"):
            self.render_time_chips(force=False)

    def arrange_responsive_grid(self, layout: QGridLayout, widgets: list[QWidget], item_width: int, spacing: int):
        if not widgets:
            return

        parent = layout.parentWidget()
        available_width = parent.width() if parent is not None else self.mode_stack.width()
        left, _top, right, _bottom = layout.getContentsMargins()
        columns = self.columns_for_width(
            available_width - left - right,
            item_width,
            spacing,
            max_columns=len(widgets),
        )

        for widget in widgets:
            layout.removeWidget(widget)

        for index, widget in enumerate(widgets):
            row, column = divmod(index, columns)
            layout.addWidget(widget, row, column, Qt.AlignLeft | Qt.AlignTop)

        for column in range(max(len(widgets), columns) + 1):
            layout.setColumnStretch(column, 0)
        layout.setColumnStretch(columns, 1)

    def columns_for_width(
        self,
        width: int,
        item_width: int,
        spacing: int,
        max_columns: Optional[int] = None,
    ) -> int:
        available_width = max(item_width, width)
        columns = max(1, (available_width + spacing) // (item_width + spacing))
        if max_columns is not None:
            columns = min(max_columns, columns)
        return columns

    def grid_height(self, item_height: int, spacing: int, rows: int) -> int:
        return rows * item_height + max(0, rows - 1) * spacing

    def time_grid_columns(self) -> int:
        left, _top, right, _bottom = self.time_list_layout.getContentsMargins()
        width = self.time_scroll.viewport().width() - left - right
        return self.columns_for_width(width, TIME_CHIP_WIDTH, TIME_GRID_SPACING)

    def load_settings(self):
        layout_version = self.setting_int("window/layout_version", 0)
        saved_geometry = self.settings.value("window/geometry")
        if saved_geometry is not None:
            self.restoreGeometry(saved_geometry)
            if layout_version < SETTINGS_LAYOUT_VERSION:
                if layout_version < 2:
                    self.resize(
                        max(self.width(), DEFAULT_WINDOW_WIDTH),
                        max(self.height(), DEFAULT_WINDOW_HEIGHT),
                    )
                elif layout_version < 7 and self.width() >= 1000 and self.height() <= 730:
                    self.resize(
                        max(self.width(), DEFAULT_WINDOW_WIDTH),
                        DEFAULT_WINDOW_HEIGHT,
                    )
                elif self.width() <= 950 or self.height() <= MIN_WINDOW_HEIGHT:
                    self.resize(
                        max(self.width(), MIN_WINDOW_WIDTH),
                        max(self.height(), MIN_WINDOW_HEIGHT),
                    )

        save_dir = self.settings.value("save_dir", "")
        if isinstance(save_dir, str) and save_dir.strip():
            self.save_dir = Path(save_dir)

        self.interval_spin.setValue(self.setting_float("interval/value", 60))
        self.check_button_by_property(
            self.unit_group,
            "seconds",
            self.setting_int("interval/unit_seconds", 1),
        )
        self.check_button_by_property(
            self.minute_group,
            "minutes",
            self.setting_int("minute/mark", 5),
        )

        self.daily_times = self.load_saved_times()
        self.render_time_chips()
        self.auto_check_updates = self.setting_bool("updates/auto_check", True)
        saved_shortcut = self.settings.value("hotkey/capture_once", DEFAULT_CAPTURE_SHORTCUT)
        self.capture_shortcut_sequence = normalize_shortcut_sequence(str(saved_shortcut))
        close_behavior = self.settings.value("window/close_behavior", "")
        if close_behavior in (CLOSE_BEHAVIOR_TRAY, CLOSE_BEHAVIOR_QUIT):
            self.close_behavior = str(close_behavior)
        else:
            self.close_behavior = CLOSE_BEHAVIOR_ASK
        if not self.tray_available and self.close_behavior == CLOSE_BEHAVIOR_TRAY:
            self.close_behavior = CLOSE_BEHAVIOR_QUIT

        active_custom = self.setting_bool("region/customized", False)
        saved_region = self.load_saved_region()
        self.custom_region = self.load_saved_custom_region()
        if self.custom_region is None and active_custom:
            self.custom_region = saved_region

        saved_capture_target = self.setting_int(
            "region/capture_target",
            CAPTURE_TARGET_CUSTOM if active_custom else CAPTURE_TARGET_FULLSCREEN,
        )
        if saved_capture_target not in (
            CAPTURE_TARGET_FULLSCREEN,
            CAPTURE_TARGET_CUSTOM,
            CAPTURE_TARGET_BROWSER,
        ):
            saved_capture_target = CAPTURE_TARGET_FULLSCREEN

        self.capture_target = saved_capture_target
        self.region_customized = (
            self.capture_target == CAPTURE_TARGET_CUSTOM and self.custom_region is not None
        )
        if self.capture_target == CAPTURE_TARGET_CUSTOM and self.custom_region is None:
            self.capture_target = CAPTURE_TARGET_FULLSCREEN
        self.region = self.custom_region if self.region_customized else self.default_region()
        self.sync_region_buttons()

        mode = self.setting_int("mode", 0)
        self.set_mode(mode if mode in (0, 1, 2) else 0)
        self.refresh_path()
        self.refresh_region()
        self.refresh_interval_preview()
        self.refresh_minute_preview()
        self.refresh_close_behavior_ui()
        self.restart_hotkey_listener()
        self.update_tray_ui()

    def save_settings(self):
        unit_button = self.unit_group.checkedButton()
        unit_seconds = int(unit_button.property("seconds")) if unit_button is not None else 1

        self.settings.setValue("window/layout_version", SETTINGS_LAYOUT_VERSION)
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("save_dir", str(self.save_dir))
        self.settings.setValue("mode", self.mode_group.checkedId())
        self.settings.setValue("interval/value", self.interval_spin.value())
        self.settings.setValue("interval/unit_seconds", unit_seconds)
        self.settings.setValue("minute/mark", self.mark_minutes())
        self.settings.setValue("daily/times", "|".join(self.daily_times))
        self.settings.setValue("region/capture_target", self.capture_target)
        self.settings.setValue("region/customized", self.region_customized)
        self.settings.setValue("region/x", self.region.x)
        self.settings.setValue("region/y", self.region.y)
        self.settings.setValue("region/width", self.region.width)
        self.settings.setValue("region/height", self.region.height)
        self.settings.setValue("updates/auto_check", self.auto_check_updates)
        self.settings.setValue("hotkey/capture_once", self.capture_shortcut_sequence)
        self.settings.setValue("window/close_behavior", "" if self.close_behavior == CLOSE_BEHAVIOR_ASK else self.close_behavior)
        if self.custom_region is not None:
            self.settings.setValue("region/custom_x", self.custom_region.x)
            self.settings.setValue("region/custom_y", self.custom_region.y)
            self.settings.setValue("region/custom_width", self.custom_region.width)
            self.settings.setValue("region/custom_height", self.custom_region.height)
        self.settings.sync()

    def setting_int(self, key: str, default: int) -> int:
        value = self.settings.value(key, default)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def setting_float(self, key: str, default: float) -> float:
        value = self.settings.value(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def setting_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def check_button_by_property(self, group: QButtonGroup, name: str, expected: int):
        for button in group.buttons():
            try:
                value = int(button.property(name))
            except (TypeError, ValueError):
                continue
            if value == expected:
                button.setChecked(True)
                return

    def load_saved_times(self) -> list[str]:
        raw_times = self.settings.value("daily/times", "")
        if not isinstance(raw_times, str):
            return []

        times = []
        for value in raw_times.split("|"):
            normalized = self.normalize_time_text(value)
            if normalized is not None and normalized not in times:
                times.append(normalized)
        return sorted(times)

    def normalize_time_text(self, value: str) -> Optional[str]:
        try:
            return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")
        except (AttributeError, ValueError):
            return None

    def load_saved_region(self) -> Optional[CaptureRegion]:
        return self.load_region_values(
            "region/x",
            "region/y",
            "region/width",
            "region/height",
        )

    def load_saved_custom_region(self) -> Optional[CaptureRegion]:
        return self.load_region_values(
            "region/custom_x",
            "region/custom_y",
            "region/custom_width",
            "region/custom_height",
        )

    def load_region_values(
        self,
        x_key: str,
        y_key: str,
        width_key: str,
        height_key: str,
    ) -> Optional[CaptureRegion]:
        region = CaptureRegion(
            x=self.setting_int(x_key, 0),
            y=self.setting_int(y_key, 0),
            width=self.setting_int(width_key, 0),
            height=self.setting_int(height_key, 0),
        )
        if region.width <= 0 or region.height <= 0:
            return None
        return region

    def closeEvent(self, event):
        if self.force_quit_requested:
            self.save_settings()
            self.stop_hotkey_listener()
            event.accept()
            return

        if self.tray_available:
            behavior = self.close_behavior
            if behavior == CLOSE_BEHAVIOR_ASK:
                behavior = self.ask_close_behavior()

            if behavior == CLOSE_BEHAVIOR_TRAY:
                self.save_settings()
                event.ignore()
                self.hide_to_tray()
                return
            if behavior == CLOSE_BEHAVIOR_QUIT:
                self.force_quit_requested = True
                self.save_settings()
                self.stop_hotkey_listener()
                self.teardown_tray_icon()
                event.accept()
                QTimer.singleShot(0, QApplication.instance().quit)
                return
            event.ignore()
            return

        self.save_settings()
        self.stop_hotkey_listener()
        event.accept()

    def refresh_path(self):
        self.path_value.setText(f"{self.save_dir}\n按日期自动保存到 {self.dated_save_dir().name}/")

    def refresh_capture_action_buttons(self):
        has_active_session = self.running or self.capture_in_progress
        self.start_button.setEnabled(not has_active_session)
        self.capture_once_button.setEnabled(not self.capture_in_progress and not self.single_capture_mode)
        self.stop_button.setEnabled(self.running)

    def dated_save_dir(self, captured_at: Optional[datetime] = None) -> Path:
        value = captured_at or datetime.now()
        return self.save_dir / value.strftime("%Y-%m-%d")

    def set_capture_options_locked(self, locked: bool):
        widgets = [
            self.choose_dir_button,
            self.interval_button,
            self.minute_button,
            self.daily_button,
            self.mode_stack,
            self.fullscreen_region_button,
            self.custom_region_button,
            self.browser_pages_button,
            self.reselect_region_button,
            self.add_time_button,
            self.daily_time,
            *self.daily_time_step_buttons,
        ]
        for button in self.unit_group.buttons():
            widgets.append(button)
        for button in self.minute_group.buttons():
            widgets.append(button)

        for widget in widgets:
            widget.setEnabled(not locked)

        if hasattr(self, "settings_panel_effect") and self.settings_panel_effect is not None:
            self.settings_panel_effect.setOpacity(0.76 if locked else 1.0)

        self.sync_region_buttons()

    def refresh_region(self):
        if self.capture_target == CAPTURE_TARGET_BROWSER:
            if self.system_name == "Windows":
                text = "逐个浏览器窗口截全屏；整批完成后再计下一次"
            else:
                text = "依次截取浏览器标签页；整批完成后再计下一次"
        elif self.region_customized:
            text = f"X {self.region.x}, Y {self.region.y}, {self.region.width} x {self.region.height}"
        else:
            text = "当前使用全屏截图"
        self.region_value.setText(text)

    def refresh_idle_note(self):
        if self.capture_in_progress and not self.running:
            self.note_label.setText("正在停止，当前这一轮结束后就会停下")
            self.update_tray_ui()
            return

        if self.running and self.single_capture_mode:
            self.note_label.setText("单次截图执行中")
            self.update_tray_ui()
            return

        if self.running and self.next_capture_at is not None:
            self.note_label.setText(
                f"下一次截图\n{self.next_capture_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.update_tray_ui()
            return

        if self.mode_group.checkedId() == 0:
            button = self.unit_group.checkedButton()
            unit = button.text() if button is not None else "秒"
            self.note_label.setText(f"每 {self.interval_spin.value():g} {unit}截图一次")
        elif self.mode_group.checkedId() == 1:
            minutes = self.mark_minutes()
            if minutes == 1:
                self.note_label.setText("每到新的分钟截图一次")
            elif minutes == 60:
                self.note_label.setText("每到整点截图一次")
            else:
                self.note_label.setText(f"每到 {minutes} 分钟点截图一次")
        elif self.daily_times:
            self.note_label.setText("定时截图\n" + "、".join(self.daily_times))
        else:
            self.note_label.setText("请先添加至少一个时间点")
        self.update_tray_ui()

    def choose_directory(self):
        if self.running:
            return

        chosen = QFileDialog.getExistingDirectory(self, "选择保存位置", str(self.save_dir))
        if chosen:
            self.save_dir = Path(chosen)
            self.refresh_path()
            self.refresh_idle_note()

    def open_save_directory(self):
        self.save_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.save_dir)))

    def set_mode(self, index: int):
        if self.running:
            return

        self.interval_button.setChecked(index == 0)
        self.minute_button.setChecked(index == 1)
        self.daily_button.setChecked(index == 2)
        self.mode_stack.setCurrentIndex(index)
        for button in (self.interval_button, self.minute_button, self.daily_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self.mode_stack.updateGeometry()
        self.mode_stack.repaint()
        self.centralWidget().update()
        self.refresh_idle_note()
        self.reflow_dynamic_layouts()

    def on_minute_rule_changed(self):
        self.refresh_minute_preview()
        self.refresh_idle_note()

    def on_interval_rule_changed(self):
        self.refresh_interval_preview()
        self.refresh_idle_note()

    def interval_seconds(self) -> float:
        button = self.unit_group.checkedButton()
        multiplier = float(button.property("seconds")) if button else 1.0
        return float(self.interval_spin.value()) * multiplier

    def mark_minutes(self) -> int:
        button = self.minute_group.checkedButton()
        return int(button.property("minutes")) if button else 5

    def step_daily_time(self, minutes: int):
        if self.running:
            return
        self.daily_time.setTime(self.daily_time.time().addSecs(minutes * 60))

    def refresh_interval_preview(self):
        button = self.unit_group.checkedButton()
        unit = button.text() if button is not None else "秒"
        self.interval_preview.setText(f"预览：每 {self.interval_spin.value():g} {unit}截图一次")

    def refresh_minute_preview(self):
        minutes = self.mark_minutes()
        start = datetime.combine(datetime.now().date(), dt_time(12, 0))
        examples = "、".join(
            (start + timedelta(minutes=minutes * index)).strftime("%H:%M")
            for index in range(3)
        )

        if minutes == 1:
            text = f"预览：每个新分钟都会截图，例如 {examples}"
        elif minutes == 60:
            text = f"预览：每个整点截图，例如 {examples}"
        else:
            text = f"预览：每到 {minutes} 的倍数分钟截图，例如 {examples}"
        self.minute_preview.setText(text)

    def add_time(self, value: str, silent: bool = False):
        if self.running:
            return

        if value not in self.daily_times:
            self.daily_times.append(value)
            self.daily_times.sort()
            self.render_time_chips()
        if not silent:
            self.refresh_idle_note()

    def remove_time(self, value: str):
        if self.running:
            return

        self.daily_times = [item for item in self.daily_times if item != value]
        self.render_time_chips()
        self.refresh_idle_note()

    def render_time_chips(self, force: bool = True):
        columns = self.time_grid_columns()
        viewport_width = self.time_scroll.viewport().width()
        if (
            not force
            and columns == getattr(self, "current_time_columns", None)
            and len(self.daily_times) == getattr(self, "current_time_count", None)
            and viewport_width == getattr(self, "current_time_viewport_width", None)
        ):
            return

        while self.time_list_layout.count() > 0:
            item = self.time_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, value in enumerate(self.daily_times):
            chip = TimeChip(value)
            chip.remove_requested.connect(self.remove_time)
            row, column = divmod(index, columns)
            self.time_list_layout.addWidget(chip, row, column, Qt.AlignLeft | Qt.AlignTop)

        previous_columns = getattr(self, "current_time_columns", columns)
        previous_rows = getattr(self, "current_time_rows", 0)
        for column in range(max(previous_columns, columns) + 2):
            self.time_list_layout.setColumnStretch(column, 0)
        for row in range(previous_rows + 2):
            self.time_list_layout.setRowStretch(row, 0)

        rows = max(1, (len(self.daily_times) + columns - 1) // columns)
        content_width = max(
            viewport_width,
            columns * TIME_CHIP_WIDTH + max(0, columns - 1) * TIME_GRID_SPACING,
        )
        content_height = self.grid_height(TIME_CHIP_HEIGHT, TIME_GRID_SPACING, rows)
        self.time_list.setFixedSize(content_width, content_height)
        self.time_list_layout.setColumnStretch(columns, 1)
        self.time_list_layout.setRowStretch(rows, 1)
        self.current_time_columns = columns
        self.current_time_rows = rows
        self.current_time_count = len(self.daily_times)
        self.current_time_viewport_width = viewport_width

    def use_fullscreen_region(self):
        if self.running:
            self.sync_region_buttons()
            return

        self.capture_target = CAPTURE_TARGET_FULLSCREEN
        self.region = self.default_region()
        self.region_customized = False
        self.sync_region_buttons()
        self.refresh_region()

    def use_custom_region(self):
        if self.running:
            self.sync_region_buttons()
            return

        self.capture_target = CAPTURE_TARGET_CUSTOM
        if self.custom_region is None:
            self.select_region()
            return

        self.region = self.custom_region
        self.region_customized = True
        self.sync_region_buttons()
        self.refresh_region()

    def use_browser_pages(self):
        if self.running:
            self.sync_region_buttons()
            return

        self.capture_target = CAPTURE_TARGET_BROWSER
        self.region_customized = False
        self.region = self.default_region()
        self.sync_region_buttons()
        self.refresh_region()

    def select_region(self):
        if self.running:
            self.sync_region_buttons()
            return

        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            QMessageBox.warning(self, "无法选择", "没有检测到可用屏幕。")
            self.sync_region_buttons()
            return

        self.restore_geometry = self.geometry()
        self.restore_window_state = self.windowState()
        self.hide()
        QApplication.processEvents()

        QTimer.singleShot(120, lambda selected_screen=screen: self.open_selection_overlay(selected_screen))

    def open_selection_overlay(self, screen):
        self.overlay = SelectionOverlay(screen, QPixmap())
        self.overlay.selection_made.connect(self.on_region_selected)
        self.overlay.selection_cancelled.connect(self.on_region_cancelled)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def screen_capture_region(self, screen) -> CaptureRegion:
        geometry = screen.geometry()
        ratio = screen.devicePixelRatio()
        return CaptureRegion(
            x=round(geometry.x() * ratio),
            y=round(geometry.y() * ratio),
            width=round(geometry.width() * ratio),
            height=round(geometry.height() * ratio),
        )

    def capture_screen_pixmap(self, screen) -> QPixmap:
        if self.system_name == "Darwin":
            pixmap = self.capture_full_screen_pixmap()
            if not pixmap.isNull():
                return pixmap

        try:
            pixmap = self.capture_region_pixmap(self.screen_capture_region(screen))
            if not pixmap.isNull():
                return pixmap
        except Exception:  # noqa: BLE001
            pass

        return screen.grabWindow(0)

    def capture_full_screen_pixmap(self) -> QPixmap:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            subprocess.run(
                ["screencapture", "-x", str(temp_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return QPixmap(str(temp_path))
        except Exception:  # noqa: BLE001
            return QPixmap()
        finally:
            temp_path.unlink(missing_ok=True)

    def capture_region_with_screencapture(self, region: CaptureRegion, filepath: Path):
        region_text = f"{region.x},{region.y},{region.width},{region.height}"
        try:
            subprocess.run(
                ["screencapture", "-x", f"-R{region_text}", str(filepath)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "系统没有成功读取当前选区。请确认已经给 PyCharm、Python 或定格截图开启“屏幕录制”权限。"
            ) from exc

    def warm_screen_recording_permission(self):
        if self.system_name != "Darwin":
            return

        thread = threading.Thread(target=self.capture_full_screen_pixmap, daemon=True)
        thread.start()

    def capture_region_pixmap(self, region: CaptureRegion) -> QPixmap:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            if self.system_name == "Darwin":
                try:
                    self.capture_region_with_screencapture(region, temp_path)
                except RuntimeError:
                    full_screen = self.capture_full_screen_pixmap()
                    if full_screen.isNull():
                        raise
                    return full_screen.copy(region.x, region.y, region.width, region.height)
            else:
                if ImageGrab is None:
                    raise RuntimeError("当前系统缺少 Pillow，无法截图。")
                image = ImageGrab.grab(
                    bbox=(
                        region.x,
                        region.y,
                        region.x + region.width,
                        region.y + region.height,
                    )
                )
                image.save(temp_path)
            return QPixmap(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

    def screen_for_region(self, region: CaptureRegion):
        center = QPoint(region.x + region.width // 2, region.y + region.height // 2)
        for screen in QApplication.screens():
            screen_region = self.screen_capture_region(screen)
            screen_rect = QRect(
                screen_region.x,
                screen_region.y,
                screen_region.width,
                screen_region.height,
            )
            if screen_rect.contains(center):
                return screen
        return QApplication.primaryScreen()

    def preview_region(self):
        if not self.region_customized:
            QMessageBox.information(self, "暂无选区", "当前使用全屏截图，请先选取截图区域。")
            return

        screen = self.screen_for_region(self.region)
        if screen is None:
            QMessageBox.warning(self, "无法预览", "没有检测到当前选区所在的屏幕。")
            return

        if self.preview_overlay is not None:
            self.preview_overlay.close()
        self.preview_overlay = RegionPreviewOverlay(screen, self.region)
        self.preview_overlay.destroyed.connect(lambda: setattr(self, "preview_overlay", None))
        self.preview_overlay.show()
        self.preview_overlay.raise_()
        self.preview_overlay.activateWindow()

    def on_region_selected(self, region: CaptureRegion):
        self.custom_region = region
        self.region = region
        self.capture_target = CAPTURE_TARGET_CUSTOM
        self.region_customized = True
        self.sync_region_buttons()
        self.refresh_region()
        self.restore_main_window()

    def on_region_cancelled(self):
        self.sync_region_buttons()
        self.restore_main_window()

    def sync_region_buttons(self):
        self.fullscreen_region_button.setChecked(self.capture_target == CAPTURE_TARGET_FULLSCREEN)
        self.custom_region_button.setChecked(self.capture_target == CAPTURE_TARGET_CUSTOM)
        self.browser_pages_button.setChecked(self.capture_target == CAPTURE_TARGET_BROWSER)
        is_custom_target = self.capture_target == CAPTURE_TARGET_CUSTOM
        is_unlocked = not self.running
        self.preview_region_button.setVisible(is_custom_target)
        self.preview_region_button.setEnabled(self.custom_region is not None)
        self.reselect_region_button.setVisible(is_custom_target)
        self.reselect_region_button.setEnabled(is_unlocked and self.custom_region is not None)
        for button in (
            self.fullscreen_region_button,
            self.custom_region_button,
            self.browser_pages_button,
        ):
            button.setEnabled(is_unlocked)

    def restore_main_window(self):
        geometry = self.restore_geometry
        state = self.restore_window_state
        self.restore_geometry = None
        self.restore_window_state = None
        self.overlay = None

        if state is not None and state & Qt.WindowMaximized:
            self.showMaximized()
        else:
            self.showNormal()
            if geometry is not None:
                self.setGeometry(geometry)

        self.raise_()
        self.activateWindow()

    def run_osascript(self, script: str) -> str:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(message or "执行浏览器自动化脚本失败。") from exc
        return result.stdout.strip()

    def warm_browser_capture_permissions(self):
        thread = threading.Thread(target=self.warm_browser_capture_permissions_worker, daemon=True)
        thread.start()

    def warm_browser_capture_permissions_worker(self):
        available_apps: list[tuple[str, str]] = []
        for app_name, display_name in BROWSER_APPS:
            try:
                output = self.run_osascript(self.browser_tabs_script(app_name))
            except RuntimeError:
                continue
            if output.strip():
                available_apps.append((app_name, display_name))

        self.browser_capture_apps = available_apps
        self.browser_capture_apps_ready = True

    def is_macos_automation_permission_error(self, message: str) -> bool:
        markers = (
            "-1743",
            "not authorized",
            "not permitted",
            "not allowed",
            "未获授权",
            "没有权限",
            "不允许",
        )
        lower_message = message.lower()
        return any(marker.lower() in lower_message for marker in markers)

    def browser_tabs(self, strict_errors: bool = False) -> list[BrowserTab]:
        tabs: list[BrowserTab] = []
        errors: list[str] = []
        permission_errors: list[str] = []
        apps = self.browser_capture_apps if self.browser_capture_apps_ready else []
        for app_name, display_name in apps:
            try:
                output = self.run_osascript(self.browser_tabs_script(app_name))
            except RuntimeError as exc:
                message = str(exc)
                if self.is_macos_automation_permission_error(message):
                    permission_errors.append(f"{display_name}: {message}")
                elif strict_errors:
                    errors.append(f"{display_name}: {message}")
                continue

            for line in output.splitlines():
                parts = line.split("\t", 3)
                if len(parts) != 4:
                    continue
                window_index, tab_index, title, url = parts
                try:
                    tabs.append(
                        BrowserTab(
                            app_name=app_name,
                            display_name=display_name,
                            window_index=int(window_index),
                            tab_index=int(tab_index),
                            title=title.strip() or "未命名页面",
                            url=url.strip(),
                        )
                    )
                except ValueError:
                    continue

        if strict_errors and not tabs and permission_errors:
            detail = "\n".join(permission_errors[:4])
            raise RuntimeError(
                "macOS 还没有允许定格截图控制部分浏览器。\n\n"
                "请在弹出的系统提示中选择“允许”，或到“系统设置 > 隐私与安全性 > 自动化”里手动开启。\n\n"
                f"{detail}"
            )
        if strict_errors and not tabs and errors:
            detail = "\n".join(errors[:4])
            raise RuntimeError(
                "检测到了浏览器，但没有成功读取到标签页。\n\n"
                "这通常是某个浏览器不支持当前的自动化脚本，不是权限开关没打开。\n\n"
                f"{detail}"
            )
        if strict_errors and not tabs and not self.browser_capture_apps_ready:
            raise RuntimeError("浏览器权限预热还没有完成，请稍等几秒后再开始。")
        return tabs

    def ensure_browser_capture_ready(self):
        if self.system_name == "Darwin":
            return

        if self.system_name == "Windows":
            if ImageGrab is None:
                raise RuntimeError("当前系统缺少 Pillow，无法在 Windows 上截图。")
            if not self.windows_browser_windows():
                raise RuntimeError("没有检测到已打开的浏览器窗口。请先让浏览器保持打开状态。")

    def browser_tabs_script(self, app_name: str) -> str:
        return f'''
        set output to ""
        set delimiter to ASCII character 9
        tell application "System Events"
            if not (exists process "{app_name}") then return output
        end tell
        tell application "{app_name}"
            set windowCount to count of windows
            repeat with w from 1 to windowCount
                set tabCount to count of tabs of window w
                repeat with t from 1 to tabCount
                    set tabTitle to ""
                    set tabUrl to ""
                    try
                        set tabTitle to title of tab t of window w
                    end try
                    if tabTitle is "" then
                        try
                            set tabTitle to name of tab t of window w
                        end try
                    end if
                    try
                        set tabUrl to URL of tab t of window w
                    end try
                    set output to output & w & delimiter & t & delimiter & tabTitle & delimiter & tabUrl & linefeed
                end repeat
            end repeat
        end tell
        return output
        '''

    def activate_browser_tab(self, tab: BrowserTab):
        if tab.app_name == "Safari":
            script = f'''
            tell application "{tab.app_name}"
                activate
                set index of window {tab.window_index} to 1
                set current tab of window {tab.window_index} to tab {tab.tab_index} of window {tab.window_index}
            end tell
            '''
        else:
            script = f'''
            tell application "{tab.app_name}"
                activate
                set index of window {tab.window_index} to 1
                set active tab index of window {tab.window_index} to {tab.tab_index}
            end tell
            '''
        self.run_osascript(script)
        QApplication.processEvents()

    def front_browser_window_region(self, app_name: str) -> CaptureRegion:
        output = self.run_osascript(
            f'''
            tell application "{app_name}"
                activate
                set index of window 1 to 1
                set windowBounds to bounds of window 1
                return (item 1 of windowBounds as text) & "," & ¬
                    (item 2 of windowBounds as text) & "," & ¬
                    ((item 3 of windowBounds) - (item 1 of windowBounds) as text) & "," & ¬
                    ((item 4 of windowBounds) - (item 2 of windowBounds) as text)
            end tell
            '''
        )
        x_text, y_text, width_text, height_text = output.split(",", 3)
        x = float(x_text)
        y = float(y_text)
        width = float(width_text)
        height = float(height_text)
        screen = QApplication.screenAt(QPoint(round(x + width / 2), round(y + height / 2)))
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
        return CaptureRegion(
            x=round(x * ratio),
            y=round(y * ratio),
            width=round(width * ratio),
            height=round(height * ratio),
        )

    def safe_filename_part(self, value: str, default: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", value.strip())
        cleaned = cleaned.strip("._")
        return (cleaned or default)[:60]

    def report_image_src(self, image_path: Path, report_dir: Path) -> str:
        if image_path.parent == report_dir:
            return image_path.name
        return image_path.as_posix()

    def queue_capture_report(self, timestamp: str, records: list[CaptureRecord]):
        if not records:
            return

        thread = threading.Thread(
            target=self.write_capture_report_safely,
            args=(timestamp, records),
            daemon=True,
        )
        thread.start()

    def write_capture_report_safely(self, timestamp: str, records: list[CaptureRecord]):
        try:
            self.write_capture_report(timestamp, records)
        except Exception as exc:  # noqa: BLE001
            log_dir = records[0].filepath.parent if records else self.dated_save_dir()
            log_path = log_dir / "report_errors.log"
            with self.report_lock:
                with log_path.open("a", encoding="utf-8") as file:
                    file.write(f"{datetime.now().isoformat(timespec='seconds')} {exc}\n")

    def write_capture_report(self, timestamp: str, records: list[CaptureRecord]):
        report_dir = records[0].filepath.parent
        report_path = report_dir / f"capture_{timestamp}.html"

        with self.report_lock:
            report_path.write_text(
                self.capture_report_html(timestamp, records, report_dir),
                encoding="utf-8",
            )

    def capture_report_html(self, timestamp: str, records: list[CaptureRecord], report_dir: Path) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        first_time = records[0].captured_at.strftime("%Y-%m-%d %H:%M:%S")
        cards = "\n".join(self.capture_report_card(record, report_dir, index) for index, record in enumerate(records, 1))
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>定格截图报告 {escape(timestamp)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f5f7;
      --panel: #ffffff;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --line: #dedee6;
      --blue: #0a84ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.55;
    }}
    main {{
      width: min(1180px, calc(100% - 40px));
      margin: 28px auto 44px;
    }}
    header {{
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .summary {{
      color: var(--muted);
      font-size: 14px;
    }}
    .shot-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      margin-top: 16px;
      overflow: hidden;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.045);
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }}
    .meta div {{
      min-width: 0;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 2px;
    }}
    .value {{
      word-break: break-word;
      font-weight: 600;
    }}
    .canvas-wrap {{
      position: relative;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: #fafafa;
    }}
    .image-stage {{
      position: relative;
      width: 100%;
      overflow: hidden;
    }}
    canvas {{
      display: none;
      width: 100%;
      height: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }}
    .shot-image {{
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100% - 24px, 1180px); margin-top: 18px; }}
      .meta {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>定格截图报告</h1>
      <div class="summary">截图时间：{escape(first_time)} · 本次截图：{len(records)} 张 · 报告生成：{escape(generated_at)}</div>
    </header>
    {cards}
  </main>
  <script>
    document.querySelectorAll("canvas[data-src]").forEach((canvas) => {{
      const ctx = canvas.getContext("2d");
      const img = new Image();
      img.onload = () => {{
        canvas.width = img.naturalWidth || img.width;
        canvas.height = img.naturalHeight || img.height;
        ctx.drawImage(img, 0, 0);
        canvas.style.display = "block";
        const fallback = canvas.nextElementSibling;
        if (fallback) fallback.style.display = "none";
      }};
      img.onerror = () => {{
        canvas.width = 1200;
        canvas.height = 180;
        ctx.fillStyle = "#f5f5f7";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#6e6e73";
        ctx.font = "28px sans-serif";
        ctx.fillText("图片加载失败：" + canvas.dataset.src, 32, 96);
      }};
      img.src = canvas.dataset.src;
    }});
  </script>
</body>
</html>
"""

    def capture_report_card(self, record: CaptureRecord, report_dir: Path, index: int) -> str:
        image_src = self.report_image_src(record.filepath, report_dir)
        title = record.page_title or record.capture_type
        browser = record.browser_name or "-"
        url = record.url or "-"
        return f"""
    <section class="shot-card">
      <div class="meta">
        <div><span class="label">序号</span><span class="value">{index}</span></div>
        <div><span class="label">截图时间</span><span class="value">{escape(record.captured_at.strftime("%Y-%m-%d %H:%M:%S"))}</span></div>
        <div><span class="label">截图方式</span><span class="value">{escape(record.capture_type)}</span></div>
        <div><span class="label">浏览器</span><span class="value">{escape(browser)}</span></div>
        <div><span class="label">页面标题</span><span class="value">{escape(title)}</span></div>
        <div><span class="label">页面地址</span><span class="value">{escape(url)}</span></div>
        <div><span class="label">截图文件</span><span class="value">{escape(record.filepath.name)}</span></div>
      </div>
      <div class="canvas-wrap">
        <div class="image-stage">
          <canvas data-src="{escape(image_src, quote=True)}"></canvas>
          <img class="shot-image" src="{escape(image_src, quote=True)}" alt="截图 {index}">
        </div>
      </div>
    </section>
"""

    def set_browser_capture_progress(
        self,
        browser_name: str,
        current_index: int,
        total_count: Optional[int] = None,
        title: str = "",
    ):
        if not self.running:
            return
        self.status_card.set_value("正在截图")
        if total_count is not None and total_count > 0:
            text = f"正在截图 {browser_name} 第 {current_index}/{total_count} 个标签页"
        else:
            text = f"正在截图 {browser_name} 第 {current_index} 个标签页"
        if title:
            text += f"\n{title}"
        self.note_label.setText(text)
        self.update_tray_ui()
        QApplication.processEvents()

    def restore_window_after_background_capture(self, was_hidden: bool):
        if was_hidden:
            self.update_tray_ui()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_tray_ui()

    def save_browser_page_screenshots(self, timestamp: str, max_count: int, output_dir: Path) -> list[CaptureRecord]:
        if max_count <= 0:
            return []

        if self.system_name == "Windows":
            return self.save_windows_browser_page_screenshots(timestamp, max_count, output_dir)
        if self.system_name != "Darwin":
            raise RuntimeError("浏览器页面截图目前只支持 macOS 和 Windows。")

        tabs = self.browser_tabs(strict_errors=True)
        if not tabs:
            raise RuntimeError("没有检测到已打开的浏览器标签页。")

        records: list[CaptureRecord] = []
        total_count = min(len(tabs), max_count)
        was_hidden = self.isHidden()
        try:
            for index, tab in enumerate(tabs, start=1):
                if len(records) >= max_count or not self.running:
                    break

                self.set_browser_capture_progress(tab.display_name, index, total_count, tab.title)
                if not self.running:
                    break
                self.activate_browser_tab(tab)
                QApplication.processEvents()
                if not self.running:
                    break
                time.sleep(0.45)
                QApplication.processEvents()
                if not self.running:
                    break

                region = self.front_browser_window_region(tab.app_name)
                browser_name = self.safe_filename_part(tab.display_name, "Browser")
                title = self.safe_filename_part(tab.title, f"page_{index}")
                filepath = output_dir / f"browser_{timestamp}_{index:03d}_{browser_name}_{title}.png"
                self.capture_region_with_screencapture(region, filepath)
                records.append(
                    CaptureRecord(
                        captured_at=datetime.now(),
                        filepath=filepath,
                        capture_type="浏览器页面",
                        page_title=tab.title,
                        url=tab.url,
                        browser_name=tab.display_name,
                    )
                )
        finally:
            self.restore_window_after_background_capture(was_hidden)

        return records

    def windows_api(self):
        try:
            import ctypes
            import ctypes.wintypes
        except ImportError as exc:
            raise RuntimeError("当前 Python 无法调用 Windows 自动化接口。") from exc
        return ctypes

    def windows_process_name(self, pid: int) -> str:
        ctypes = self.windows_api()
        kernel32 = ctypes.windll.kernel32
        process_query_limited_information = 0x1000
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ""
        try:
            buffer_size = ctypes.wintypes.DWORD(260)
            buffer = ctypes.create_unicode_buffer(buffer_size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_size)):
                return Path(buffer.value).name.lower()
            return ""
        finally:
            kernel32.CloseHandle(handle)

    def windows_browser_windows(self) -> list[tuple[int, str, str]]:
        ctypes = self.windows_api()
        user32 = ctypes.windll.user32
        windows: list[tuple[int, str, str]] = []

        enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title_length = user32.GetWindowTextLengthW(hwnd)
            if title_length <= 0:
                return True

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_name = self.windows_process_name(pid.value)
            display_name = WINDOWS_BROWSER_EXECUTABLES.get(process_name)
            if display_name is None:
                return True

            title = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title, title_length + 1)
            windows.append((int(hwnd), display_name, title.value))
            return True

        user32.EnumWindows(enum_windows_proc(callback), 0)
        return windows

    def activate_windows_window(self, hwnd: int):
        ctypes = self.windows_api()
        user32 = ctypes.windll.user32
        sw_restore = 9
        user32.ShowWindow(hwnd, sw_restore)
        user32.SetForegroundWindow(hwnd)

    def windows_window_title(self, hwnd: int) -> str:
        ctypes = self.windows_api()
        user32 = ctypes.windll.user32
        title_length = user32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return ""
        title = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title, title_length + 1)
        return title.value

    def send_windows_ctrl_tab(self):
        ctypes = self.windows_api()

        user32 = ctypes.windll.user32
        keyeventf_keyup = 0x0002
        vk_control = 0x11
        vk_tab = 0x09
        user32.keybd_event(vk_control, 0, 0, 0)
        user32.keybd_event(vk_tab, 0, 0, 0)
        user32.keybd_event(vk_tab, 0, keyeventf_keyup, 0)
        user32.keybd_event(vk_control, 0, keyeventf_keyup, 0)

    def save_windows_browser_page_screenshots(self, timestamp: str, max_count: int, output_dir: Path) -> list[CaptureRecord]:
        if max_count <= 0:
            return []

        if ImageGrab is None:
            raise RuntimeError("当前系统缺少 Pillow，无法在 Windows 上截图。")

        browser_windows = self.windows_browser_windows()
        if not browser_windows:
            raise RuntimeError("没有检测到已打开的浏览器窗口。请先让浏览器保持打开状态。")

        was_hidden = self.isHidden()
        self.hide()
        QApplication.processEvents()
        time.sleep(0.35)

        records: list[CaptureRecord] = []
        try:
            for window_index, (hwnd, browser_name, _title) in enumerate(browser_windows, start=1):
                if len(records) >= max_count or not self.running:
                    break

                self.activate_windows_window(hwnd)
                time.sleep(WINDOWS_BROWSER_PAGE_DELAY_SECONDS)
                if not self.running:
                    break
                first_title = self.windows_window_title(hwnd)
                seen_titles: set[str] = set()

                for _ in range(WINDOWS_BROWSER_TAB_SAFETY_LIMIT):
                    if len(records) >= max_count or not self.running:
                        break

                    current_title = self.windows_window_title(hwnd)
                    if current_title in seen_titles:
                        break

                    seen_titles.add(current_title)
                    self.set_browser_capture_progress(
                        browser_name,
                        len(records) + 1,
                        None,
                        current_title,
                    )
                    title_part = self.safe_filename_part(current_title, f"tab_{len(seen_titles)}")
                    filepath = (
                        output_dir
                        / f"browser_{timestamp}_{len(records) + 1:03d}_{browser_name}_w{window_index}_{title_part}.png"
                    )
                    image = ImageGrab.grab()
                    image.save(filepath)
                    records.append(
                        CaptureRecord(
                            captured_at=datetime.now(),
                            filepath=filepath,
                            capture_type="浏览器页面",
                            page_title=current_title,
                            browser_name=browser_name,
                        )
                    )

                    if len(records) >= max_count:
                        break

                    self.send_windows_ctrl_tab()
                    time.sleep(WINDOWS_BROWSER_PAGE_DELAY_SECONDS)
                    QApplication.processEvents()
                    if not self.running:
                        break

                    if self.windows_window_title(hwnd) == first_title and len(seen_titles) > 0:
                        break
        finally:
            self.restore_window_after_background_capture(was_hidden)

        return records

    def start_capture(self):
        if self.running:
            QMessageBox.information(self, "正在运行", "截图任务已经开始了。")
            return

        if self.mode_group.checkedId() == 2 and not self.daily_times:
            QMessageBox.warning(self, "缺少时间点", "请先添加至少一个截图时间点。")
            return

        if self.capture_target == CAPTURE_TARGET_BROWSER:
            try:
                self.ensure_browser_capture_ready()
            except Exception as exc:  # noqa: BLE001
                self.status_card.set_value("未开始")
                self.note_label.setText(f"浏览器截图未准备好：{exc}")
                QMessageBox.warning(
                    self,
                    "浏览器截图未准备好",
                    f"{exc}",
                )
                return

        self.begin_capture_run(single_capture=False)

    def capture_once(self):
        if self.capture_in_progress:
            QMessageBox.information(self, "正在截图", "请先等待当前这轮截图完成。")
            return

        if self.capture_target == CAPTURE_TARGET_BROWSER:
            try:
                self.ensure_browser_capture_ready()
            except Exception as exc:  # noqa: BLE001
                self.status_card.set_value("未开始")
                self.note_label.setText(f"浏览器截图未准备好：{exc}")
                QMessageBox.warning(
                    self,
                    "浏览器截图未准备好",
                    f"{exc}",
                )
                return

        if self.running:
            self.pending_manual_resume_at = self.next_capture_at
            self.timer.stop()
            self.next_capture_at = None
            self.status_card.set_value("准备截图")
            self.note_label.setText("立即执行一轮截图；若原定时间未过，则继续按原计划")
            self.update_tray_ui()
            QTimer.singleShot(0, self.on_timer_timeout)
            return

        self.begin_capture_run(single_capture=True)

    def begin_capture_run(self, single_capture: bool):
        self.dated_save_dir().mkdir(parents=True, exist_ok=True)
        self.running = True
        self.capture_in_progress = False
        self.single_capture_mode = single_capture
        self.last_runtime_error = ""
        self.pending_manual_resume_at = None
        self.capture_count = 0
        self.count_card.set_current_value("0")
        self.count_card.set_total_value(str(self.total_capture_count))
        self.set_capture_options_locked(True)
        self.refresh_capture_action_buttons()
        self.update_tray_ui()
        if single_capture:
            self.next_capture_at = None
            self.status_card.set_value("准备截图")
            self.note_label.setText("单次截图准备中")
            QTimer.singleShot(0, self.on_timer_timeout)
            return

        self.status_card.set_value("等待执行")
        self.schedule_next_capture()

    def stop_capture(self):
        if self.capture_in_progress:
            self.running = False
            self.next_capture_at = None
            self.pending_manual_resume_at = None
            self.timer.stop()
            self.last_runtime_error = ""
            self.status_card.set_value("正在停止")
            self.refresh_capture_action_buttons()
            self.refresh_idle_note()
            return

        self.running = False
        self.capture_in_progress = False
        self.single_capture_mode = False
        self.next_capture_at = None
        self.pending_manual_resume_at = None
        self.timer.stop()
        self.last_runtime_error = ""
        self.status_card.set_value("已停止")
        self.set_capture_options_locked(False)
        self.refresh_capture_action_buttons()
        self.refresh_idle_note()

    def restore_pending_capture_schedule(self) -> bool:
        scheduled_at = self.pending_manual_resume_at
        self.pending_manual_resume_at = None
        if scheduled_at is None or not self.running:
            return False

        now = datetime.now()
        if scheduled_at <= now:
            return False

        self.next_capture_at = scheduled_at
        delay_seconds = max((scheduled_at - now).total_seconds(), 0.5)
        self.status_card.set_value("等待执行")
        self.timer.start(max(500, int(delay_seconds * 1000)))
        self.refresh_capture_action_buttons()
        self.refresh_idle_note()
        return True

    def schedule_next_capture(self):
        if not self.running:
            return

        now = datetime.now()
        mode = self.mode_group.checkedId()
        if mode == 0:
            delay_seconds = self.interval_seconds()
            self.next_capture_at = now + timedelta(seconds=delay_seconds)
        elif mode == 1:
            self.next_capture_at = self.next_mark_datetime(now)
            delay_seconds = max((self.next_capture_at - now).total_seconds(), 1)
        else:
            self.next_capture_at = self.next_daily_datetime(now)
            delay_seconds = max((self.next_capture_at - now).total_seconds(), 1)

        self.status_card.set_value("等待执行")
        self.timer.start(max(500, int(delay_seconds * 1000)))
        self.refresh_capture_action_buttons()
        self.refresh_idle_note()

    def next_daily_datetime(self, now: datetime) -> datetime:
        candidates = []
        for value in self.daily_times:
            hour, minute = [int(part) for part in value.split(":")]
            candidate = datetime.combine(now.date(), dt_time(hour, minute))
            if candidate <= now:
                candidate += timedelta(days=1)
            candidates.append(candidate)
        return min(candidates)

    def next_mark_datetime(self, now: datetime) -> datetime:
        minutes = self.mark_minutes()
        candidate = now.replace(second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(minutes=1)

        for _ in range(0, 61):
            if minutes == 60:
                if candidate.minute == 0:
                    return candidate
            elif candidate.minute % minutes == 0:
                return candidate
            candidate += timedelta(minutes=1)

        return candidate

    def on_timer_timeout(self):
        if self.capture_in_progress or not self.running:
            return

        self.capture_in_progress = True
        self.status_card.set_value("正在截图")
        self.refresh_capture_action_buttons()
        self.update_tray_ui()
        QApplication.processEvents()

        try:
            saved_count = self.save_screenshot()
        except Exception as exc:  # noqa: BLE001
            self.capture_in_progress = False
            self.running = False
            self.single_capture_mode = False
            self.timer.stop()
            self.next_capture_at = None
            self.pending_manual_resume_at = None
            self.last_runtime_error = str(exc)
            self.status_card.set_value("运行失败")
            self.set_capture_options_locked(False)
            self.refresh_capture_action_buttons()
            self.note_label.setText(f"截图失败：{exc}")
            self.update_tray_ui()
            QMessageBox.critical(
                self,
                "截图失败",
                f"截图时出现错误。\n\n{exc}",
            )
            return

        self.capture_in_progress = False
        self.capture_count += max(0, saved_count)
        self.total_capture_count += max(0, saved_count)
        self.count_card.set_current_value(str(self.capture_count))
        self.count_card.set_total_value(str(self.total_capture_count))
        if not self.running:
            self.single_capture_mode = False
            self.timer.stop()
            self.next_capture_at = None
            self.pending_manual_resume_at = None
            self.last_runtime_error = ""
            self.status_card.set_value("已停止")
            self.set_capture_options_locked(False)
            self.refresh_capture_action_buttons()
            self.note_label.setText(f"截图已停止，本次任务共保存 {self.capture_count} 张")
            self.update_tray_ui()
            return

        if self.single_capture_mode:
            self.running = False
            self.single_capture_mode = False
            self.timer.stop()
            self.next_capture_at = None
            self.pending_manual_resume_at = None
            self.last_runtime_error = ""
            self.status_card.set_value("已完成")
            self.set_capture_options_locked(False)
            self.refresh_capture_action_buttons()
            self.note_label.setText(f"单次截图已完成，本次保存 {saved_count} 张")
            self.update_tray_ui()
            return

        if self.capture_count >= MAX_CAPTURE_IMAGES_PER_RUN:
            self.running = False
            self.single_capture_mode = False
            self.timer.stop()
            self.next_capture_at = None
            self.pending_manual_resume_at = None
            self.last_runtime_error = ""
            self.status_card.set_value("已完成")
            self.set_capture_options_locked(False)
            self.refresh_capture_action_buttons()
            self.note_label.setText(f"已达到单次 {MAX_CAPTURE_IMAGES_PER_RUN:,} 张上限，截图已自动停止")
            self.update_tray_ui()
            return

        if self.restore_pending_capture_schedule():
            return

        self.schedule_next_capture()

    def save_screenshot(self):
        captured_at = datetime.now()
        timestamp = captured_at.strftime("%Y%m%d_%H%M%S")
        output_dir = self.dated_save_dir(captured_at)
        output_dir.mkdir(parents=True, exist_ok=True)
        remaining_count = MAX_CAPTURE_IMAGES_PER_RUN - self.capture_count
        if remaining_count <= 0:
            return 0

        if self.capture_target == CAPTURE_TARGET_BROWSER:
            records = self.save_browser_page_screenshots(timestamp, remaining_count, output_dir)
            self.queue_capture_report(timestamp, records)
            return len(records)

        filepath = output_dir / f"screenshot_{timestamp}.png"

        if self.system_name == "Darwin":
            self.capture_region_with_screencapture(self.region, filepath)
            return 1

        if ImageGrab is None:
            raise RuntimeError("当前系统缺少 Pillow，无法截图。")

        image = ImageGrab.grab(
            bbox=(
                self.region.x,
                self.region.y,
                self.region.x + self.region.width,
                self.region.y + self.region.height,
            )
        )
        image.save(filepath)
        return 1


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(SETTINGS_ORGANIZATION)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setQuitOnLastWindowClosed(False)
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(app_icon_pixmap(256)))
    window = ScreenshotWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

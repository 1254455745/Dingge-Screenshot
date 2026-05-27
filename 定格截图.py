from html import escape
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

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    from PySide6.QtCore import QByteArray, QPoint, QRect, QSettings, QSize, QTimer, Qt, QUrl, Signal
    from PySide6.QtGui import (
        QColor,
        QCursor,
        QDesktopServices,
        QFont,
        QIcon,
        QPainter,
        QPen,
        QPixmap,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractSpinBox,
        QButtonGroup,
        QDialog,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QAbstractScrollArea,
        QScrollArea,
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


SETTINGS_ORGANIZATION = "Anzhen"
SETTINGS_APPLICATION = "TimedScreenshotTool"
SETTINGS_LAYOUT_VERSION = 7
APP_DISPLAY_NAME = "定格截图"
APP_VERSION = "1.0"


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
GITHUB_URL = "https://github.com/1254455745/Dingge-Screenshot"
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

CAPTURE_TARGET_FULLSCREEN = 0
CAPTURE_TARGET_CUSTOM = 1
CAPTURE_TARGET_BROWSER = 2

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


def github_icon_pixmap(size: int) -> QPixmap:
    icon = QPixmap(size, size)
    icon.fill(QColor(0, 0, 0, 0))
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path fill="#1d1d1f" d="M12 .297C5.37.297 0 5.67 0 12.297c0 5.303 3.438 9.8 8.207 11.387.6.113.82-.258.82-.578 0-.285-.01-1.04-.016-2.04-3.338.727-4.043-1.608-4.043-1.608-.547-1.387-1.336-1.758-1.336-1.758-1.09-.746.083-.73.083-.73 1.205.086 1.84 1.238 1.84 1.238 1.07 1.835 2.808 1.305 3.492.997.108-.775.418-1.305.762-1.605-2.665-.303-5.466-1.333-5.466-5.93 0-1.31.467-2.38 1.235-3.22-.124-.303-.535-1.523.117-3.176 0 0 1.008-.322 3.3 1.23a11.48 11.48 0 0 1 3.005-.404c1.02.005 2.047.138 3.006.404 2.29-1.552 3.296-1.23 3.296-1.23.654 1.653.243 2.873.12 3.176.77.84 1.233 1.91 1.233 3.22 0 4.61-2.805 5.624-5.477 5.92.43.37.814 1.103.814 2.222 0 1.605-.015 2.898-.015 3.293 0 .322.216.697.825.58C20.565 22.092 24 17.597 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
    """
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(icon)
    renderer.render(painter)
    painter.end()
    return icon


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


class ScreenshotWindow(QMainWindow):
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
        self.running = False
        self.overlay: Optional[SelectionOverlay] = None
        self.preview_overlay: Optional[RegionPreviewOverlay] = None
        self.next_capture_at: Optional[datetime] = None
        self.restore_geometry: Optional[QRect] = None
        self.restore_window_state = None
        self.report_lock = threading.Lock()
        self.browser_capture_apps: list[tuple[str, str]] = []
        self.browser_capture_apps_ready = False
        self.capture_target = CAPTURE_TARGET_FULLSCREEN
        self.region_customized = False
        self.region = self.default_region()
        self.custom_region: Optional[CaptureRegion] = None
        self.daily_times: list[str] = []

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)

        self.build_ui()
        self.apply_styles()
        has_saved_times = self.settings.contains("daily/times")
        self.load_settings()
        if not has_saved_times:
            self.add_time(self.current_time_text(), silent=True)
        self.refresh_idle_note()
        QTimer.singleShot(0, self.reflow_dynamic_layouts)
        if self.system_name == "Darwin":
            QTimer.singleShot(400, self.warm_screen_recording_permission)
            QTimer.singleShot(600, self.warm_browser_capture_permissions)

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

        self.about_button = QPushButton("i")
        self.about_button.setObjectName("AboutButton")
        self.about_button.setFixedSize(32, 32)
        self.about_button.setToolTip("关于")
        self.about_button.clicked.connect(self.show_about)
        header.addWidget(self.about_button)
        root.addLayout(header)

        main = QHBoxLayout()
        main.setSpacing(18)
        root.addLayout(main, 1)

        settings = QFrame()
        settings.setObjectName("Panel")
        settings.setMinimumWidth(520)
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
        self.count_card = StatCard("已截图张数", "0")
        side_layout.addWidget(self.status_card)
        side_layout.addWidget(self.count_card)

        self.note_label = QLabel()
        self.note_label.setObjectName("NoteLabel")
        self.note_label.setWordWrap(True)
        side_layout.addWidget(self.note_label)
        side_layout.addStretch(1)

        self.start_button = self.make_button("开始截图", "primary")
        self.stop_button = self.make_button("停止截图", "danger")
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(self.stop_capture)
        self.stop_button.setEnabled(False)
        side_layout.addWidget(self.start_button)
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
            QPushButton#AboutButton {
                background: white;
                border: 1px solid #e2e2e7;
                border-radius: 16px;
                color: #6e6e73;
                font-size: 15px;
                font-weight: 700;
                max-height: 32px;
                max-width: 32px;
                min-height: 32px;
                min-width: 32px;
                padding: 0;
            }
            QPushButton#AboutButton:hover {
                background: #f8f8fa;
                color: #1d1d1f;
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

    def show_about(self):
        dialog = QDialog(self)
        dialog.setObjectName("AboutDialog")
        dialog.setWindowTitle(f"关于 {APP_DISPLAY_NAME}")
        dialog.setModal(True)
        dialog.setFixedWidth(600)
        if LOGO_PATH.exists():
            dialog.setWindowIcon(QIcon(app_icon_pixmap(256)))

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(14)

        logo_label = QLabel()
        logo_label.setObjectName("AboutLogo")
        logo_label.setFixedSize(88, 88)
        logo_label.setPixmap(logo_pixmap(88))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label, 0, Qt.AlignHCenter)

        title_label = QLabel(APP_DISPLAY_NAME)
        title_label.setObjectName("AboutTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 {APP_VERSION}")
        version_label.setObjectName("AboutVersion")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setFixedSize(76, 24)
        layout.addWidget(version_label, 0, Qt.AlignHCenter)

        author_label = QLabel(f"作者：{AUTHOR_NAME}")
        author_label.setObjectName("AboutAuthor")
        author_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(author_label)

        body_card = QFrame()
        body_card.setObjectName("AboutBodyCard")
        body_layout = QVBoxLayout(body_card)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(8)

        for text in (
            "轻量的定时截图小工具，用来按规则自动保存屏幕画面。",
            "支持间隔、分钟点和指定时间截图，也支持全屏和自定义区域。",
            f"单次运行最多保存 {MAX_CAPTURE_IMAGES_PER_RUN:,} 张截图，达到上限后会自动停止。",
            "macOS 首次控制浏览器时，需要在系统弹窗中允许本软件控制对应浏览器。",
            "关闭后会自动保留上次的设置。",
        ):
            body_line = QLabel(text)
            body_line.setObjectName("AboutBodyText")
            body_line.setWordWrap(False)
            body_layout.addWidget(body_line)
        layout.addWidget(body_card)

        github_button = QPushButton()
        github_button.setObjectName("AboutGithubButton")
        github_button.setFixedHeight(40)
        github_button.setCursor(QCursor(Qt.PointingHandCursor))
        github_button.clicked.connect(self.open_github)

        github_button_layout = QHBoxLayout(github_button)
        github_button_layout.setContentsMargins(0, 0, 0, 0)
        github_button_layout.setSpacing(7)
        github_button_layout.setAlignment(Qt.AlignCenter)

        github_icon = QLabel()
        github_icon.setObjectName("AboutGithubIcon")
        github_icon.setFixedSize(18, 18)
        github_icon.setPixmap(github_icon_pixmap(18))
        github_icon.setAlignment(Qt.AlignCenter)
        github_icon.setAttribute(Qt.WA_TransparentForMouseEvents)

        github_text = QLabel("GitHub 项目主页")
        github_text.setObjectName("AboutGithubText")
        github_text.setAlignment(Qt.AlignCenter)
        github_text.setAttribute(Qt.WA_TransparentForMouseEvents)

        github_button_layout.addWidget(github_icon)
        github_button_layout.addWidget(github_text)
        layout.addWidget(github_button)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.addStretch(1)
        ok_button = QPushButton("知道了")
        ok_button.setObjectName("AboutOkButton")
        ok_button.setFixedSize(96, 36)
        ok_button.clicked.connect(dialog.accept)
        button_row.addWidget(ok_button)
        layout.addLayout(button_row)

        dialog.setStyleSheet(
            """
            QDialog#AboutDialog {
                background: #f5f5f7;
                color: #1d1d1f;
                font-family: "PingFang SC", "SF Pro Text", sans-serif;
                font-size: 14px;
            }
            QLabel#AboutLogo {
                background: transparent;
                border: none;
            }
            QLabel#AboutTitle {
                color: #1d1d1f;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#AboutVersion {
                background: #eaeaef;
                border-radius: 12px;
                color: #6e6e73;
                font-size: 12px;
                font-weight: 600;
                padding: 0;
            }
            QLabel#AboutAuthor {
                color: #6e6e73;
                font-size: 13px;
                font-weight: 600;
            }
            QFrame#AboutBodyCard {
                background: white;
                border: 1px solid #e4e4e8;
                border-radius: 12px;
            }
            QLabel#AboutBodyText {
                background: transparent;
                border: none;
                color: #36363a;
                font-size: 13px;
                padding: 0;
            }
            QPushButton#AboutGithubButton {
                background: white;
                border: 1px solid #e2e2e7;
                border-radius: 10px;
                min-height: 38px;
                padding: 0;
            }
            QPushButton#AboutGithubButton:hover {
                background: #fbfbfc;
                border-color: #d2d2da;
            }
            QPushButton#AboutGithubButton:pressed {
                background: #eeeeF3;
            }
            QLabel#AboutGithubIcon {
                background: transparent;
                border: none;
            }
            QLabel#AboutGithubText {
                background: transparent;
                border: none;
                color: #1d1d1f;
                font-size: 13px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton#AboutOkButton {
                background: #0A84FF;
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: 700;
                min-height: 36px;
                min-width: 96px;
                padding: 0;
            }
            QPushButton#AboutOkButton:hover {
                background: #0070dd;
            }
            QPushButton#AboutOkButton:pressed {
                background: #0068cc;
            }
            """
        )
        dialog.exec()

    def open_github(self):
        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def current_time_text(self) -> str:
        return datetime.now().replace(second=0, microsecond=0).strftime("%H:%M")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "time_list_layout"):
            self.reflow_dynamic_layouts()

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
        self.save_settings()
        super().closeEvent(event)

    def refresh_path(self):
        self.path_value.setText(f"{self.save_dir}\n按日期自动保存到 {self.dated_save_dir().name}/")

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
        if self.running and self.next_capture_at is not None:
            self.note_label.setText(
                f"下一次截图\n{self.next_capture_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
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
        try:
            for index, tab in enumerate(tabs, start=1):
                if len(records) >= max_count:
                    break

                self.activate_browser_tab(tab)
                QApplication.processEvents()
                time.sleep(0.45)
                QApplication.processEvents()

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
            self.showNormal()
            self.raise_()
            self.activateWindow()

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

        self.hide()
        QApplication.processEvents()
        time.sleep(0.35)

        records: list[CaptureRecord] = []
        try:
            for window_index, (hwnd, browser_name, _title) in enumerate(browser_windows, start=1):
                if len(records) >= max_count:
                    break

                self.activate_windows_window(hwnd)
                time.sleep(WINDOWS_BROWSER_PAGE_DELAY_SECONDS)
                first_title = self.windows_window_title(hwnd)
                seen_titles: set[str] = set()

                for _ in range(WINDOWS_BROWSER_TAB_SAFETY_LIMIT):
                    if len(records) >= max_count:
                        break

                    current_title = self.windows_window_title(hwnd)
                    if current_title in seen_titles:
                        break

                    seen_titles.add(current_title)
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

                    if self.windows_window_title(hwnd) == first_title and len(seen_titles) > 0:
                        break
        finally:
            self.showNormal()
            self.raise_()
            self.activateWindow()

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

        self.dated_save_dir().mkdir(parents=True, exist_ok=True)
        self.running = True
        self.capture_count = 0
        self.count_card.set_value("0")
        self.status_card.set_value("等待执行")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.set_capture_options_locked(True)
        self.schedule_next_capture()

    def stop_capture(self):
        self.running = False
        self.next_capture_at = None
        self.timer.stop()
        self.status_card.set_value("已停止")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.set_capture_options_locked(False)
        self.refresh_idle_note()

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
        if not self.running:
            return

        self.status_card.set_value("正在截图")
        QApplication.processEvents()

        try:
            saved_count = self.save_screenshot()
        except Exception as exc:  # noqa: BLE001
            self.running = False
            self.timer.stop()
            self.next_capture_at = None
            self.status_card.set_value("运行失败")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.set_capture_options_locked(False)
            self.note_label.setText(f"截图失败：{exc}")
            QMessageBox.critical(
                self,
                "截图失败",
                f"截图时出现错误。\n\n{exc}",
            )
            return

        self.capture_count += max(0, saved_count)
        self.count_card.set_value(str(self.capture_count))
        if self.capture_count >= MAX_CAPTURE_IMAGES_PER_RUN:
            self.running = False
            self.timer.stop()
            self.next_capture_at = None
            self.status_card.set_value("已完成")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.set_capture_options_locked(False)
            self.note_label.setText(f"已达到单次 {MAX_CAPTURE_IMAGES_PER_RUN:,} 张上限，截图已自动停止")
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
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(app_icon_pixmap(256)))
    window = ScreenshotWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

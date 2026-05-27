import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    from PySide6.QtCore import QPoint, QRect, QSettings, QSize, QTimer, Qt, Signal
    from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractSpinBox,
        QButtonGroup,
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
except ImportError:
    applescript = (
        'display dialog "缺少界面依赖 PySide6_Essentials。'
        '\\n\\n请先运行：python3 -m pip install --user PySide6_Essentials" '
        'buttons {"知道了"} default button "知道了" with title "定格截图"'
    )
    subprocess.run(["osascript", "-e", applescript], check=False)
    raise SystemExit("Missing PySide6_Essentials")


SETTINGS_ORGANIZATION = "Anzhen"
SETTINGS_APPLICATION = "TimedScreenshotTool"
SETTINGS_LAYOUT_VERSION = 7
APP_DISPLAY_NAME = "定格截图"
APP_VERSION = "1.0"

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


@dataclass
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int


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
        self.draw_background(painter)
        painter.fillRect(self.rect(), QColor(8, 12, 20, 118))

        rect = QRect(self.origin, self.current).normalized()
        if self.dragging and not rect.isNull():
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
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self.system_name = platform.system()
        self.save_dir = Path.cwd() / "screenshots"
        self.capture_count = 0
        self.running = False
        self.overlay: Optional[SelectionOverlay] = None
        self.next_capture_at: Optional[datetime] = None
        self.restore_geometry: Optional[QRect] = None
        self.restore_window_state = None
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
        header.setSpacing(12)

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("WindowTitle")
        header.addWidget(title)
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

        choose_btn = self.make_button("选择", "secondary")
        choose_btn.setFixedWidth(86)
        choose_btn.clicked.connect(self.choose_directory)

        layout.addWidget(self.path_value, 1, 0)
        layout.addWidget(choose_btn, 1, 1)
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
        self.daily_time = QTimeEdit()
        self.daily_time.setDisplayFormat("HH:mm")
        self.daily_time.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.daily_time.setFixedWidth(130)
        self.daily_time.setFixedHeight(42)
        self.daily_time.setTime(datetime.now().replace(second=0, microsecond=0).time())
        self.daily_time.lineEdit().returnPressed.connect(
            lambda: self.add_time(self.daily_time.time().toString("HH:mm"))
        )
        add_btn = self.make_button("添加时间点", "secondary")
        add_btn.setFixedWidth(120)
        add_btn.setFixedHeight(42)
        add_btn.clicked.connect(lambda: self.add_time(self.daily_time.time().toString("HH:mm")))
        add_row.addWidget(self.daily_time)
        add_row.addWidget(add_btn)
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

    def build_region_section(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        region_label = self.make_label("截图区域")
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
        for button in (self.fullscreen_region_button, self.custom_region_button):
            button.setCheckable(True)
            button.setObjectName("SegmentButton")
            segment_layout.addWidget(button)

        self.fullscreen_region_button.setChecked(True)
        self.region_group = QButtonGroup(self)
        self.region_group.setExclusive(True)
        self.region_group.addButton(self.fullscreen_region_button, 0)
        self.region_group.addButton(self.custom_region_button, 1)
        self.fullscreen_region_button.clicked.connect(self.use_fullscreen_region)
        self.custom_region_button.clicked.connect(self.use_custom_region)
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
                font-size: 28px;
                font-weight: 700;
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
            QPushButton#RegionReselectButton {
                background: #f1f1f4;
                border: 1px solid #ddddE3;
                border-radius: 10px;
                color: #4b4b51;
                font-weight: 700;
                padding: 0 8px;
            }
            QPushButton#RegionReselectButton:hover {
                background: #eaeaee;
            }
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
        QMessageBox.information(
            self,
            f"关于 {APP_DISPLAY_NAME}",
            (
                f"{APP_DISPLAY_NAME}\n"
                f"版本 {APP_VERSION}\n\n"
                "一个轻量的定时截图小工具。\n"
                "支持间隔截图、分钟点截图、指定时间截图，以及全屏/选区截图。\n"
                "关闭后会自动保留上次的设置。"
            ),
        )

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

        self.region_customized = active_custom and self.custom_region is not None
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
        self.path_value.setText(str(self.save_dir))

    def refresh_region(self):
        if self.region_customized:
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
        chosen = QFileDialog.getExistingDirectory(self, "选择保存位置", str(self.save_dir))
        if chosen:
            self.save_dir = Path(chosen)
            self.refresh_path()
            self.refresh_idle_note()

    def set_mode(self, index: int):
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
        if value not in self.daily_times:
            self.daily_times.append(value)
            self.daily_times.sort()
            self.render_time_chips()
        if not silent:
            self.refresh_idle_note()

    def remove_time(self, value: str):
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
        self.region = self.default_region()
        self.region_customized = False
        self.sync_region_buttons()
        self.refresh_region()

    def use_custom_region(self):
        if self.custom_region is None:
            self.select_region()
            return

        self.region = self.custom_region
        self.region_customized = True
        self.sync_region_buttons()
        self.refresh_region()

    def select_region(self):
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
        background = screen.grabWindow(0)
        if background.isNull():
            self.restore_main_window()
            self.sync_region_buttons()
            QMessageBox.warning(self, "无法选择", "没有成功读取当前屏幕画面，请检查系统截图权限。")
            return

        self.overlay = SelectionOverlay(screen, background)
        self.overlay.selection_made.connect(self.on_region_selected)
        self.overlay.selection_cancelled.connect(self.on_region_cancelled)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def on_region_selected(self, region: CaptureRegion):
        self.custom_region = region
        self.region = region
        self.region_customized = True
        self.sync_region_buttons()
        self.refresh_region()
        self.restore_main_window()

    def on_region_cancelled(self):
        self.sync_region_buttons()
        self.restore_main_window()

    def sync_region_buttons(self):
        self.fullscreen_region_button.setChecked(not self.region_customized)
        self.custom_region_button.setChecked(self.region_customized)
        self.reselect_region_button.setVisible(self.region_customized)
        self.reselect_region_button.setEnabled(self.custom_region is not None)

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

    def start_capture(self):
        if self.running:
            QMessageBox.information(self, "正在运行", "截图任务已经开始了。")
            return

        if self.mode_group.checkedId() == 2 and not self.daily_times:
            QMessageBox.warning(self, "缺少时间点", "请先添加至少一个截图时间点。")
            return

        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.capture_count = 0
        self.count_card.set_value("0")
        self.status_card.set_value("等待执行")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.schedule_next_capture()

    def stop_capture(self):
        self.running = False
        self.next_capture_at = None
        self.timer.stop()
        self.status_card.set_value("已停止")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
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
            self.save_screenshot()
        except Exception as exc:  # noqa: BLE001
            self.running = False
            self.timer.stop()
            self.next_capture_at = None
            self.status_card.set_value("运行失败")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.note_label.setText(f"截图失败：{exc}")
            QMessageBox.critical(
                self,
                "截图失败",
                "截图时出现错误。\n\n如果你是 macOS，请确认已经给启动器开启“屏幕录制”权限。",
            )
            return

        self.capture_count += 1
        self.count_card.set_value(str(self.capture_count))
        self.schedule_next_capture()

    def save_screenshot(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.save_dir / f"screenshot_{timestamp}.png"

        if self.system_name == "Darwin":
            region = f"{self.region.x},{self.region.y},{self.region.width},{self.region.height}"
            subprocess.run(["screencapture", "-x", f"-R{region}", str(filepath)], check=True)
            return

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


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(SETTINGS_ORGANIZATION)
    app.setApplicationName(APP_DISPLAY_NAME)
    window = ScreenshotWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

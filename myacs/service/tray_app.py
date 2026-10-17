"""
MyAcs — Windows Desktop Window & System Tray Management
Provides a native PySide6 Control Dashboard, native system tray icon,
minimize-to-tray, close-to-tray, and direct browser viewer launcher.
"""

import os
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction, QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QFrame,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QScrollArea
)

from myacs.core.device_identity import config
from myacs.core.security import session_manager
from myacs.core.discovery import get_all_lan_ips
from myacs.service.autostart import is_windows_autostart_enabled, set_windows_autostart

ASSETS_DIR = Path(__file__).resolve().parent.parent / "ui" / "static" / "assets"
ICON_PATH = ASSETS_DIR / "icon.png"

# Modern Dark Theme Stylesheet (QSS)
DARK_QSS = """
QMainWindow, QWidget {
    background-color: #090d16;
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
QFrame.card {
    background-color: rgba(17, 24, 39, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px;
}
QLabel.title {
    font-size: 17px;
    font-weight: 700;
    color: #ffffff;
}
QLabel.subtitle {
    font-size: 12px;
    color: #94a3b8;
}
QLabel.badge {
    background-color: rgba(6, 182, 212, 0.15);
    color: #06b6d4;
    border: 1px solid rgba(6, 182, 212, 0.3);
    border-radius: 6px;
    padding: 4px 8px;
    font-weight: 600;
    font-size: 11px;
}
QLabel.device-id {
    font-family: ui-monospace, Consolas, monospace;
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 2px;
}
QLineEdit {
    background-color: rgba(0, 0, 0, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    padding: 8px 12px;
    color: #ffffff;
    font-size: 14px;
}
QLineEdit:focus {
    border: 1px solid #6366f1;
}
QPushButton {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    padding: 8px 16px;
}
QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.15);
    border-color: rgba(255, 255, 255, 0.25);
}
QPushButton.primary {
    background-color: #4f46e5;
    border: none;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}
QPushButton.primary:hover {
    background-color: #4338ca;
}
QPushButton.danger {
    background-color: rgba(239, 68, 68, 0.2);
    border: 1px solid rgba(239, 68, 68, 0.4);
    color: #ef4444;
}
QPushButton.danger:hover {
    background-color: #ef4444;
    color: #ffffff;
}
QCheckBox {
    font-size: 13px;
    color: #e2e8f0;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background-color: rgba(0, 0, 0, 0.3);
}
QCheckBox::indicator:checked {
    background-color: #6366f1;
    border-color: #6366f1;
}
"""


class MyAcsMainWindow(QMainWindow):
    """Native Windows Control Dashboard for MyAcs."""

    def __init__(self, port: int = 45821):
        super().__init__()
        self.port = port
        self.server_url = f"http://127.0.0.1:{self.port}"
        
        self.setWindowTitle("MyAcs — Local Network Screen Mirroring (View-Only)")
        self.setMinimumSize(780, 640)
        self.resize(840, 700)
        
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.setStyleSheet(DARK_QSS)
        self._init_ui()
        
        # Periodic status refresh timer (every 2.5s)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_status)
        self.refresh_timer.start(2500)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header Section
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        
        title_label = QLabel("MyAcs Screen Mirroring")
        title_label.setProperty("class", "title")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        
        sub_label = QLabel("Secure, low-latency, view-only LAN screen sharing")
        sub_label.setProperty("class", "subtitle")
        
        header_text_layout.addWidget(title_label)
        header_text_layout.addWidget(sub_label)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()

        self.lan_status_badge = QLabel("● Active on LAN")
        self.lan_status_badge.setProperty("class", "badge")
        header_layout.addWidget(self.lan_status_badge)
        main_layout.addLayout(header_layout)

        # ---------------------------------------------------------
        # Card 1: Permanent Device Identity
        # ---------------------------------------------------------
        card_id = QFrame()
        card_id.setProperty("class", "card")
        card_id_layout = QVBoxLayout(card_id)
        
        id_header = QHBoxLayout()
        id_title = QLabel("Permanent Device ID (Machine Bound)")
        id_title.setStyleSheet("font-weight: 700; color: #06b6d4; font-size: 12px; text-transform: uppercase;")
        id_header.addWidget(id_title)
        id_header.addStretch()
        card_id_layout.addLayout(id_header)

        id_row = QHBoxLayout()
        self.device_id_label = QLabel(config.get("device_id", "ACS-....-...."))
        self.device_id_label.setProperty("class", "device-id")
        id_row.addWidget(self.device_id_label)
        id_row.addStretch()

        self.btn_copy_id = QPushButton("Copy Device ID")
        self.btn_copy_id.clicked.connect(self._copy_device_id)
        id_row.addWidget(self.btn_copy_id)
        card_id_layout.addLayout(id_row)

        primary_ip = (get_all_lan_ips() or ["127.0.0.1"])[0]
        self.ip_info_label = QLabel(f"Computer: {config.get('device_name')}  •  Local IP: {primary_ip}:{self.port}")
        self.ip_info_label.setStyleSheet("color: #94a3b8; font-size: 12px; margin-top: 4px;")
        card_id_layout.addWidget(self.ip_info_label)

        main_layout.addWidget(card_id)

        # ---------------------------------------------------------
        # Card 2: Security & PIN Configuration
        # ---------------------------------------------------------
        card_sec = QFrame()
        card_sec.setProperty("class", "card")
        card_sec_layout = QVBoxLayout(card_sec)
        
        sec_title = QLabel("Security PIN & Protection")
        sec_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #ffffff;")
        card_sec_layout.addWidget(sec_title)

        sec_sub = QLabel("Remote viewers must enter this PIN to connect. Device IDs do not act as the sole credential.")
        sec_sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        card_sec_layout.addWidget(sec_sub)

        pin_row = QHBoxLayout()
        self.pin_input = QLineEdit()
        self.pin_input.setText(str(config.get("security_pin", "123456")))
        self.pin_input.setMaximumWidth(160)
        self.pin_input.setAlignment(Qt.AlignCenter)
        self.pin_input.setFont(QFont("Consolas", 14, QFont.Bold))
        pin_row.addWidget(self.pin_input)

        self.btn_save_pin = QPushButton("Save PIN")
        self.btn_save_pin.clicked.connect(self._save_pin)
        pin_row.addWidget(self.btn_save_pin)

        self.btn_regen_pin = QPushButton("Generate New PIN")
        self.btn_regen_pin.clicked.connect(self._generate_random_pin)
        pin_row.addWidget(self.btn_regen_pin)

        pin_row.addStretch()
        card_sec_layout.addLayout(pin_row)

        view_only_note = QLabel("🔒 View-Only Mode Enforced: Remote mouse and keyboard inputs are strictly disabled.")
        view_only_note.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px; margin-top: 4px;")
        card_sec_layout.addWidget(view_only_note)

        main_layout.addWidget(card_sec)

        # ---------------------------------------------------------
        # Card 3: Windows Background & Autostart
        # ---------------------------------------------------------
        card_bg = QFrame()
        card_bg.setProperty("class", "card")
        card_bg_layout = QVBoxLayout(card_bg)

        bg_header = QHBoxLayout()
        self.chk_autostart = QCheckBox("Start automatically with Windows (Background Service)")
        self.chk_autostart.setChecked(is_windows_autostart_enabled())
        self.chk_autostart.toggled.connect(self._toggle_autostart)
        bg_header.addWidget(self.chk_autostart)
        bg_header.addStretch()
        card_bg_layout.addLayout(bg_header)

        bg_desc = QLabel("MyAcs will run silently in the Windows System Tray at startup. Closing this window keeps sharing available 24/7.")
        bg_desc.setStyleSheet("color: #94a3b8; font-size: 12px; margin-top: 4px;")
        card_bg_layout.addWidget(bg_desc)

        main_layout.addWidget(card_bg)

        # ---------------------------------------------------------
        # Action Bar: Launch Web Viewer & Configure Firewall
        # ---------------------------------------------------------
        action_layout = QHBoxLayout()
        
        self.btn_open_web = QPushButton("Open Live Web Viewer (Browser)")
        self.btn_open_web.setProperty("class", "primary")
        self.btn_open_web.clicked.connect(self._open_web_viewer)
        action_layout.addWidget(self.btn_open_web)

        self.btn_firewall = QPushButton("Allow Windows Firewall")
        self.btn_firewall.clicked.connect(self._run_firewall_setup)
        action_layout.addWidget(self.btn_firewall)

        action_layout.addStretch()

        self.viewers_count_label = QLabel("Connected Viewers: 0")
        self.viewers_count_label.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 12px;")
        action_layout.addWidget(self.viewers_count_label)

        main_layout.addLayout(action_layout)

    def _copy_device_id(self):
        dev_id = config.get("device_id")
        QApplication.clipboard().setText(dev_id)
        self.btn_copy_id.setText("Copied!")
        QTimer.singleShot(1800, lambda: self.btn_copy_id.setText("Copy Device ID"))

    def _save_pin(self):
        new_pin = self.pin_input.text().strip()
        if len(new_pin) < 4:
            QMessageBox.warning(self, "Invalid PIN", "PIN must be at least 4 digits.")
            return
        config.set_security_pin(new_pin)
        self.btn_save_pin.setText("Saved!")
        QTimer.singleShot(1800, lambda: self.btn_save_pin.setText("Save PIN"))

    def _generate_random_pin(self):
        import secrets
        new_pin = f"{secrets.randbelow(900000) + 100000}"
        self.pin_input.setText(new_pin)
        config.set_security_pin(new_pin)

    def _toggle_autostart(self, checked: bool):
        set_windows_autostart(checked)
        config.set("autostart", checked)

    def _open_web_viewer(self):
        webbrowser.open(self.server_url)

    def _run_firewall_setup(self):
        bat_path = Path(__file__).resolve().parent.parent.parent / "add_firewall_rule.bat"
        if bat_path.exists():
            os.startfile(str(bat_path))
        else:
            QMessageBox.information(self, "Firewall", "Please run add_firewall_rule.bat as Administrator.")

    def _refresh_status(self):
        """Updates viewer count and LAN status periodically."""
        active = session_manager.get_active_sessions_summary()
        count = len(active)
        self.viewers_count_label.setText(f"Connected Viewers: {count}")
        if count > 0:
            self.lan_status_badge.setText(f"● Streaming to {count} viewer{'s' if count > 1 else ''}")
            self.lan_status_badge.setStyleSheet("background-color: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4);")
        else:
            self.lan_status_badge.setText("● Active on LAN")
            self.lan_status_badge.setStyleSheet("background-color: rgba(6, 182, 212, 0.15); color: #06b6d4; border: 1px solid rgba(6, 182, 212, 0.3);")

    def closeEvent(self, event):
        """
        CRITICAL REQUIREMENT #4 & #5:
        Closing window minimizes silently to system tray.
        """
        event.ignore()
        self.hide()
        if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "MyAcs Active in Background",
                "Screen mirroring is active. Your PC remains available on the local network.",
                QSystemTrayIcon.Information,
                2000
            )


class MyAcsTrayManager:
    """Manages the Windows System Tray lifecycle and menu."""

    def __init__(self, main_window: MyAcsMainWindow, app: QApplication):
        self.window = main_window
        self.app = app
        self.tray = QSystemTrayIcon()
        
        if ICON_PATH.exists():
            self.tray.setIcon(QIcon(str(ICON_PATH)))
        else:
            self.tray.setIcon(self.window.windowIcon())

        self.tray.setToolTip(f"MyAcs — {config.get('device_id')} (Active on LAN)")
        self.window.tray_icon = self.tray

        self._build_context_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_context_menu(self):
        menu = QMenu()

        dev_id = config.get("device_id")
        id_action = QAction(f"ID: {dev_id}", menu)
        id_action.setEnabled(False)
        menu.addAction(id_action)

        menu.addSeparator()

        open_action = QAction("Open Dashboard", menu)
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)

        browser_action = QAction("Open Web Viewer in Browser", menu)
        browser_action.triggered.connect(lambda: webbrowser.open(f"http://127.0.0.1:{self.window.port}"))
        menu.addAction(browser_action)

        copy_action = QAction("Copy Device ID", menu)
        copy_action.triggered.connect(self._copy_id_to_clipboard)
        menu.addAction(copy_action)

        menu.addSeparator()

        self.autostart_action = QAction("Start with Windows", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_windows_autostart_enabled())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        exit_action = QAction("Exit MyAcs", menu)
        exit_action.triggered.connect(self._exit_application)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.toggle_window()

    def show_window(self):
        self.window.showNormal()
        self.window.activateWindow()

    def toggle_window(self):
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.show_window()

    def _copy_id_to_clipboard(self):
        dev_id = config.get("device_id")
        QApplication.clipboard().setText(dev_id)
        self.tray.showMessage(
            "Device ID Copied",
            f"{dev_id} has been copied to your clipboard.",
            QSystemTrayIcon.Information,
            2000
        )

    def _toggle_autostart(self):
        enable = self.autostart_action.isChecked()
        set_windows_autostart(enable)
        config.set("autostart", enable)

    def _exit_application(self):
        reply = QMessageBox.question(
            self.window,
            "Exit MyAcs?",
            "Exiting will stop screen mirroring and make this PC unavailable on the local network.\n\nAre you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.tray.hide()
            self.app.quit()

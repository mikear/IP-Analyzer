import sys
import os
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent, QAction, QColor, QIcon, QPixmap, QPainter, QColor as QCol
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QSplitter, QGroupBox, QDialog, QFileDialog,
    QMessageBox, QFrame, QStatusBar, QAbstractItemView
)

# Ensure src dir in path
script_dir = Path(__file__).parent.resolve()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

import config
import api_clients
import file_io
import processing

logger = logging.getLogger(__name__)


def _make_icon(svg_path_data: str, color: str = "#3B82F6", size: int = 24) -> QIcon:
    """Create a QIcon from an SVG path string."""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}">
      <path fill="{color}" d="{svg_path_data}"/>
    </svg>'''
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode('utf-8'))
    return QIcon(pixmap)


class _Icons:
    """Lazy icon loader - creates icons on first access."""
    _cache = {}

    @staticmethod
    def _get(key, svg, color):
        if key not in _Icons._cache:
            _Icons._cache[key] = _make_icon(svg, color)
        return _Icons._cache[key]

    @staticmethod
    def eye(): return _Icons._get('eye', 'M256 32C132.3 32 32 132.3 32 256s100.3 224 224 224 224-100.3 224-224S379.7 32 256 32zm0 384c-88.4 0-160-71.6-160-160S167.6 96 256 96s160 71.6 160 160-71.6 160-160 160zm0-256c-53 0-96 43-96 96s43 96 96 96 96-43 96-96-43-96-96-96z', '#475569')
    @staticmethod
    def eye_slash(): return _Icons._get('eye_slash', 'M256 32C132.3 32 32 132.3 32 256s100.3 224 224 224 224-100.3 224-224S379.7 32 256 32zm0 384c-88.4 0-160-71.6-160-160S167.6 96 256 96s160 71.6 160 160-71.6 160-160 160zm0-256c-53 0-96 43-96 96s43 96 96 96 96-43 96-96-43-96-96-96z', '#475569')
    @staticmethod
    def plug(): return _Icons._get('plug', 'M352 32H160c-17.7 0-32 14.3-32 32v64h128V96h96v256h-32V192h-96v64H160v-64c0-17.7 14.3-32 32-32h160c17.7 0 32 14.3 32 32v224c0 17.7-14.3 32-32 32H160c-17.7 0-32-14.3-32-32V352H64c-17.7 0-32-14.3-32-32V64C32 46.3 46.3 32 64 32h288c17.7 0 32 14.3 32 32v224c0 17.7-14.3 32-32 32h-32v64h32c35.3 0 64-28.7 64-64V64c0-17.7-14.3-32-32-32z', '#475569')
    @staticmethod
    def save(): return _Icons._get('save', 'M288 32H192c-17.7 0-32 14.3-32 32v64H96c-17.7 0-32 14.3-32 32v288c0 17.7 14.3 32 32 32h288c17.7 0 32-14.3 32-32V128c0-17.7-14.3-32-32-32h-32V64c0-17.7-14.3-32-32-32zm-32 0v64h96V64h-96zM192 384V224h128v160H192z', '#FFFFFF')
    @staticmethod
    def folder_open(): return _Icons._get('folder_open', 'M448 480H192c-17.7 0-32-14.3-32-32V164.6c0-9.7 5.5-18.4 14.1-22.7l128-64c7.8-3.9 17.2-1.5 21.6 5.1L448 160v320c0 17.7-14.3 32-32 32zM64 480H32c-17.7 0-32-14.3-32-32V160c0-17.7 14.3-32 32-32h32l48-32h160l48 32h32c17.7 0 32 14.3 32 32v32H64v288z', '#3B82F6')
    @staticmethod
    def file(): return _Icons._get('file', 'M320 448v40c0 13.3-10.7 24-24 24H72c-13.3 0-24-10.7-24-24V120c0-13.3 10.7-24 24-24h224v40c0 26.5 21.5 48 48 48h40zM256 0C119 0 8 111 8 248v224c0 13.3 10.7 24 24 24h32c13.3 0 24-10.7 24-24V248c0-97 79-176 176-176h32V0L256 0zm240 320h-32c-44.2 0-80 35.8-80 80v32c0 13.3 10.7 24 24 24h72c13.3 0 24-10.7 24-24v-32c0-8.8-7.2-16-16-16z', '#3B82F6')
    @staticmethod
    def globe(): return _Icons._get('globe', 'M256 0C114.6 0 0 114.6 0 256s114.6 256 256 256 256-114.6 256-256S391.4 0 256 0zm164.5 388.5c-15 15-35.4 23.5-56.5 23.5h-21.6c-2.8-18.5-11.3-35.8-24.2-49.3l10.5-10.5c6.2-6.2 6.2-16.4 0-22.6l-22.6-22.6c-6.2-6.2-16.4-6.2-22.6 0l-14.9 14.9c-16.8-8-35-11.5-53.5-11.5h-5.8c-27 0-52.6 10.5-71.8 29.7L133.3 231c-6.2-6.2-16.4-6.2-22.6 0L88.1 253.6c-6.2 6.2-6.2 16.4 0 22.6l25.7 25.7c-8 16.8-11.5 35-11.5 53.5v5.8c0 27 10.5 52.6 29.7 71.8l-17.2 17.2c-6.2 6.2-6.2 16.4 0 22.6l22.6 22.6c6.2 6.2 16.4 6.2 22.6 0l17.2-17.2c19.2 19.2 44.8 29.7 71.8 29.7h5.8c18.5 0 36.7-3.5 53.5-11.5l-14.9 14.9c-6.2 6.2-6.2 16.4 0 22.6l22.6 22.6c6.2 6.2 16.4 6.2 22.6 0l25.7-25.7c6.2-6.2 6.2-16.4 0-22.6l-17.2-17.2c19.2-19.2 29.7-44.8 29.7-71.8v-5.8c0-21.1-8.5-41.5-23.5-56.5l-10.5 10.5c-13.5 13.5-30.8 22-49.3 24.2V256c0-8.8-7.2-16-16-16s-16 7.2-16 16v42.3c-18.5-2.2-35.8-10.7-49.3-24.2l-10.5 10.5c-15 15-35.4 23.5-56.5 23.5h-21.6c-2.8-18.5-11.3-35.8-24.2-49.3l10.5-10.5c6.2-6.2 6.2-16.4 0-22.6l-22.6-22.6c-6.2-6.2-16.4-6.2-22.6 0l-14.9 14.9c-16.8-8-35-11.5-53.5-11.5h-5.8c-27 0-52.6 10.5-71.8 29.7L79 231c-6.2-6.2-16.4-6.2-22.6 0L33.8 253.6c-6.2 6.2-6.2 16.4 0 22.6l25.7 25.7c-8 16.8-11.5 35-11.5 53.5v5.8c0 27 10.5 52.6 29.7 71.8L60 447.6c-6.2 6.2-6.2 16.4 0 22.6l22.6 22.6c6.2 6.2 16.4 6.2 22.6 0l17.2-17.2c19.2 19.2 44.8 29.7 71.8 29.7h5.8c18.5 0 36.7-3.5 53.5-11.5l14.9 14.9c6.2 6.2 16.4 6.2 22.6 0l22.6-22.6c6.2-6.2 6.2-16.4 0-22.6L300.5 471c19.2-19.2 29.7-44.8 29.7-71.8v-5.8c0-21.1-8.5-41.5-23.5-56.5z', '#3B82F6')
    @staticmethod
    def building(): return _Icons._get('building', 'M432 32H80C44.7 32 16 60.7 16 96v320c0 35.3 28.7 64 64 64h32c17.7 0 32-14.3 32-32V288h128v160c0 17.7 14.3 32 32 32h32c35.3 0 64-28.7 64-64V96c0-35.3-28.7-64-64-64zm0 352H80V96h352v288zM160 176h64v64h-64v-64zm96 0h64v64h-64v-64zm-96 96h64v64h-64v-64zm96 0h64v64h-64v-64z', '#3B82F6')
    @staticmethod
    def lock(): return _Icons._get('lock', 'M400 224h-24v-72C376 68.2 307.8 0 224 0S72 68.2 72 152v72H48c-26.5 0-48 21.5-48 48v192c0 26.5 21.5 48 48 48h352c26.5 0 48-21.5 48-48V272c0-26.5-21.5-48-48-48zm-24-72c0-48.6 39.4-88 88-88s88 39.4 88 88v72H376v-72z', '#3B82F6')
    @staticmethod
    def key(): return _Icons._get('key', 'M500.3 441.7l-99.8-99.8c36.3-57.5 57.9-128 57.9-204.1C458.4 76.7 381.7 0 288.2 0 194.6 0 118 76.7 118 170.7c0 76.1 21.6 146.6 57.9 204.1l-99.8 99.8C64.6 493.4 52.5 512 73.6 512h345.5c21.2 0 33.3-18.6 11.2-40.3zM288.2 80c50.6 0 91.6 41 91.6 91.6 0 36-21.1 67.4-51.6 82.1-13.3-25.6-37.2-45.4-65.4-50.8V80h25.4zm-25.4 86.4c-28.2 5.4-52.1 25.2-65.4 50.8-30.5-14.7-51.6-46.1-51.6-82.1 0-50.6 41-91.6 91.6-91.6v122.9h25.4z', '#475569')
    @staticmethod
    def play(): return _Icons._get('play', 'M448 256c0 119.4-96.6 216-216 216S16 375.4 16 256 112.6 40 232 40s216 96.6 216 216zm-48 0l-176-112v224l176-112z', '#FFFFFF')
    @staticmethod
    def trash(): return _Icons._get('trash', 'M320 64h-80c0-35.3-28.7-64-64-64s-64 28.7-64 64H48C21.5 64 0 85.5 0 112v32c0 17.7 14.3 32 32 32h16l48 320h256l48-320h16c17.7 0 32-14.3 32-32v-32c0-26.5-21.5-48-48-48zM160 64c0-17.7 14.3-32 32-32s32 14.3 32 32H160zm176 368H80L48 144V112c0-8.8 7.2-16 16-16h288c8.8 0 16 7.2 16 16v32l-32 256z', '#475569')
    @staticmethod
    def clipboard(): return _Icons._get('clipboard', 'M448 32H336c-17.7 0-32 14.3-32 32v48H272V96c0-17.7-14.3-32-32-32h-80c-17.7 0-32 14.3-32 32v16H64c-17.7 0-32 14.3-32 32v352c0 17.7 14.3 32 32 32h384c17.7 0 32-14.3 32-32V64c0-17.7-14.3-32-32-32zM160 64h192v48H160V64zm224 416H64V128h48v64c0 8.8 7.2 16 16 16h256c8.8 0 16-7.2 16-16v-64h48v352zM160 240h224v32H160v-32zm0 80h160v32H160v-32z', '#475569')
    @staticmethod
    def sync(): return _Icons._get('sync', 'M448 32H288l-32 32H64C28.7 64 0 92.7 0 128v256c0 35.3 28.7 64 64 64h139l-32 32v24c0 13.3 10.7 24 24 24h192c13.3 0 24-10.7 24-24V392l-32-32h136c35.3 0 64-28.7 64-64V128c0-35.3-28.7-64-64-64zM256 368c-61.9 0-112-50.1-112-112s50.1-112 112-112c33.1 0 62.4 14.4 83 37 8.1 9 23.3 8.6 30.9-.9l20.5-26c8.2-10.6 6.5-25.5-4-33.4C373.5 71.8 317.4 48 256 48 132.3 48 32 148.3 32 272s100.3 224 224 224 224-100.3 224-224h-32c0 53-43 96-96 96s-96-43-96-96 43-96 96-96c17.6 0 33.8 4.8 47.8 13.1L256 272v96z', '#475569')
    @staticmethod
    def times(): return _Icons._get('times', 'M352 96L288 32 176 144 64 32 0 96l112 112L0 320l64 64 112-112 112 112 64-64-112-112L352 96z', '#475569')
    @staticmethod
    def info(): return _Icons._get('info', 'M256 0C114.6 0 0 114.6 0 256s114.6 256 256 256 256-114.6 256-256S391.4 0 256 0zm0 480c-123.7 0-224-100.3-224-224S132.3 32 256 32s224 100.3 224 224-100.3 224-224 224zm32-224c0-17.7-14.3-32-32-32H224c-17.7 0-32 14.3-32 32v128c0 17.7 14.3 32 32 32h32c17.7 0 32-14.3 32-32V256zm-48-96c17.7 0 32-14.3 32-32s-14.3-32-32-32-32 14.3-32 32 14.3 32 32 32z', '#475569')
    @staticmethod
    def file_export(): return _Icons._get('file_export', 'M320 448v40c0 13.3-10.7 24-24 24H72c-13.3 0-24-10.7-24-24V120c0-13.3 10.7-24 24-24h224v40c0 26.5 21.5 48 48 48h40zM256 0C119 0 8 111 8 248v224c0 13.3 10.7 24 24 24h32c13.3 0 24-10.7 24-24V248c0-97 79-176 176-176h32V0L256 0zm240 320h-32c-44.2 0-80 35.8-80 80v32c0 13.3 10.7 24 24 24h72c13.3 0 24-10.7 24-24v-32c0-8.8-7.2-16-16-16z', '#475569')


class QtLogHandler(logging.Handler):
    def __init__(self, signal: Signal):
        super().__init__()
        self.signal = signal

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self.signal.emit(msg, record.levelname)


class AnalysisWorker(QObject):
    progress_updated = Signal(dict)
    log_emitted = Signal(str, str)
    finished = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, filepath: Path, target_tz: str, ipinfo_token: str, file_hash: str, app_version: str):
        super().__init__()
        self.filepath = filepath
        self.target_tz = target_tz
        self.ipinfo_token = ipinfo_token
        self.file_hash = file_hash
        self.app_version = app_version

    def run(self):
        handler = QtLogHandler(self.log_emitted)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S'))

        class QtProgressQueue:
            def __init__(self, signal):
                self.signal = signal
            def put_nowait(self, data):
                self.signal.emit(data)

        progress_q = QtProgressQueue(self.progress_updated)

        try:
            results = processing.process_ip_analysis(
                input_filepath=self.filepath,
                target_timezone=self.target_tz,
                ipinfo_token=self.ipinfo_token,
                progress_queue=progress_q,
                log_queue_handler=handler,
                input_file_hash=self.file_hash,
                app_version=self.app_version
            )
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"Error en worker de analisis: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.finished.emit(None)


class ApiTokenDialog(QDialog):
    def __init__(self, parent=None, current_token: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Configuracion de Token IPInfo API")
        self.setMinimumWidth(500)
        self.setModal(True)
        self.token = current_token

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title_lbl = QLabel("Enriquecimiento de Geolocalizacion e ISP")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F172A;")
        layout.addWidget(title_lbl)

        info_lbl = QLabel(
            "Ingrese su token de API de <b>ipinfo.io</b> para obtener la geolocalizacion, "
            "proveedor ISP y hostname de cada direccion IP consultada.<br><br>"
            "<i>Nota: Si no cuenta con token, el analisis se ejecutara en modo 100% local extrayendo IPs y timestamps.</i>"
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #475569; font-size: 12px; line-height: 1.4;")
        layout.addWidget(info_lbl)

        form_card = QFrame()
        form_card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        form_layout = QVBoxLayout(form_card)

        token_box = QHBoxLayout()
        self.token_entry = QLineEdit(current_token)
        self.token_entry.setEchoMode(QLineEdit.Password)
        self.token_entry.setPlaceholderText("Ej. 1a2b3c4d5e6f7g")
        self.token_entry.setMinimumHeight(34)
        token_box.addWidget(self.token_entry)

        self.show_cb = QPushButton(" Mostrar")
        self.show_cb.setIcon(_Icons.eye())
        self.show_cb.setCheckable(True)
        self.show_cb.setFixedHeight(34)
        self.show_cb.toggled.connect(self._toggle_show)
        token_box.addWidget(self.show_cb)

        form_layout.addLayout(token_box)
        layout.addWidget(form_card)

        btn_box = QHBoxLayout()
        test_btn = QPushButton(" Probar Conexion")
        test_btn.setIcon(_Icons.plug())
        test_btn.setFixedHeight(36)
        test_btn.clicked.connect(self._test_token)

        save_btn = QPushButton(" Guardar")
        save_btn.setIcon(_Icons.save())
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(test_btn)
        btn_box.addStretch()
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def _toggle_show(self, checked: bool):
        self.token_entry.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        if checked:
            self.show_cb.setText(" Ocultar")
            self.show_cb.setIcon(_Icons.eye_slash())
        else:
            self.show_cb.setText(" Mostrar")
        self.show_cb.setIcon(_Icons.eye())

    def _test_token(self):
        token = self.token_entry.text().strip()
        if not token:
            QMessageBox.warning(self, "Token Vacio", "Por favor introduzca un token para probar.")
            return
        ok = api_clients.validate_api_keys(token)
        if ok:
            QMessageBox.information(self, "Exito", "Token de ipinfo.io validado correctamente!")
        else:
            QMessageBox.critical(self, "Error", "El token introducido no es valido o hay un error de conexion con ipinfo.io.")

    def _save(self):
        self.token = self.token_entry.text().strip()
        config.save_api_keys(ipinfo_token=self.token)
        self.accept()


class DropArea(QFrame):
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(70)
        self.reset_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(10, 10, 10, 10)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(_Icons.folder_open().pixmap(32, 32))
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        self.label = QLabel("Arrastre y suelte su archivo aqui (.txt, .log, .csv, .docx)<br><span style='font-size: 11px; color: #64748B;'>o haga clic en 'Seleccionar Archivo'</span>")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #334155; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.label)

    def reset_style(self):
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #CBD5E1;
                border-radius: 10px;
                background-color: #F8FAFC;
            }
            DropArea:hover {
                border-color: #3B82F6;
                background-color: #EFF6FF;
            }
        """)

    def set_file_selected_style(self):
        self.setStyleSheet("""
            DropArea {
                border: 2px solid #2563EB;
                border-radius: 10px;
                background-color: #EFF6FF;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            if filepath:
                self.file_dropped.emit(filepath)


class StatCard(QFrame):
    def __init__(self, title: str, value: str = "0", icon=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            StatCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        icon_lbl = QLabel()
        if icon:
            icon_lbl.setPixmap(icon.pixmap(20, 20))
        layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A;")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;")

        text_layout.addWidget(self.val_lbl)
        text_layout.addWidget(title_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_value(self, value: str):
        self.val_lbl.setText(value)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IP Analyzer v2.2 - Extraccion Local & Enriquecimiento")
        self.resize(1400, 900)
        self.setMinimumSize(1100, 700)

        self.ipinfo_token = ""
        self.full_results: List[Dict[str, Any]] = []
        self.analysis_metadata: Dict[str, Any] = {}
        self.worker_thread: Optional[QThread] = None
        self.selected_file: Optional[Path] = None

        self._load_config()
        self._setup_ui()
        self._setup_menu()
        self._apply_styles()
        self._update_status()

    def _load_config(self):
        _, self.ipinfo_token = config.load_config()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # --- Header ---
        header_frame = QFrame()
        header_frame.setObjectName("HeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)

        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(2)
        title_lbl = QLabel("IP Analyzer v2.2")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A;")
        sub_lbl = QLabel("Extraccion Deterministica Rapida & Enriquecimiento de Datos de Red")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        brand_layout.addWidget(title_lbl)
        brand_layout.addWidget(sub_lbl)
        header_layout.addLayout(brand_layout)

        header_layout.addStretch()

        self.token_status_lbl = QLabel()
        self.token_status_lbl.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 10px;")
        header_layout.addWidget(self.token_status_lbl)

        btn_token_mgr = QPushButton(" Token IPInfo")
        btn_token_mgr.setIcon(_Icons.key())
        btn_token_mgr.setFixedHeight(28)
        btn_token_mgr.clicked.connect(self._manage_token)
        header_layout.addWidget(btn_token_mgr)

        main_layout.addWidget(header_frame)

        # --- Controls ---
        controls_group = QGroupBox(" Configuracion del Analisis")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(6)
        controls_layout.setContentsMargins(8, 8, 8, 8)

        file_box = QHBoxLayout()
        file_box.setSpacing(12)
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_selected)
        file_box.addWidget(self.drop_area, stretch=1)

        btn_file_layout = QVBoxLayout()
        btn_file_layout.setSpacing(8)
        self.btn_select_file = QPushButton(" Seleccionar Archivo")
        self.btn_select_file.setIcon(_Icons.folder_open())
        self.btn_select_file.setMinimumHeight(32)
        self.btn_select_file.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #0F172A;
                font-weight: 600;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """)
        self.btn_select_file.clicked.connect(self._browse_file)
        btn_file_layout.addWidget(self.btn_select_file)

        self.tz_combo = QComboBox()
        tz_options = ["UTC"] + [f"UTC+{h}" for h in range(1, 15)] + [f"UTC-{h}" for h in range(1, 13)]
        self.tz_combo.addItems(tz_options)
        self.tz_combo.setFixedHeight(28)

        tz_box = QVBoxLayout()
        tz_box.setSpacing(2)
        tz_lbl = QLabel("Zona Horaria Objetivo:")
        tz_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #475569;")
        tz_box.addWidget(tz_lbl)
        tz_box.addWidget(self.tz_combo)
        btn_file_layout.addLayout(tz_box)

        file_box.addLayout(btn_file_layout)
        controls_layout.addLayout(file_box)

        # Metadata
        meta_group = QGroupBox(" Metadatos del Caso (Opcional)")
        meta_layout = QGridLayout(meta_group)
        meta_layout.setContentsMargins(6, 6, 6, 6)
        meta_layout.setSpacing(6)

        lbl_invest = QLabel("Investigador:")
        lbl_invest.setStyleSheet("color: #0F172A; font-size: 11px;")
        meta_layout.addWidget(lbl_invest, 0, 0)
        self.entry_investigator = QLineEdit()
        self.entry_investigator.setPlaceholderText("Nombre del analista / perito")
        meta_layout.addWidget(self.entry_investigator, 0, 1)

        lbl_court = QLabel("Juzgado / Fiscalia:")
        lbl_court.setStyleSheet("color: #0F172A; font-size: 11px;")
        meta_layout.addWidget(lbl_court, 0, 2)
        self.entry_court = QLineEdit()
        self.entry_court.setPlaceholderText("Organismo requirente")
        meta_layout.addWidget(self.entry_court, 0, 3)

        lbl_dep = QLabel("Dependencia:")
        lbl_dep.setStyleSheet("color: #0F172A; font-size: 11px;")
        meta_layout.addWidget(lbl_dep, 1, 0)
        self.entry_dep = QLineEdit()
        self.entry_dep.setPlaceholderText("Unidad o division")
        meta_layout.addWidget(self.entry_dep, 1, 1)

        lbl_case = QLabel("Causa / Ref:")
        lbl_case.setStyleSheet("color: #0F172A; font-size: 11px;")
        meta_layout.addWidget(lbl_case, 1, 2)
        self.entry_case = QLineEdit()
        self.entry_case.setPlaceholderText("N Causa o Expte.")
        meta_layout.addWidget(self.entry_case, 1, 3)

        controls_layout.addWidget(meta_group)

        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton(" Iniciar Analisis")
        self.btn_start.setIcon(_Icons.play())
        self.btn_start.setFixedHeight(32)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.btn_start.clicked.connect(self._start_analysis)
        action_layout.addWidget(self.btn_start)

        self.btn_clear = QPushButton(" Limpiar")
        self.btn_clear.setIcon(_Icons.trash())
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.clicked.connect(self._clear_all)
        action_layout.addWidget(self.btn_clear)

        action_layout.addStretch()

        self.btn_toggle_log = QPushButton(" Mostrar Log")
        self.btn_toggle_log.setIcon(_Icons.clipboard())
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(False)
        self.btn_toggle_log.setFixedHeight(32)
        self.btn_toggle_log.toggled.connect(self._toggle_log_visibility)
        action_layout.addWidget(self.btn_toggle_log)

        controls_layout.addLayout(action_layout)
        main_layout.addWidget(controls_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E2E8F0;
                border-radius: 7px;
                background-color: #F1F5F9;
                text-align: center;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 6px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        # --- KPI Cards ---
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(6)
        self.card_total = StatCard("Total IPs", "0", _Icons.globe())
        self.card_isps = StatCard("ISPs Unicos", "0", _Icons.building())
        self.card_countries = StatCard("Paises", "0", _Icons.globe())
        self.card_private = StatCard("Redes Privadas", "0", _Icons.lock())

        stats_layout.addWidget(self.card_total)
        stats_layout.addWidget(self.card_isps)
        stats_layout.addWidget(self.card_countries)
        stats_layout.addWidget(self.card_private)
        main_layout.addLayout(stats_layout)

        # --- Splitter ---
        self.splitter = QSplitter(Qt.Vertical)

        results_widget = QWidget()
        res_vbox = QVBoxLayout(results_widget)
        res_vbox.setContentsMargins(0, 0, 0, 0)
        res_vbox.setSpacing(4)

        filter_box = QHBoxLayout()
        filter_box.setSpacing(6)

        lbl_search = QLabel("Buscar:")
        lbl_search.setStyleSheet("color: #0F172A; font-size: 11px;")
        filter_box.addWidget(lbl_search)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Filtrar por IP, ISP, Ubicacion, Hostname, Timestamp...")
        self.search_entry.textChanged.connect(self._filter_table)
        filter_box.addWidget(self.search_entry, stretch=2)

        lbl_country = QLabel("Pais:")
        lbl_country.setStyleSheet("color: #0F172A; font-size: 11px;")
        filter_box.addWidget(lbl_country)
        self.country_combo = QComboBox()
        self.country_combo.addItem("Todos")
        self.country_combo.currentTextChanged.connect(self._filter_table)
        filter_box.addWidget(self.country_combo, stretch=1)

        self.lbl_result_count = QLabel("Resultados: 0 IPs")
        self.lbl_result_count.setStyleSheet("font-weight: bold; color: #0F172A; font-size: 11px; padding: 0 6px;")
        filter_box.addWidget(self.lbl_result_count)

        res_vbox.addLayout(filter_box)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["N", "IP Address", "Timestamp (UTC)", "Timestamp Conv.", "ISP / Categoria", "Ubicacion", "Hostname"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        res_vbox.addWidget(self.table)

        self.splitter.addWidget(results_widget)

        self.log_widget = QGroupBox(" Log de Ejecucion del Sistema")
        log_vbox = QVBoxLayout(self.log_widget)
        log_vbox.setContentsMargins(4, 4, 4, 4)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; background-color: #0F172A; color: #F8FAFC;")
        log_vbox.addWidget(self.log_text)

        self.splitter.addWidget(self.log_widget)
        self.log_widget.setVisible(False)
        self.splitter.setSizes([700, 120])

        main_layout.addWidget(self.splitter, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&Archivo")

        action_token = QAction(" Gestionar Token IPInfo...", self)
        action_token.setIcon(_Icons.key())
        action_token.triggered.connect(self._manage_token)
        file_menu.addAction(action_token)

        action_reload = QAction(" Recargar Token (.env)", self)
        action_reload.setIcon(_Icons.sync())
        action_reload.triggered.connect(self._reload_env)
        file_menu.addAction(action_reload)

        file_menu.addSeparator()

        self.action_export = QAction(" Exportar Informe...", self)
        self.action_export.setIcon(_Icons.file_export())
        self.action_export.setEnabled(False)
        self.action_export.triggered.connect(self._export_report)
        file_menu.addAction(self.action_export)

        file_menu.addSeparator()

        action_exit = QAction(" Salir", self)
        action_exit.setIcon(_Icons.times())
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        view_menu = menu_bar.addMenu("&Ver")
        self.action_toggle_log = QAction(" Log de Ejecucion", self, checkable=True)
        self.action_toggle_log.setIcon(_Icons.clipboard())
        self.action_toggle_log.toggled.connect(self.btn_toggle_log.setChecked)
        view_menu.addAction(self.action_toggle_log)

        help_menu = menu_bar.addMenu("&Ayuda")
        action_about = QAction(" Acerca de IP Analyzer", self)
        action_about.setIcon(_Icons.info())
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F8FAFC;
            }
            #HeaderFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                margin-top: 6px;
                background-color: #FFFFFF;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #2563EB;
            }
            QTableWidget {
                gridline-color: #E2E8F0;
                background-color: #FFFFFF;
                selection-background-color: #DBEAFE;
                selection-color: #1E3A8A;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #334155;
                font-weight: bold;
                font-size: 12px;
                padding: 6px;
                border: none;
                border-right: 1px solid #E2E8F0;
                border-bottom: 2px solid #CBD5E1;
            }
            QLineEdit, QComboBox {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 5px 10px;
                background-color: #FFFFFF;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #2563EB;
            }
            QPushButton {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 14px;
                background-color: #FFFFFF;
                color: #334155;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
            }
            QMessageBox {
                background-color: #FFFFFF;
            }
            QMessageBox QLabel {
                color: #0F172A;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)

    def _update_status(self):
        if self.ipinfo_token:
            self.token_status_lbl.setText("Token IPInfo Activo")
            self.token_status_lbl.setStyleSheet("background-color: #DCFCE7; color: #166534; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 10px;")
            self.status_bar.showMessage("Enriquecimiento completo IPInfo habilitado.", 5000)
        else:
            self.token_status_lbl.setText("Modo Local (Sin Token)")
            self.token_status_lbl.setStyleSheet("background-color: #FEF9C3; color: #854D0E; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 10px;")
            self.status_bar.showMessage("Modo Local Activo (Sin Token IPInfo). Geolocalizacion no disponible.", 5000)

    def _toggle_log_visibility(self, checked: bool):
        self.log_widget.setVisible(checked)
        if checked:
            self.btn_toggle_log.setText(" Ocultar Log")
            self.btn_toggle_log.setIcon(_Icons.clipboard())
        else:
            self.btn_toggle_log.setText(" Mostrar Log")
            self.btn_toggle_log.setIcon(_Icons.clipboard())
        self.action_toggle_log.setChecked(checked)

    def _manage_token(self):
        dialog = ApiTokenDialog(self, self.ipinfo_token)
        if dialog.exec():
            self.ipinfo_token = dialog.token
            self._update_status()

    def _reload_env(self):
        self._load_config()
        self._update_status()
        QMessageBox.information(self, "Recarga", "Configuracion recargada exitosamente desde .env.")

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de entrada", "",
            "Archivos Soportados (*.txt *.log *.csv *.docx);;Todos (*.*)"
        )
        if filepath:
            self._on_file_selected(filepath)

    def _on_file_selected(self, filepath: str):
        path = Path(filepath)
        if path.is_file():
            self.selected_file = path
            file_size_kb = path.stat().st_size / 1024
            size_str = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb/1024:.2f} MB"

            self.drop_area.icon_label.setPixmap(_Icons.file().pixmap(32, 32))
            self.drop_area.label.setText(f"<b>{path.name}</b><br><span style='font-size: 11px; color: #64748B;'>Tamano: {size_str}</span>")
            self.drop_area.set_file_selected_style()
            self.status_bar.showMessage(f"Archivo cargado correctamente: {path.name}")
        else:
            QMessageBox.warning(self, "Error", f"No se pudo encontrar el archivo: {filepath}")

    def _start_analysis(self):
        if not self.selected_file or not self.selected_file.is_file():
            QMessageBox.warning(self, "Atencion", "Por favor seleccione o arrastre un archivo primero.")
            return

        self.btn_start.setEnabled(False)
        self.btn_select_file.setEnabled(False)
        self.progress_bar.setValue(0)
        self.table.setRowCount(0)
        self.log_text.clear()
        self.action_export.setEnabled(False)

        file_hash = self._calculate_file_hash(self.selected_file)

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(
            filepath=self.selected_file,
            target_tz=self.tz_combo.currentText(),
            ipinfo_token=self.ipinfo_token,
            file_hash=file_hash,
            app_version=self.windowTitle()
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.log_emitted.connect(self._on_log)
        self.worker.finished.connect(self._on_analysis_finished)
        self.worker.error_occurred.connect(lambda err: QMessageBox.critical(self, "Error", f"Error en el worker de analisis: {err}"))

        self.worker_thread.start()

    def _calculate_file_hash(self, filepath: Path) -> str:
        sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception:
            return ""

    def _on_progress(self, data: dict):
        perc = data.get("percentage", 0)
        msg = data.get("message", "")
        self.progress_bar.setValue(perc)
        self.status_bar.showMessage(msg)

    def _on_log(self, msg: str, level: str):
        color = "#F8FAFC"
        if level == "WARNING": color = "#FBBF24"
        elif level in ("ERROR", "CRITICAL"): color = "#F87171"
        elif level == "DEBUG": color = "#94A3B8"

        self.log_text.append(f'<font color="{color}">{msg}</font>')

    def _on_analysis_finished(self, results_wrapper: Optional[dict]):
        self.btn_start.setEnabled(True)
        self.btn_select_file.setEnabled(True)

        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()

        if not results_wrapper:
            self.status_bar.showMessage("El analisis finalizo sin generar resultados.")
            return

        self.full_results = results_wrapper.get("analysis_results", [])
        self.analysis_metadata = results_wrapper.get("metadata", {})

        self.status_bar.showMessage(f"Analisis finalizado exitosamente: {len(self.full_results)} IPs procesadas.", 8000)
        self.action_export.setEnabled(len(self.full_results) > 0)

        self._update_kpi_cards(self.full_results)
        self._populate_table(self.full_results)
        self._populate_country_filter()

    def _update_kpi_cards(self, results: List[Dict[str, Any]]):
        prep_data = file_io._prepare_export_data(results)
        total_ips = len(prep_data)

        isps = set()
        countries = set()
        private_count = 0

        for item in prep_data:
            isp = item.get("isp", "")
            if isp and "Error: Red" in isp:
                private_count += 1
            elif isp and not isp.startswith("Error"):
                isps.add(isp)

            country = item.get("country", "")
            if country and country != "N/A":
                countries.add(country)

        self.card_total.set_value(str(total_ips))
        self.card_isps.set_value(str(len(isps)))
        self.card_countries.set_value(str(len(countries)))
        self.card_private.set_value(str(private_count))

    def _populate_table(self, results: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        prep_data = file_io._prepare_export_data(results)

        self.table.setRowCount(len(prep_data))
        for row_idx, item in enumerate(prep_data):
            item_num = QTableWidgetItem(str(item.get("orden", "")))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, item_num)

            item_ip = QTableWidgetItem(str(item.get("ip_address", "")))
            item_ip.setFont(QFont("Consolas", 10, QFont.Bold))
            self.table.setItem(row_idx, 1, item_ip)

            self.table.setItem(row_idx, 2, QTableWidgetItem(str(item.get("timestamp_utc", ""))))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(item.get("timestamp_converted", ""))))

            isp_val = str(item.get("isp", ""))
            item_isp = QTableWidgetItem(isp_val)

            if "Error: Red Privada" in isp_val or "Error: Red Loopback" in isp_val:
                item_isp.setBackground(QColor("#E0E7FF"))
                item_isp.setForeground(QColor("#3730A3"))
            elif isp_val.startswith("Error:"):
                item_isp.setBackground(QColor("#FEE2E2"))
                item_isp.setForeground(QColor("#991B1B"))

            self.table.setItem(row_idx, 4, item_isp)

            self.table.setItem(row_idx, 5, QTableWidgetItem(str(item.get("location", ""))))
            self.table.setItem(row_idx, 6, QTableWidgetItem(str(item.get("hostname", ""))))

        self.lbl_result_count.setText(f"Resultados: {len(prep_data)} IPs")

    def _populate_country_filter(self):
        self.country_combo.blockSignals(True)
        self.country_combo.clear()
        self.country_combo.addItem("Todos")

        countries = set()
        prep_data = file_io._prepare_export_data(self.full_results)
        for item in prep_data:
            c = item.get("country")
            if c and c != "N/A":
                countries.add(c)

        for c in sorted(countries):
            self.country_combo.addItem(c)

        self.country_combo.blockSignals(False)

    def _filter_table(self):
        search_text = self.search_entry.text().lower().strip()
        selected_country = self.country_combo.currentText()

        prep_data = file_io._prepare_export_data(self.full_results)
        filtered = []

        for orig, prep in zip(self.full_results, prep_data):
            if selected_country != "Todos" and prep.get("country") != selected_country:
                continue

            if search_text:
                combined_text = " ".join([
                    str(prep.get("ip_address", "")),
                    str(prep.get("isp", "")),
                    str(prep.get("location", "")),
                    str(prep.get("hostname", "")),
                    str(prep.get("timestamp_utc", "")),
                    str(prep.get("timestamp_converted", ""))
                ]).lower()
                if search_text not in combined_text:
                    continue

            filtered.append(orig)

        self._populate_table(filtered)

    def _clear_all(self):
        self.full_results = []
        self.analysis_metadata = {}
        self.selected_file = None
        self.table.setRowCount(0)
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.search_entry.clear()
        self.country_combo.clear()
        self.country_combo.addItem("Todos")
        self.lbl_result_count.setText("Resultados: 0 IPs")
        self.action_export.setEnabled(False)

        self.card_total.set_value("0")
        self.card_isps.set_value("0")
        self.card_countries.set_value("0")
        self.card_private.set_value("0")

        self.drop_area.icon_label.setPixmap(_Icons.folder_open())
        self.drop_area.label.setText("Arrastre y suelte su archivo aqui (.txt, .log, .csv, .docx)<br><span style='font-size: 11px; color: #64748B;'>o haga clic en 'Seleccionar Archivo'</span>")
        self.drop_area.reset_style()
        self.status_bar.showMessage("Listo para iniciar un nuevo analisis.")

    def _export_report(self):
        if not self.full_results:
            return

        suggested_fn = f"Informe_IP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Exportar Informe", suggested_fn,
            "Documento PDF (*.pdf);;Archivo CSV (*.csv);;Archivo JSON (*.json);;Informe de Texto (*.txt)"
        )
        if not filepath:
            return

        path = Path(filepath)
        fmt = path.suffix.lower().replace(".", "")
        if not fmt:
            if "PDF" in selected_filter: fmt = "pdf"
            elif "CSV" in selected_filter: fmt = "csv"
            elif "JSON" in selected_filter: fmt = "json"
            else: fmt = "txt"
            path = path.with_suffix(f".{fmt}")

        meta = {
            "investigador": self.entry_investigator.text().strip(),
            "juzgado_fiscalia": self.entry_court.text().strip(),
            "dependencia": self.entry_dep.text().strip(),
            "causa_referencia": self.entry_case.text().strip(),
            "zona_horaria_solicitada_gui": self.tz_combo.currentText()
        }
        if self.analysis_metadata:
            meta.update(self.analysis_metadata)

        try:
            export_func = getattr(file_io, f"export_to_{fmt}", None)
            if export_func:
                export_func(path, self.full_results, meta)
                QMessageBox.information(self, "Exito", f"Informe exportado correctamente a:\n{path}")
            else:
                QMessageBox.critical(self, "Error", f"Formato no soportado: {fmt}")
        except Exception as e:
            logger.error(f"Error al exportar: {e}", exc_info=True)
            QMessageBox.critical(self, "Error de Exportacion", f"Ocurrio un error al exportar:\n{e}")

    def _show_about(self):
        QMessageBox.about(
            self,
            "Acerca de IP Analyzer",
            "<h3>IP Analyzer v2.2</h3>"
            "<p>Herramienta avanzada para la extraccion determinista, geolocalizacion y analisis forense de direcciones IP en documentos y registros de red.</p>"
            "<p><b>Caracteristicas clave:</b></p>"
            "<ul>"
            "<li>Rapida extraccion deterministica 100% local (sin dependencia de IA externas).</li>"
            "<li>Soporte de archivos .txt, .log, .csv y .docx.</li>"
            "<li>Conversion flexible de zonas horarias de timestamps.</li>"
            "<li>Enriquecimiento de ISP y geolocalizacion via ipinfo.io.</li>"
            "<li>Exportacion a PDF, CSV, JSON y TXT con metadatos del caso.</li>"
            "</ul>"
            "<p><b>Desarrollado por:</b> Diego A. Rabalo</p>"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

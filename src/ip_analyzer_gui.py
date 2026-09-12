import sys
import os
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import re

from PySide6.QtCore import Qt, QThread, Signal, QObject, QUrl
from PySide6.QtGui import QIcon, QFont, QDragEnterEvent, QDropEvent, QAction, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QSplitter, QGroupBox, QDialog, QFileDialog,
    QMessageBox, QFrame, QMenu, QMenuBar, QStatusBar, QTabWidget,
    QFormLayout, QAbstractItemView
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


class QtLogHandler(logging.Handler):
    """Logging handler that emits Qt signals for log messages."""
    def __init__(self, signal: Signal):
        super().__init__()
        self.signal = signal

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self.signal.emit(msg, record.levelname)


class AnalysisWorker(QObject):
    """Worker object to run processing in a separate QThread."""
    progress_updated = Signal(dict)
    log_emitted = Signal(str, str)
    finished = Signal(object) # Returns result dict or None
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
            logger.error(f"Error en worker de análisis: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.finished.emit(None)


class ApiTokenDialog(QDialog):
    """Dialog for managing ipinfo.io API token."""
    def __init__(self, parent=None, current_token: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Token API IPInfo")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.token = current_token

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        info_lbl = QLabel(
            "Ingrese su token de API de <b>ipinfo.io</b> para el enriquecimiento de geolocalización, ISP y detección de VPN/Proxy.\n"
            "Si no posee token, deje el campo vacío (se mostrarán únicamente IPs y timestamps)."
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        form = QFormLayout()
        self.token_entry = QLineEdit(current_token)
        self.token_entry.setEchoMode(QLineEdit.Password)
        self.token_entry.setPlaceholderText("Ej. 1a2b3c4d5e6f7g")
        form.addRow("Token IPInfo:", self.token_entry)

        self.show_cb = QPushButton("Mostrar")
        self.show_cb.setCheckable(True)
        self.show_cb.toggled.connect(self._toggle_show)
        form.addRow("", self.show_cb)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        test_btn = QPushButton("Probar Token")
        test_btn.clicked.connect(self._test_token)
        save_btn = QPushButton("Guardar")
        save_btn.setStyleSheet("background-color: #0066cc; color: white; font-weight: bold; padding: 6px 14px;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(test_btn)
        btn_box.addStretch()
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def _toggle_show(self, checked: bool):
        self.token_entry.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.show_cb.setText("Ocultar" if checked else "Mostrar")

    def _test_token(self):
        token = self.token_entry.text().strip()
        if not token:
            QMessageBox.warning(self, "Token Vacío", "Por favor introduzca un token para probar.")
            return
        ok = api_clients.validate_api_keys(token)
        if ok:
            QMessageBox.information(self, "Éxito", "Token de ipinfo.io validado correctamente.")
        else:
            QMessageBox.critical(self, "Error", "El token introducido no es válido o hay un error de conexión.")

    def _save(self):
        self.token = self.token_entry.text().strip()
        config.save_api_keys(ipinfo_token=self.token)
        self.accept()


class DropArea(QFrame):
    """Custom drag & drop file target widget."""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Sunken)
        self.setLineWidth(2)
        self.setMinimumHeight(80)
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #8a8a8a;
                border-radius: 8px;
                background-color: #f7f9fa;
            }
            DropArea:hover {
                border-color: #0066cc;
                background-color: #f0f7ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel("📁 Arrastre y suelte aquí su archivo (.txt, .log, .csv, .docx) o haga clic en Seleccionar")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #444444; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            if filepath:
                self.file_dropped.emit(filepath)


class MainWindow(QMainWindow):
    """Main application window built with PySide6."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IP Analyzer v2.2 - (Sin IA / Alta Velocidad Local)")
        self.resize(1150, 780)
        self.setMinimumSize(950, 600)

        self.ipinfo_token = ""
        self.full_results: List[Dict[str, Any]] = []
        self.analysis_metadata: Dict[str, Any] = {}
        self.worker_thread: Optional[QThread] = None

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
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # --- Top Section: Input controls & Metadata ---
        controls_group = QGroupBox("Configuración del Análisis")
        controls_layout = QVBoxLayout(controls_group)

        # Drop Area & File Selector Line
        file_box = QHBoxLayout()
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_selected)
        file_box.addWidget(self.drop_area, stretch=1)

        btn_file_layout = QVBoxLayout()
        self.btn_select_file = QPushButton("Seleccionar...")
        self.btn_select_file.setFixedHeight(36)
        self.btn_select_file.clicked.connect(self._browse_file)
        btn_file_layout.addWidget(self.btn_select_file)
        btn_file_layout.addStretch()
        file_box.addLayout(btn_file_layout)

        controls_layout.addLayout(file_box)

        # Options Line (Timezone, Actions)
        options_layout = QHBoxLayout()
        
        options_layout.addWidget(QLabel("Zona Horaria Objetivos:"))
        self.tz_combo = QComboBox()
        tz_options = ["UTC"] + [f"UTC+{h}" for h in range(1, 15)] + [f"UTC-{h}" for h in range(1, 13)]
        self.tz_combo.addItems(tz_options)
        self.tz_combo.setFixedWidth(130)
        options_layout.addWidget(self.tz_combo)

        options_layout.addSpacing(20)

        self.btn_start = QPushButton("🚀 Iniciar Análisis")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet("font-weight: bold; background-color: #007acc; color: white; border-radius: 4px; padding: 0 16px;")
        self.btn_start.clicked.connect(self._start_analysis)
        options_layout.addWidget(self.btn_start)

        self.btn_clear = QPushButton("Limpiar")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self._clear_all)
        options_layout.addWidget(self.btn_clear)

        options_layout.addStretch()
        controls_layout.addLayout(options_layout)

        # Collapsible/Compact Metadata Grid
        meta_group = QGroupBox("Metadatos del Caso / Informe (Opcional)")
        meta_layout = QGridLayout(meta_group)
        meta_layout.setContentsMargins(8, 8, 8, 8)

        meta_layout.addWidget(QLabel("Investigador:"), 0, 0)
        self.entry_investigator = QLineEdit()
        meta_layout.addWidget(self.entry_investigator, 0, 1)

        meta_layout.addWidget(QLabel("Juzgado/Fiscalía:"), 0, 2)
        self.entry_court = QLineEdit()
        meta_layout.addWidget(self.entry_court, 0, 3)

        meta_layout.addWidget(QLabel("Dependencia:"), 1, 0)
        self.entry_dep = QLineEdit()
        meta_layout.addWidget(self.entry_dep, 1, 1)

        meta_layout.addWidget(QLabel("Causa/Ref:"), 1, 2)
        self.entry_case = QLineEdit()
        meta_layout.addWidget(self.entry_case, 1, 3)

        controls_layout.addWidget(meta_group)
        main_layout.addWidget(controls_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        main_layout.addWidget(self.progress_bar)

        # --- Main Splitter: Results Table & Log ---
        splitter = QSplitter(Qt.Vertical)

        # Tab Widget for Results & Search
        results_widget = QWidget()
        res_vbox = QVBoxLayout(results_widget)
        res_vbox.setContentsMargins(0, 0, 0, 0)

        # Filter bar
        filter_box = QHBoxLayout()
        filter_box.addWidget(QLabel("🔍 Buscar en Resultados:"))
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Filtrar por IP, ISP, VPN, País, Timestamp...")
        self.search_entry.textChanged.connect(self._filter_table)
        filter_box.addWidget(self.search_entry)

        filter_box.addSpacing(15)
        filter_box.addWidget(QLabel("Filtrar País:"))
        self.country_combo = QComboBox()
        self.country_combo.addItem("Todos")
        self.country_combo.currentTextChanged.connect(self._filter_table)
        filter_box.addWidget(self.country_combo)

        self.lbl_result_count = QLabel("Resultados: 0 IPs")
        self.lbl_result_count.setStyleSheet("font-weight: bold; color: #555555;")
        filter_box.addSpacing(15)
        filter_box.addWidget(self.lbl_result_count)

        res_vbox.addLayout(filter_box)

        # Results Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Nº", "IP Address", "Timestamp (UTC)", "Timestamp Conv.", "ISP / Error", "Tipo Red / Privacidad", "Ubicación", "Hostname"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        res_vbox.addWidget(self.table)

        splitter.addWidget(results_widget)

        # Log Section
        log_widget = QGroupBox("Log del Sistema")
        log_vbox = QVBoxLayout(log_widget)
        log_vbox.setContentsMargins(6, 6, 6, 6)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        log_vbox.addWidget(self.log_text)

        splitter.addWidget(log_widget)
        splitter.setSizes([500, 180])

        main_layout.addWidget(splitter, stretch=1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _setup_menu(self):
        menu_bar = self.menuBar()

        # Archivo
        file_menu = menu_bar.addMenu("&Archivo")

        action_token = QAction("Gestionar Token IPInfo...", self)
        action_token.triggered.connect(self._manage_token)
        file_menu.addAction(action_token)

        action_reload = QAction("Recargar Token desde .env", self)
        action_reload.triggered.connect(self._reload_env)
        file_menu.addAction(action_reload)

        file_menu.addSeparator()

        self.action_export = QAction("Exportar Informe...", self)
        self.action_export.setEnabled(False)
        self.action_export.triggered.connect(self._export_report)
        file_menu.addAction(self.action_export)

        file_menu.addSeparator()

        action_exit = QAction("Salir", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        # Ayuda
        help_menu = menu_bar.addMenu("&Ayuda")
        action_about = QAction("Acerca de...", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f4f6f8;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                margin-top: 6px;
                background-color: #ffffff;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #0055aa;
            }
            QTableWidget {
                gridline-color: #e0e0e0;
                background-color: #ffffff;
                selection-background-color: #007acc;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #eef2f5;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #d0d0d0;
            }
            QLineEdit, QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QPushButton {
                border: 1px solid #bbbbbb;
                border-radius: 4px;
                padding: 5px 12px;
                background-color: #f8f9fa;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #999999;
            }
        """)

    def _update_status(self):
        if self.ipinfo_token:
            self.status_bar.showMessage("Listo. Token IPInfo configurado.", 5000)
        else:
            self.status_bar.showMessage("Modo Local Activo (Sin Token IPInfo). Geolocalización y VPN limitados.", 5000)

    def _manage_token(self):
        dialog = ApiTokenDialog(self, self.ipinfo_token)
        if dialog.exec():
            self.ipinfo_token = dialog.token
            self._update_status()

    def _reload_env(self):
        self._load_config()
        self._update_status()
        QMessageBox.information(self, "Recarga", "Configuración recargada desde .env.")

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de entrada", "",
            "Soportados (*.txt *.log *.csv *.docx);;Todos (*.*)"
        )
        if filepath:
            self._on_file_selected(filepath)

    def _on_file_selected(self, filepath: str):
        path = Path(filepath)
        if path.is_file():
            self.selected_file = path
            self.drop_area.label.setText(f"📄 Archivo Seleccionado: <b>{path.name}</b> ({path.stat().st_size} bytes)")
            self.drop_area.setStyleSheet("""
                DropArea {
                    border: 2px solid #007acc;
                    border-radius: 8px;
                    background-color: #eef7ff;
                }
            """)
            self.status_bar.showMessage(f"Archivo cargado: {path.name}")
        else:
            QMessageBox.warning(self, "Error", f"Archivo no encontrado: {filepath}")

    def _start_analysis(self):
        if not hasattr(self, 'selected_file') or not self.selected_file or not self.selected_file.is_file():
            QMessageBox.warning(self, "Atención", "Por favor seleccione o arrastre un archivo primero.")
            return

        # Prepare UI for analysis
        self.btn_start.setEnabled(False)
        self.btn_select_file.setEnabled(False)
        self.progress_bar.setValue(0)
        self.table.setRowCount(0)
        self.log_text.clear()
        self.action_export.setEnabled(False)

        # Hash file
        file_hash = self._calculate_file_hash(self.selected_file)

        # Setup worker & thread
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
        self.worker.error_occurred.connect(lambda err: QMessageBox.critical(self, "Error", f"Error en análisis: {err}"))

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
        color = "black"
        if level == "WARNING": color = "orange"
        elif level in ("ERROR", "CRITICAL"): color = "red"
        elif level == "DEBUG": color = "gray"

        self.log_text.append(f'<font color="{color}">{msg}</font>')

    def _on_analysis_finished(self, results_wrapper: Optional[dict]):
        self.btn_start.setEnabled(True)
        self.btn_select_file.setEnabled(True)

        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()

        if not results_wrapper:
            self.status_bar.showMessage("Análisis no devolvió resultados.")
            return

        self.full_results = results_wrapper.get("analysis_results", [])
        self.analysis_metadata = results_wrapper.get("metadata", {})

        self.status_bar.showMessage(f"Análisis finalizado: {len(self.full_results)} IPs procesadas.", 8000)
        self.action_export.setEnabled(len(self.full_results) > 0)

        self._populate_table(self.full_results)
        self._populate_country_filter()

    def _populate_table(self, results: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        prep_data = file_io._prepare_export_data(results)

        self.table.setRowCount(len(prep_data))
        for row_idx, item in enumerate(prep_data):
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(item.get("orden", ""))))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(item.get("ip_address", ""))))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(item.get("timestamp_utc", ""))))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(item.get("timestamp_converted", ""))))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(item.get("isp", ""))))

            # Privacy status item
            priv_item = QTableWidgetItem(str(item.get("privacy_status", "")))
            priv_str = str(item.get("privacy_status", ""))
            if "VPN" in priv_str or "Proxy" in priv_str or "TOR" in priv_str:
                priv_item.setForeground(QColor("#d9534f")) # Red highlight for VPN/Proxy
            elif "Hosting" in priv_str:
                priv_item.setForeground(QColor("#f0ad4e")) # Orange highlight for hosting
            elif "Residencial" in priv_str:
                priv_item.setForeground(QColor("#5cb85c")) # Green highlight for real residential IP

            self.table.setItem(row_idx, 5, priv_item)
            self.table.setItem(row_idx, 6, QTableWidgetItem(str(item.get("location", ""))))
            self.table.setItem(row_idx, 7, QTableWidgetItem(str(item.get("hostname", ""))))

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
            # Country filter
            if selected_country != "Todos" and prep.get("country") != selected_country:
                continue

            # Text filter
            if search_text:
                combined_text = " ".join([
                    str(prep.get("ip_address", "")),
                    str(prep.get("isp", "")),
                    str(prep.get("privacy_status", "")),
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
        self.table.setRowCount(0)
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.search_entry.clear()
        self.country_combo.clear()
        self.country_combo.addItem("Todos")
        self.lbl_result_count.setText("Resultados: 0 IPs")
        self.action_export.setEnabled(False)
        self.drop_area.label.setText("📁 Arrastre y suelte aquí su archivo (.txt, .log, .csv, .docx) o haga clic en Seleccionar")
        self.drop_area.setStyleSheet("""
            DropArea {
                border: 2px dashed #8a8a8a;
                border-radius: 8px;
                background-color: #f7f9fa;
            }
        """)
        if hasattr(self, 'selected_file'):
            del self.selected_file
        self.status_bar.showMessage("Listo para un nuevo análisis.")

    def _export_report(self):
        if not self.full_results:
            return

        suggested_fn = f"Informe_IP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Exportar Informe", suggested_fn,
            "PDF (*.pdf);;CSV (*.csv);;JSON (*.json);;TXT (*.txt)"
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
                QMessageBox.information(self, "Éxito", f"Informe exportado correctamente a:\n{path}")
            else:
                QMessageBox.critical(self, "Error", f"Formato no soportado: {fmt}")
        except Exception as e:
            logger.error(f"Error al exportar: {e}", exc_info=True)
            QMessageBox.critical(self, "Error de Exportación", f"Ocurrió un error al exportar:\n{e}")

    def _show_about(self):
        QMessageBox.about(
            self,
            "Acerca de IP Analyzer",
            "<h3>IP Analyzer v2.2</h3>"
            "<p>Herramienta avanzada de escritorio para análisis, geolocalización, detección de VPN/Proxy y procesamiento de direcciones IP y timestamps en documentos de red e investigaciones forenses digital.</p>"
            "<p><b>Desarrollado por:</b> Diego A. Rábalo</p>"
            "<p>Despliegue local rápido y seguro sin IA externa.</p>"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

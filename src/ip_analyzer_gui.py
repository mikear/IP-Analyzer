import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog, Toplevel, font as tkFont
import hashlib
import os
import subprocess
from queue import Queue, Empty
from pathlib import Path
import sys
import logging
from logging import LogRecord
import re
import threading
from datetime import datetime
from typing import Optional # Added Optional import # Added datetime import # Added threading import # Added re import

# --- Asegurar que el directorio del script esté en el path ---
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    script_dir = Path(sys._MEIPASS)
else:
    # Running from source
    from typing import List, Dict, Any, Optional, Iterator

    script_dir = Path(__file__).parent.resolve()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# --- Importar los módulos del backend ---
try:
    import config
    import api_clients
    import file_io
    import processing

    backend_missing_deps = processing._check_critical_dependencies()
    if backend_missing_deps:
        critical_for_gui = [
            d for d in backend_missing_deps if not ("docx" in d or "fpdf2" in d)
        ]
        if critical_for_gui:
            messagebox.showerror(
                "Error de Dependencias Críticas",
                f"Backend requiere dependencias esenciales:\n- {', '.join(critical_for_gui)}\n\nInstálalas e intenta de nuevo.",
            )
            sys.exit(1)
        else:
            # Usar print aquí o configurar un logger básico temporalmente
            print(f"ADVERTENCIA: Faltan deps opcionales backend: {backend_missing_deps}")

except ImportError as e:
    messagebox.showerror(
        "Error de Importación Crítico",
        f"No se pudo importar un módulo del backend.\nAsegúrate de que estén en {script_dir}.\nError: {e}",
    )
    sys.exit(1)
except Exception as general_import_error:
    messagebox.showerror(
        "Error de Importación Crítico",
        f"Error general importando módulos del backend:\n{general_import_error}\n\n{traceback.format_exc()}",
    )
    sys.exit(1)


# --- Handler de Logging para la Cola de la GUI ---
class QueueHandler(logging.Handler):
    """Handler que pone LogRecords en una cola Queue."""
    def __init__(self, log_queue: Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: LogRecord):
        self.log_queue.put(record)


# --- Clase de Diálogo para API Keys ---
class ApiKeyDialog(Toplevel):
    """Diálogo modal para ingresar y guardar claves API."""
    def __init__(self, parent, current_gemini_key: Optional[str], current_ipinfo_token: Optional[str]):
        super().__init__(parent)
        self.title("Gestionar Claves API"); self.transient(parent); self.grab_set()
        self.resizable(False, False); self.parent = parent
        self.gemini_key_var = tk.StringVar(value=current_gemini_key or "")
        self.ipinfo_token_var = tk.StringVar(value=current_ipinfo_token or "")
        self.gemini_show_var = tk.BooleanVar(value=False); self.ipinfo_show_var = tk.BooleanVar(value=False)
        self.result: Optional[Dict[str, str]] = None

        frame = ttk.Frame(self, padding="15"); frame.pack(expand=True, fill=tk.BOTH)
        ttk.Label(frame, text="Clave API Google Gemini:").grid(row=0, column=0, padx=5, pady=8, sticky=tk.W)
        gemini_entry = ttk.Entry(frame, textvariable=self.gemini_key_var, width=60, show="*")
        gemini_entry.grid(row=0, column=1, padx=5, pady=8)
        gemini_show_btn = ttk.Checkbutton(frame, text="Mostrar", variable=self.gemini_show_var, command=lambda e=gemini_entry, v=self.gemini_show_var: self._toggle_visibility(e, v))
        gemini_show_btn.grid(row=0, column=2, padx=(5, 0), pady=8, sticky=tk.W)
        ttk.Label(frame, text="Token API ipinfo.io:").grid(row=1, column=0, padx=5, pady=8, sticky=tk.W)
        ipinfo_entry = ttk.Entry(frame, textvariable=self.ipinfo_token_var, width=60, show="*")
        ipinfo_entry.grid(row=1, column=1, padx=5, pady=8)
        ipinfo_show_btn = ttk.Checkbutton(frame, text="Mostrar", variable=self.ipinfo_show_var, command=lambda e=ipinfo_entry, v=self.ipinfo_show_var: self._toggle_visibility(e, v))
        ipinfo_show_btn.grid(row=1, column=2, padx=(5, 0), pady=8, sticky=tk.W)
        button_frame = ttk.Frame(frame); button_frame.grid(row=2, column=0, columnspan=3, pady=(15, 5))
        accent_style = 'Accent.TButton' if 'Accent.TButton' in self.winfo_toplevel().tk.call('ttk::style', 'map', 'TButton') else 'TButton'
        ttk.Button(button_frame, text="Guardar y Cerrar", command=self._save, style=accent_style).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=10)
        self.update_idletasks(); parent_x = parent.winfo_rootx(); parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width(); parent_height = parent.winfo_height()
        dialog_width = self.winfo_width(); dialog_height = self.winfo_height()
        x = parent_x + (parent_width // 2) - (dialog_width // 2); y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f"{x}+{y}"); gemini_entry.focus_set(); self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _toggle_visibility(self, entry_widget: ttk.Entry, show_var: tk.BooleanVar):
        entry_widget.config(show="" if show_var.get() else "*")

    def _save(self):
        gemini = self.gemini_key_var.get().strip(); ipinfo = self.ipinfo_token_var.get().strip()
        if not gemini or not ipinfo: messagebox.showwarning("Campos Vacíos", "Ambas claves API son necesarias.", parent=self); return
        try:
            save_successful = config.save_api_keys(gemini, ipinfo)
            if save_successful: self.result = {"gemini": gemini, "ipinfo": ipinfo}; self.destroy()
            else: messagebox.showerror("Error al Guardar", "No se pudieron guardar claves API en .env.", parent=self)
        except Exception as e: messagebox.showerror("Error Inesperado al Guardar", f"Ocurrió un error:\n{e}", parent=self); logging.getLogger(__name__).error("Error guardando claves (diálogo)", exc_info=True)


# --- Clase Principal de la GUI ---
class IPAnalyzerApp(tk.Tk):
    """Clase principal de la aplicación GUI."""

    def __init__(self):
        super().__init__()
        self.title("IP Analyzer v2.2")
        self.minsize(950, 700)

        gui_logger = logging.getLogger('GUI') # Logger para GUI
        icon_set = False
        for ext in ['png', 'ico']:
             try:
                 icon_path = script_dir.parent / "assets" / f"app_icon.{ext}"
                 if icon_path.is_file():
                     if ext == 'png':
                         img = tk.PhotoImage(file=str(icon_path))
                         self.tk.call('wm', 'iconphoto', self._w, img)
                     elif ext == 'ico' and os.name == 'nt':
                         self.iconbitmap(str(icon_path))
                     icon_set = True; gui_logger.info(f"Icono '{icon_path.name}' establecido.")
                     break
             except Exception as e: gui_logger.warning(f"No se pudo establecer icono {icon_path.name}: {e}")
        if not icon_set: gui_logger.info("No se encontró icono 'app_icon.png/ico'. Usando default.")

        self.withdraw(); self.update_idletasks()
        screen_width = self.winfo_screenwidth(); screen_height = self.winfo_screenheight()
        win_width = max(self.winfo_reqwidth(), int(screen_width * 0.75))
        win_height = max(self.winfo_reqheight(), int(screen_height * 0.7)) 
        win_width = max(win_width, self.winfo_width()); win_height = max(win_height, self.winfo_height())
        pos_x = max(0, (screen_width // 2) - (win_width // 2)); pos_y = max(0, (screen_height // 2) - (win_height // 2))
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}"); self.deiconify()

        # --- Variables de estado ---
        self.input_file_path = tk.StringVar()
        self.timezone = tk.StringVar(value="UTC")
        self.is_processing = tk.BooleanVar(value=False)
        self.api_keys_loaded = False
        self.gemini_key: Optional[str] = None
        self.ipinfo_token: Optional[str] = None
        self.progress_queue = Queue() 
        self.log_queue = Queue() # Cola para logs del backend
        self.full_results: Optional[List[Dict[str, Any]]] = []
        self.current_filter_country = tk.StringVar(value="Todos")
        self.meta_investigator = tk.StringVar(); self.meta_court = tk.StringVar()
        self.meta_dependency = tk.StringVar(); self.meta_case_id = tk.StringVar()
        self.analysis_thread: Optional[threading.Thread] = None
        self.default_status_fg: Optional[str] = None
        self._status_reset_job: Optional[str] = None
        self._log_check_job: Optional[str] = None
        self.log_queue_handler: Optional[QueueHandler] = None
        self._log_check_job: Optional[str] = None
        self._populate_job: Optional[str] = None

        # --- Inicialización ---
        self._apply_styles()
        self._load_api_keys()
        self._create_menu()
        self._create_widgets()
        self._setup_logging_queue_reader()
        self._update_status_bar_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _apply_styles(self) -> None:
        style = ttk.Style(self); available_themes = style.theme_names()
        if os.name == 'nt': desired_themes = ['vista', 'xpnative', 'clam', 'alt', 'default']
        elif sys.platform == 'darwin': desired_themes = ['aqua', 'clam', 'alt', 'default']
        else: desired_themes = ['clam', 'alt', 'default']
        chosen_theme = style.theme_use()
        for theme in desired_themes:
             if theme in available_themes:
                 try: style.theme_use(theme); chosen_theme = theme; logging.getLogger('GUI').info(f"Usando tema ttk '{theme}'."); break
                 except tk.TclError: continue
        default_font = tkFont.nametofont("TkDefaultFont").actual()
        base_fam = default_font.get('family', 'Segoe UI'); base_size = default_font.get('size', 9)
        style.configure('.', font=(base_fam, base_size))
        style.configure('Treeview.Heading', font=(base_fam, base_size + 1, 'bold'))
        style.configure('Treeview', rowheight=26, font=(base_fam, base_size))
        style.configure('TLabelframe.Label', font=(base_fam, base_size + 1, 'bold'), padding=(5, 2))
        style.configure('TButton', padding=(8, 4)); style.configure('TCombobox', padding=(5, 3))
        style.configure('TEntry', padding=(5, 3)); style.configure('TLabel', padding=2)

    def _load_api_keys(self) -> None:
        self.api_keys_loaded = False
        try:
            self.gemini_key, self.ipinfo_token = config.load_config()
            if self.gemini_key and self.ipinfo_token: self.api_keys_loaded = True
        except Exception as e: 
            msg = f"Error al leer config .env:\n{e}"; logging.getLogger(__name__).error(msg, exc_info=True)
            if self.winfo_exists() and self.state() == 'normal': messagebox.showerror("Error Configuración", msg, parent=self)

    def _update_status_bar_keys(self) -> None:
        if not hasattr(self, 'status_label') or not self.status_label.winfo_exists(): return
        if not hasattr(self, 'analyze_button') or not self.analyze_button.winfo_exists(): return
        status_msg = ""; status_color = self.default_status_fg
        analyze_state = tk.DISABLED
        if self.default_status_fg is None:
            try: self.default_status_fg = self.status_label.cget('foreground')
            except tk.TclError: self.default_status_fg = 'black'
        if self.api_keys_loaded:
            status_msg = "Listo. Claves API cargadas."; status_color = "green"
            if not self.is_processing.get(): analyze_state = tk.NORMAL
        else:
            status_msg = "Esperando config API Keys (Menú Archivo)"; status_color = "orange"
        self.analyze_button.config(state=analyze_state)
        try: self.status_label.config(text=status_msg, foreground=status_color)
        except tk.TclError: pass

    def _create_menu(self) -> None:
        self.menu_bar = tk.Menu(self); self.config(menu=self.menu_bar)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Gestionar Claves API...", command=self._show_api_key_dialog)
        file_menu.add_command(label="Recargar Claves API desde .env", command=self._reload_keys_action)
        file_menu.add_separator()
        self.export_menu_index = file_menu.index(tk.END); self.export_menu_index = 0 if self.export_menu_index is None else self.export_menu_index + 1
        file_menu.add_command(label="Exportar Informe...", command=self._export_report, state=tk.DISABLED)
        file_menu.add_separator(); file_menu.add_command(label="Salir", command=self._on_closing)
        self.file_menu = file_menu
        
        

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(2, weight=1); main_frame.columnconfigure(0, weight=1)
        controls_frame = ttk.LabelFrame(main_frame, text="Configuración de Análisis", padding="10")
        controls_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=(0, 10)); controls_frame.columnconfigure(1, weight=1); controls_frame.columnconfigure(3, weight=1)
        ttk.Label(controls_frame, text="Archivo de Entrada:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky=tk.W)
        self.file_entry = ttk.Entry(controls_frame, textvariable=self.input_file_path, width=70, state='readonly')
        self.file_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky=tk.EW)
        self.select_button = ttk.Button(controls_frame, text="Seleccionar...", command=self._select_file)
        try: self.select_button.config(style='Accent.TButton')
        except tk.TclError: pass
        self.select_button.grid(row=0, column=4, padx=(10, 0), pady=5)
        ttk.Label(controls_frame, text="Zona Horaria Destino:").grid(row=1, column=0, padx=(0, 5), pady=5, sticky=tk.W)
        tz_offsets = ["UTC"] + [f"UTC+{h}" for h in range(1, 15)] + [f"UTC-{h}" for h in range(1, 13)] # Considerar añadir IANA si backend las soporta bien
        self.tz_combo = ttk.Combobox(controls_frame, textvariable=self.timezone, values=tz_offsets, state="readonly", width=10)
        self.tz_combo.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W); self.timezone.set("UTC")
        ttk.Label(controls_frame, text="Filtrar Resultados por País:").grid(row=1, column=2, padx=(20, 5), pady=5, sticky=tk.W)
        self.filter_combo = ttk.Combobox(controls_frame, textvariable=self.current_filter_country, state="disabled", width=25)
        self.filter_combo.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W); self.filter_combo.bind("<<ComboboxSelected>>", self._apply_filter)
        meta_frame = ttk.Frame(controls_frame); meta_frame.grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=(10,5))
        meta_frame.columnconfigure(1, weight=1); meta_frame.columnconfigure(3, weight=1)
        ttk.Label(meta_frame, text="Investigador:").grid(row=0, column=0, padx=(0, 5), pady=3, sticky=tk.W)
        self.meta_investigator_entry = ttk.Entry(meta_frame, textvariable=self.meta_investigator, width=35)
        self.meta_investigator_entry.grid(row=0, column=1, padx=5, pady=3, sticky=tk.EW)
        ttk.Label(meta_frame, text="Juzgado/Fiscalía:").grid(row=0, column=2, padx=(15, 5), pady=3, sticky=tk.W)
        self.meta_court_entry = ttk.Entry(meta_frame, textvariable=self.meta_court, width=35)
        self.meta_court_entry.grid(row=0, column=3, padx=5, pady=3, sticky=tk.EW)
        ttk.Label(meta_frame, text="Dependencia:").grid(row=1, column=0, padx=(0, 5), pady=3, sticky=tk.W)
        self.meta_dependency_entry = ttk.Entry(meta_frame, textvariable=self.meta_dependency, width=35)
        self.meta_dependency_entry.grid(row=1, column=1, padx=5, pady=3, sticky=tk.EW)
        ttk.Label(meta_frame, text="Causa/Referencia:").grid(row=1, column=2, padx=(15, 5), pady=3, sticky=tk.W)
        self.meta_case_id_entry = ttk.Entry(meta_frame, textvariable=self.meta_case_id, width=35)
        self.meta_case_id_entry.grid(row=1, column=3, padx=5, pady=3, sticky=tk.EW)
        self.metadata_widgets = [self.meta_investigator_entry, self.meta_court_entry, self.meta_dependency_entry, self.meta_case_id_entry]
        mid_frame = ttk.Frame(main_frame, padding="5 0"); mid_frame.grid(row=1, column=0, pady=8)
        self.analyze_button = ttk.Button(mid_frame, text="Iniciar Análisis", command=self._start_analysis_thread, state=tk.DISABLED, width=18)
        self.analyze_button.pack(side=tk.LEFT, padx=(0, 10))
        self.clear_button = ttk.Button(mid_frame, text="Limpiar", command=self._clear_interface)
        self.clear_button.pack(side=tk.LEFT, padx=(0, 15))
        self.progress_bar = ttk.Progressbar(mid_frame, orient=tk.HORIZONTAL, length=450, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        bottom_pane = ttk.PanedWindow(main_frame, orient=tk.VERTICAL); bottom_pane.grid(row=2, column=0, sticky=tk.NSEW, pady=(5, 0))
        report_frame = ttk.LabelFrame(bottom_pane, text="Informe de Resultados", padding="5")
        report_frame.columnconfigure(0, weight=1); report_frame.rowconfigure(0, weight=1); bottom_pane.add(report_frame, weight=3)
        self.report_tree = ttk.Treeview(report_frame, selectmode='browse')
        self.report_tree["columns"] = ("orden", "ts_utc", "ts_conv", "isp", "location", "hostname")
        self.report_tree.column("#0", width=140, minwidth=120, anchor=tk.W, stretch=tk.NO); self.report_tree.heading("#0", text="IP Address", anchor=tk.W)
        col_defs = {"orden": {"text":"Nº", "w":40, "min":35, "a":'center', "s":tk.NO}, "ts_utc": {"text":"Timestamp (UTC)", "w":160, "min":140, "a":'w', "s":tk.YES}, "ts_conv": {"text":"Timestamp Conv.", "w":170, "min":150, "a":'w', "s":tk.YES}, "isp": {"text":"ISP / Error", "w":220, "min":180, "a":'w', "s":tk.YES}, "location": {"text":"Ubicación", "w":180, "min":150, "a":'w', "s":tk.YES}, "hostname": {"text":"Hostname", "w":200, "min":160, "a":'w', "s":tk.YES}}
        for col_id, c in col_defs.items(): self.report_tree.column(col_id, width=c["w"], minwidth=c["min"], anchor=c["a"], stretch=c["s"]); self.report_tree.heading(col_id, text=c["text"], anchor=c["a"])
        tree_vsb = ttk.Scrollbar(report_frame, orient="vertical", command=self.report_tree.yview)
        tree_hsb = ttk.Scrollbar(report_frame, orient="horizontal", command=self.report_tree.xview)
        self.report_tree.configure(yscrollcommand=tree_vsb.set, xscrollcommand=tree_hsb.set)
        self.report_tree.grid(row=0, column=0, sticky='nsew'); tree_vsb.grid(row=0, column=1, sticky='ns'); tree_hsb.grid(row=1, column=0, sticky='ew')

        log_frame = ttk.LabelFrame(bottom_pane, text="Log del Proceso", padding="5")
        log_frame.columnconfigure(0, weight=1); log_frame.rowconfigure(0, weight=1); bottom_pane.add(log_frame, weight=1)
        log_font_family = "Consolas" if "Consolas" in tkFont.families() else "Courier New"
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10, state='disabled', font=(log_font_family, 9), bd=0, relief=tk.FLAT)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        self.log_text.tag_configure("DEBUG", foreground="grey"); self.log_text.tag_configure("INFO", foreground="black")
        self.log_text.tag_configure("WARNING", foreground="orange"); self.log_text.tag_configure("ERROR", foreground="red")
        self.log_text.tag_configure("CRITICAL", foreground="red", font=(log_font_family, 9, "bold"))

        self.status_bar_frame = ttk.Frame(main_frame, relief=tk.SUNKEN, padding=0)
        self.status_bar_frame.grid(row=3, column=0, sticky=tk.EW, pady=(5,0))
        self.status_label = ttk.Label(self.status_bar_frame, text="Cargando...", anchor=tk.W, padding=(5, 3))
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _show_api_key_dialog(self) -> None:
        """Muestra el diálogo para gestionar claves API."""
        dialog = ApiKeyDialog(self, self.gemini_key, self.ipinfo_token)
        self.wait_window(dialog)

        if dialog.result:
            self.gemini_key = dialog.result["gemini"]
            self.ipinfo_token = dialog.result["ipinfo"]
            self.api_keys_loaded = True
            logging.getLogger(__name__).info("Claves API actualizadas y guardadas desde el diálogo.")
            self.update_status("Claves API guardadas en .env", "green", duration=4000)
        else:
            logging.getLogger(__name__).info("Diálogo claves API cerrado sin guardar.")

        self._update_status_bar_keys()

    def _reload_keys_action(self) -> None:
        """Recarga las claves desde el archivo .env."""
        logging.getLogger(__name__).info("Recargando claves API desde .env...")
        self._load_api_keys()
        self._update_status_bar_keys()
        if self.api_keys_loaded: messagebox.showinfo("Recarga Exitosa", ".env recargado.", parent=self)
        else: messagebox.showwarning("Recarga Fallida", f"No se encontraron claves en {config.get_dotenv_path()}", parent=self)

    

    def _export_report(self) -> None:
        if not self.full_results: messagebox.showwarning("Sin Datos", "No hay resultados para exportar.", parent=self); return
        try: input_base = Path(self.input_file_path.get()).stem
        except: input_base = "analisis"
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S"); suggested_fn = f"Informe_IP_{input_base}_{ts_str}"
        filetypes = [('CSV', '*.csv'), ('JSON', '*.json'), ('PDF', '*.pdf'), ('TXT', '*.txt'), ('Todos', '*.*')]
        filepath_save = filedialog.asksaveasfilename(title="Exportar Como", initialfile=suggested_fn, filetypes=filetypes, defaultextension=".csv", parent=self)
        if not filepath_save: return
        filepath_obj = Path(filepath_save); export_format = filepath_obj.suffix.lower()
        if export_format not in ['.csv', '.json', '.pdf', '.txt']: messagebox.showerror("Formato No Soportado", f"Extensión '{export_format}' inválida.", parent=self); return

        # Collect metadata from GUI fields
        gui_metadata = {
            "investigador": self.meta_investigator.get().strip(),
            "juzgado_fiscalia": self.meta_court.get().strip(),
            "dependencia": self.meta_dependency.get().strip(),
            "causa_referencia": self.meta_case_id.get().strip(),
            "archivo_origen": Path(self.input_file_path.get()).name,
            "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "zona_horaria_solicitada_gui": self.timezone.get()
        }
        gui_metadata = {k: v for k, v in gui_metadata.items() if v}

        # Combine analysis_metadata with GUI_metadata
        # analysis_metadata contains input_file_sha256, app_version, etc.
        # gui_metadata contains user-entered case details
        # Prioritize analysis_metadata if there are overlaps (e.g., input_filepath)
        final_metadata = {}
        if self.analysis_metadata:
            final_metadata.update(self.analysis_metadata)
        final_metadata.update(gui_metadata) # GUI metadata might override some analysis metadata if keys are the same

        try:
            self.update_status(f"Exportando a {export_format.upper()}...", "blue")
            self.config(cursor="watch"); self.update_idletasks()
            export_func = getattr(file_io, f"export_to_{export_format[1:]}", None)
            if export_func: 
                logging.getLogger(__name__).info(f"Final metadata for export: {final_metadata}")
                export_func(filepath_obj, self.full_results, final_metadata) # Pass final_metadata
            else: raise ValueError(f"Formato exportación no soportado: {export_format}")
            self.config(cursor=""); messagebox.showinfo("Exportación Completa", f"Informe exportado a:\n{filepath_obj}", parent=self)
            self.update_status("Exportación completa.", "green", duration=5000)
        except ImportError as dep_err:
             self.config(cursor=""); msg = f"Exportación {export_format.upper()} falló.\nFalta dependencia: {dep_err}"
             logging.getLogger(__name__).error(msg); messagebox.showerror("Error Dependencia", msg, parent=self)
             self.update_status(f"Error exportación (falta {dep_err}).", "red")
        except Exception as e:
            self.config(cursor=""); msg = f"Error exportando a '{filepath_obj}'.\nError: {e}"
            logging.getLogger(__name__).error(msg, exc_info=True); messagebox.showerror("Error Exportación", msg, parent=self)
            self.update_status("Error durante la exportación.", "red")

    def _select_file(self) -> None:
        if self.is_processing.get(): return
        initial_dir = getattr(self, "_last_browse_dir", script_dir)
        filepath = filedialog.askopenfilename(title="Seleccionar archivo entrada", initialdir=initial_dir, filetypes=[("Soportados", "*.txt;*.docx;*.csv;*.log"), ("Todos", "*.*")])
        if filepath:
            self._clear_interface(clear_input_field=False)
            selected_path = Path(filepath); self._last_browse_dir = selected_path.parent
            self.input_file_path.set(str(selected_path))
            self.update_status(f"Archivo listo: {selected_path.name}")
            logging.getLogger('GUI').info(f"Archivo seleccionado: {selected_path}")

    def _clear_interface(self, clear_input_field: bool = True) -> None:
        if self.is_processing.get(): return
        logging.getLogger('GUI').info("Limpiando interfaz de usuario.")
        if clear_input_field:
            self.input_file_path.set("")
        self.full_results = []
        self._clear_treeview()
        self._clear_log()
        self._set_menu_export_state(False)
        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
        if hasattr(self, 'filter_combo'):
            self.filter_combo.set("Todos")
            self.filter_combo.config(values=["Todos"], state="disabled")
        self._update_status_bar_keys()
        if clear_input_field: 
            self.update_status("Listo para un nuevo análisis.")

    def _update_log_task(self, record: LogRecord) -> None:
        if not hasattr(self, 'log_text') or not self.log_text.winfo_exists(): return
        try:
            self.log_text.config(state='normal')
            msg = self.log_queue_handler.format(record) if self.log_queue_handler and self.log_queue_handler.formatter else f"{record.levelname}: {record.getMessage()}"
            tag = record.levelname
            self.log_text.insert(tk.END, msg + "\n", (tag,))
            self.log_text.see(tk.END); self.log_text.config(state='disabled')
        except tk.TclError: pass
        except Exception as e: print(f"ERROR INTERNO GUI: Fallo al actualizar log: {e}")

    def _clear_log(self) -> None:
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            try: self.log_text.config(state='normal'); self.log_text.delete('1.0', tk.END); self.log_text.config(state='disabled')
            except tk.TclError: pass

    def _check_log_queue(self) -> None:
        try:
            while True: record = self.log_queue.get_nowait(); self.after_idle(self._update_log_task, record)
        except Empty: pass
        except Exception as e: print(f"ERROR GUI: Excepción en _check_log_queue: {e}")
        finally:
            if self.winfo_exists(): self._log_check_job = self.after(200, self._check_log_queue)

    def _setup_logging_queue_reader(self) -> None:
        self.log_queue_handler = QueueHandler(self.log_queue)
        if self._log_check_job: self.after_cancel(self._log_check_job)
        self._log_check_job = self.after(100, self._check_log_queue)

    def update_status(self, message: str, color: Optional[str] = None, duration: Optional[int] = None) -> None:
        self.after(0, self._update_status_task, message, color, duration)

    def _update_status_task(self, message: str, color: Optional[str], duration: Optional[int]) -> None:
        if not hasattr(self, 'status_label') or not self.status_label.winfo_exists(): return
        if self.default_status_fg is None:
            try: self.default_status_fg = self.status_label.cget('foreground')
            except: self.default_status_fg = 'black'
        new_fg = color if color else self.default_status_fg
        try: self.status_label.config(text=message, foreground=new_fg)
        except tk.TclError: return
        if hasattr(self, '_status_reset_job') and self._status_reset_job is not None:
             try: self.after_cancel(self._status_reset_job)
             except: pass
             finally: self._status_reset_job = None
        if duration and duration > 0:
             try: self._status_reset_job = self.after(duration, self._update_status_bar_keys)
             except tk.TclError: pass

    def _set_menu_export_state(self, enabled: bool) -> None:
        if hasattr(self, 'file_menu') and self.file_menu.winfo_exists():
            try:
                state = tk.NORMAL if enabled else tk.DISABLED
                if self.export_menu_index is not None and self.export_menu_index >= 0:
                     last_idx = self.file_menu.index(tk.END)
                     if last_idx is not None and self.export_menu_index <= last_idx:
                          self.file_menu.entryconfig(self.export_menu_index, state=state)
            except tk.TclError: pass

    def _set_processing_state(self, processing: bool) -> None:
        self.after(0, self._set_processing_state_task, processing)

    def _set_processing_state_task(self, processing: bool) -> None:
        if not self.winfo_exists(): return
        self.is_processing.set(processing)
        state_if_not = tk.NORMAL; state_if_proc = tk.DISABLED
        current_state = state_if_proc if processing else state_if_not
        try:
            if hasattr(self,'select_button') and self.select_button.winfo_exists(): self.select_button.config(state=current_state)
            if hasattr(self,'clear_button') and self.clear_button.winfo_exists(): self.clear_button.config(state=current_state)
            tz_combo_state = state_if_proc if processing else "readonly"
            if hasattr(self,'tz_combo') and self.tz_combo.winfo_exists(): self.tz_combo.config(state=tz_combo_state)
            if hasattr(self,'metadata_widgets'):
                for w in self.metadata_widgets:
                     if w.winfo_exists(): w.config(state=current_state)
            if hasattr(self,'analyze_button') and self.analyze_button.winfo_exists():
                self.analyze_button.config(text="Analizando..." if processing else "Iniciar Análisis")
                analyze_btn_state = state_if_proc if processing else (tk.NORMAL if self.api_keys_loaded else tk.DISABLED)
                self.analyze_button.config(state=analyze_btn_state)
            if hasattr(self,'menu_bar') and self.menu_bar.winfo_exists():
                for menu_name in ["Archivo", "Ayuda"]:
                     try: self.menu_bar.entryconfig(menu_name, state=current_state)
                     except tk.TclError: pass
            export_enabled = not processing and bool(self.full_results)
            self._set_menu_export_state(export_enabled)
            filter_state = tk.DISABLED
            if not processing and self.full_results:
                if hasattr(self,'filter_combo') and self.filter_combo.winfo_exists():
                    vals = self.filter_combo.cget('values')
                    if vals and len(vals) > 1: filter_state = "readonly"
            if hasattr(self,'filter_combo') and self.filter_combo.winfo_exists(): self.filter_combo.config(state=filter_state)
        except tk.TclError: pass
        except Exception as e: logging.getLogger('GUI').error("Error inesperado en _set_processing_state_task", exc_info=True)

    

    def _clear_treeview(self) -> None:
        if self._populate_job:
            self.after_cancel(self._populate_job)
            self._populate_job = None
        if hasattr(self, 'report_tree') and self.report_tree.winfo_exists():
            try:
                 children = self.report_tree.get_children()
                 if children: self.report_tree.delete(*children)
            except tk.TclError: pass

    def _populate_treeview(self, results_to_display: List[Dict[str, Any]]) -> None:
        if not hasattr(self, 'report_tree') or not self.report_tree.winfo_exists(): return
        self._clear_treeview()
        try:
            prepared_data = file_io._prepare_export_data(results_to_display)
        except Exception as e: 
            logging.getLogger(__name__).error("Error preparando datos TreeView", exc_info=True)
            self._clear_log()
            self.log_text.insert("1.0", "Error interno preparando datos para la tabla.")
            return

        rows_iterator = iter([(r.get('ip_address','N/A'), r.get('orden',''), r.get('timestamp_utc','N/A'), r.get('timestamp_converted','N/A'), r.get('isp','N/A'), r.get('location','N/A'), r.get('hostname','N/A')) for r in prepared_data])
        
        self._populate_chunk(rows_iterator)

    def _populate_chunk(self, rows_iterator: Iterator[tuple], chunk_size: int = 50):
        """Inserta un lote de filas en el TreeView y programa el siguiente lote."""
        try:
            for _ in range(chunk_size):
                row = next(rows_iterator)
                if self.report_tree.winfo_exists():
                    self.report_tree.insert("", tk.END, text=row[0], values=row[1:])
                else:
                    self._populate_job = None # Detener si la ventana se cierra
                    return
            # Programar el siguiente chunk
            self._populate_job = self.after(10, self._populate_chunk, rows_iterator, chunk_size)
        except StopIteration:
            self._populate_job = None # Se insertaron todas las filas
            self.update_status(f"Mostrando {len(self.full_results)} resultados.", "green", duration=4000)
            self.after(100, self._populate_filter_options) # Poblar filtros al final
            logging.getLogger('GUI').info("Poblado de TreeView completado.")
        except tk.TclError:
            self._populate_job = None # Detener si hay error en la GUI
            logging.getLogger('GUI').warning("Error TclError durante poblado de TreeView (ventana cerrada?).")

    def _populate_filter_options(self) -> None:
        if not hasattr(self, 'filter_combo') or not self.filter_combo.winfo_exists(): return
        values = ["Todos"]; countries = set()
        if self.full_results:
            try:
                prep = file_io._prepare_export_data(self.full_results)
                for item in prep:
                    if not item.get('ip_info_error') and item.get('country') and item.get('country') != 'N/A':
                        countries.add(item['country'])
            except Exception as e: logging.getLogger(__name__).error("Error preparando datos filtro", exc_info=True)
        if countries: values.extend(sorted(list(countries)))
        try:
             curr = self.current_filter_country.get(); self.filter_combo.config(values=values)
             self.current_filter_country.set(curr if curr in values else "Todos")
             state = "disabled"
             if len(values) > 1 and not self.is_processing.get(): state = "readonly"
             self.filter_combo.config(state=state)
        except tk.TclError: pass

    def _apply_filter(self, event=None) -> None:
        if not hasattr(self, 'filter_combo') or not self.filter_combo.winfo_exists(): return
        selected = self.current_filter_country.get(); logging.getLogger(__name__).info(f"Aplicando filtro GUI: {selected}")
        if not self.full_results: self._clear_treeview(); return
        try: prep_all = file_io._prepare_export_data(self.full_results)
        except Exception as e: logging.getLogger(__name__).error("Error preparando datos para filtro", exc_info=True); return
        count = 0
        if selected == "Todos":
            self._populate_treeview(self.full_results); count = len(self.full_results)
        else:
            filtered_results = [orig for orig, prep in zip(self.full_results, prep_all) if not prep.get('ip_info_error') and prep.get('country') == selected]
            self._populate_treeview(filtered_results); count = len(filtered_results)
        self.update_status(f"Mostrando {count} resultado{'s' if count != 1 else ''} ({selected}).")
        if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
             try: self.progress_bar['value'] = 0
             except tk.TclError: pass

    def _check_progress_queue(self) -> None:
        if not self.winfo_exists(): # Check if window still exists
             return

        # Handle progress updates
        try:
            while True:
                progress_val = self.progress_queue.get_nowait()
                if isinstance(progress_val, (int, float)):
                    if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                        self.progress_bar['value'] = progress_val
                # Optionally, handle other types of messages if the queue is used for more than just progress
        except Empty:
            pass # No more progress updates for now
        except Exception as e:
            logging.getLogger('GUI').error(f"Error procesando cola progreso: {e}")

        # Handle log updates (existing logic)
        try:
            while True:
                record = self.log_queue.get_nowait()
                self.after_idle(self._update_log_task, record)
        except Empty:
            pass
        except Exception as e:
            logging.getLogger('GUI').error(f"Error procesando cola log: {e}")

        finally:
            if self.winfo_exists() and self.is_processing.get():
                self._progress_check_job = self.after(150, self._check_progress_queue)
            elif self.winfo_exists() and not self.is_processing.get():
                # Ensure progress bar is 100% when processing finishes
                if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                    self.progress_bar['value'] = 100

    def _analysis_task(self, filepath: Path, backend_timezone: str, queue_handler: logging.Handler, file_hash: str, app_version: str) -> None:
        self.full_results = None
        self.analysis_metadata = None # New attribute to store metadata
        analysis_successful = False
        try:
            # Pass the file_hash to the backend processing function
            results_wrapper = processing.process_ip_analysis(
                filepath, backend_timezone, self.gemini_key, self.ipinfo_token,
                self.progress_queue, queue_handler, file_hash, app_version # Pass app_version here
            )
            if results_wrapper is not None and "analysis_results" in results_wrapper and "metadata" in results_wrapper:
                self.full_results = results_wrapper["analysis_results"]
                self.analysis_metadata = results_wrapper["metadata"] # Store metadata
                analysis_successful = True
            else:
                analysis_successful = False # Error ya fue logueado por el backend
        except Exception as e:
            analysis_successful = False; self.full_results = None; self.analysis_metadata = None
            error_msg = f"Error CRÍTICO INESPERADO en HILO GUI: {e}"
            try: logging.getLogger().critical(error_msg, exc_info=True)
            except: print(f"ERROR CRÍTICO (PRINT): {error_msg}\n{traceback.format_exc()}")
            self.after(0, self.update_status, "Error INESPERADO en el análisis.", "red")
        finally:
            self.after(0, self._set_processing_state, False)
            if analysis_successful:
                # Iniciar el poblado asíncrono de la tabla
                self.after(0, self._populate_treeview, self.full_results)
            else:
                 # Si falló, limpiar la tabla y las opciones de filtro
                 self.after(0, self._clear_treeview)
                 self.after(0, self._populate_filter_options)
            self.analysis_thread = None
            # La barra de estado se actualiza al final del poblado o por otros eventos

    def _map_display_tz_to_backend(self, display_tz: str) -> str:
        # El backend ahora maneja la validación, simplemente pasamos la string
        # El mapeo Etc/GMT puede ayudar si el backend no lo hiciera, pero ya lo hace.
        if display_tz == "UTC": return "UTC"
        match = re.fullmatch(r"UTC([+-])(\d{1,2})", display_tz)
        if match:
            sign = match.group(1); offset = int(match.group(2))
            backend_sign = "-" if sign == "+" else "+"; return f"Etc/GMT{backend_sign}{offset}"
        else:
             return display_tz # Podría ser IANA, el backend valida

    def _calculate_file_hash(self, filepath: Path) -> Optional[str]:
        """Calcula el hash SHA256 de un archivo."""
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                # Read and update hash string value in blocks of 4K
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logging.getLogger('GUI').error(f"Error calculando hash para {filepath}: {e}", exc_info=True)
            return None

    def _start_analysis_thread(self) -> None:
        if self.is_processing.get(): messagebox.showwarning("Análisis en Curso", "Ya hay un análisis en proceso.", parent=self); return
        filepath_str = self.input_file_path.get()
        if not filepath_str: messagebox.showerror("Archivo No Seleccionado", "Selecciona un archivo.", parent=self); return
        filepath = Path(filepath_str)
        if not filepath.is_file(): messagebox.showerror("Error de Archivo", f"Archivo inválido:\n{filepath}", parent=self); return
        if not self.api_keys_loaded: messagebox.showerror("Configuración Requerida", "Claves API no cargadas.", parent=self); return

        display_timezone = self.timezone.get(); backend_timezone = self._map_display_tz_to_backend(display_timezone)

        # Calculate SHA256 hash of the input file
        file_hash = self._calculate_file_hash(filepath)
        if file_hash is None:
            messagebox.showerror("Error de Hash", "No se pudo calcular el hash del archivo de entrada.", parent=self)
            return

        self._set_processing_state(True); self.update_status("Iniciando análisis...", "blue")
        self._clear_treeview(); self._clear_log()
        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
        self.update_idletasks()

        # Configurar logger backend para enviar a cola GUI
        backend_logger = logging.getLogger(processing.__name__)
        if self.log_queue_handler and self.log_queue_handler not in backend_logger.handlers:
            backend_logger.addHandler(self.log_queue_handler)
            if backend_logger.level == logging.NOTSET or backend_logger.level > logging.DEBUG:
                 backend_logger.setLevel(logging.DEBUG) # Capturar todo para GUI
            logging.getLogger('GUI').info(f"Handler log GUI añadido a logger backend '{processing.__name__}'. Nivel backend: {backend_logger.getEffectiveLevel()}")

        logging.getLogger('GUI').info(f"Iniciando hilo análisis: {filepath.name}, TZ Backend: {backend_timezone}")
        self.analysis_thread = threading.Thread(
            target=self._analysis_task,
            args=(filepath, backend_timezone, self.log_queue_handler, file_hash, self.title()), daemon=True # Pass file_hash and app_version
        )
        self.analysis_thread.start()
        self.after(100, self._check_progress_queue)

    def _on_closing(self) -> None:
        gui_logger = logging.getLogger('GUI')
        if self.is_processing.get():
            if messagebox.askyesno("Confirmar Salida", "Análisis en proceso.\n¿Seguro que deseas salir?", icon='warning', parent=self):
                gui_logger.info("Saliendo durante análisis.")
                self.destroy()
            else: gui_logger.info("Cierre cancelado."); return
        else: gui_logger.info("Saliendo."); self.destroy()


# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    gui_logger = logging.getLogger('GUI')
    if not gui_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - GUI - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        gui_logger.addHandler(handler)
        gui_logger.setLevel(logging.INFO)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt): sys.__excepthook__(exc_type, exc_value, exc_traceback); return
        logging.getLogger().critical("Error Fatal Inesperado (excepthook)", exc_info=(exc_type, exc_value, exc_traceback))
        try:
             if tk._default_root and tk._default_root.winfo_exists(): messagebox.showerror("Error Fatal", f"Error no capturado:\n{exc_type.__name__}: {exc_value}\nVer consola/log.")
        except Exception as e: print(f"ERROR: No se pudo mostrar messagebox para error fatal: {e}")
    sys.excepthook = handle_exception

    gui_logger.info("Iniciando aplicación IP Analyzer GUI...")
    app = IPAnalyzerApp()
    app.mainloop()
    gui_logger.info("Aplicación cerrada.")

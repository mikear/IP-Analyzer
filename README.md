# IP Analyzer v2.2 ⚡

Herramienta de escritorio y línea de comandos de alta velocidad para la extracción, análisis y enriquecimiento de direcciones IP desde diversas fuentes de texto.

Diseñada para analistas de seguridad e investigadores forenses digitales, la aplicación procesa archivos de texto y genera informes detallados de manera ultra rápida, de forma 100% local y determinista (sin dependencia de servicios de IA externos).

## Características Destacadas
- ⚡ **Extracción Local Determinista Rápida:** Algoritmo local basado en patrones que identifica con precisión direcciones IP (IPv4 e IPv6) y sus marcas de tiempo asociadas en archivos `.txt`, `.docx`, `.csv` y `.log`.
- 🌍 **Enriquecimiento de Datos:** Consulta la API de ipinfo.io para obtener información detallada de cada IP (ISP, geolocalización por ciudad, región, país y hostname). Se puede ejecutar en modo local si no se cuenta con token.
- ⏰ **Conversión de Zona Horaria:** Parsea timestamps en diversos formatos y los convierte a la zona horaria elegida (UTC por defecto).
- 📄 **Informes Detallados:** Genera informes completos en múltiples formatos (`.pdf`, `.csv`, `.json`, `.txt`) que incluyen:
    - Hash SHA256 del archivo de entrada para verificación de integridad.
    - Versión de la aplicación y metadatos del caso (investigador, juzgado/fiscalía, causa).
    - Numeración de páginas y pie de página en reportes PDF.
- 🖥️ **Interfaz Gráfica Moderna (PySide6 / Qt):**
    - Soporte para arrastrar y soltar archivos (Drag & Drop).
    - Búsqueda y filtrado en tiempo real por término o país.
    - Indicador de progreso y consola de log del proceso.
- ⌨️ **CLI Potente:** Interfaz de línea de comandos para automatizar análisis e integración en scripts.

---

## Requisitos del Sistema
- Python 3.8 o superior.
- Conexión a internet opcional para consultas de geolocalización con `ipinfo.io`.

---

## Instalación desde Código Fuente
1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/tu_usuario/tu_repositorio.git
   cd tu_repositorio
   ```

2. **Crea un entorno virtual:**
   ```bash
   python -m venv venv
   # En Windows:
   .\venv\Scripts\activate
   # En Linux/macOS:
   source venv/bin/activate
   ```

3. **Instala las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuración
Para enriquecer las IPs con ISP y ubicación:
1. Obten un token en [ipinfo.io](https://ipinfo.io/signup).
2. Guárdalo mediante el diálogo de la GUI (`Menú Archivo > Gestionar Token IPInfo...`) o creando un archivo `.env` en la raíz con:
   ```env
   IPINFO_TOKEN=tu_token_aqui
   ```

---

## Uso

### 🖥️ Interfaz Gráfica (GUI)
```bash
python src/ip_analyzer_gui.py
```
- Arrastra el archivo al área designada o haz clic en "Seleccionar...".
- Selecciona la zona horaria deseada.
- Opcionalmente añade metadatos del caso.
- Haz clic en **"Iniciar Análisis"**.
- Filtra o busca resultados en la tabla y exporta el informe en PDF, CSV, JSON o TXT.

### ⌨️ Línea de Comandos (CLI)
```bash
python src/main_cli.py "ruta/al/archivo.txt" -o "ruta/informe_salida" -tz "America/Argentina/Buenos_Aires"
```

---

## Licencia
Proyecto bajo Licencia MIT.

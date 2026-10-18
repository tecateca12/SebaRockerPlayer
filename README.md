# SebaRockerPlayer 🎸🥁

**SebaRockerPlayer** es un reproductor de música dual (Backing Track + Click) estilo Winamp diseñado para garantizar **sincronización perfecta a nivel de sample (cero desfasaje)** entre la pista de acompañamiento y el metrónomo/click.

 📖 **¿Buscás cómo usar el programa?** Mirá el **[Manual de Uso Básico (MANUAL_DE_USO.md)](./MANUAL_DE_USO.md)**.

---

## Características Técnicas

- **Sincronía Sample-Accurate (Cero Desfasaje):** Decodifica el archivo de Backing (`* D.wav` / `d.wav`) y el de Click (`* Clic.mp3` / `click.mp3`) en memoria RAM con la misma frecuencia de muestreo (ej. `48 kHz` o `44.1 kHz` nativos) y los mezcla dentro de **un único stream de hardware PortAudio** usando un solo puntero de frame.
- **Auto-Emparejamiento Inteligente:** Al abrir o arrastrar un tema o una carpeta entera, detecta y agrupa automáticamente cada tema con su click correspondiente mostrando un solo elemento limpio en la playlist.
- **Mezclador Independiente:**
  - **Master Volume:** `100%` por defecto (afecta ambas pistas).
  - **Backing Track:** `100%` por defecto + `Mute (M)` y `Solo (S)`.
  - **Click Track:** **`60%` por defecto** + `Mute (M)` y `Solo (S)`, con memoria automática por canción.
- **Multiplataforma:** Compatible con **macOS** y **Windows**.

---

## Requisitos Previos

- **Python 3.10 o superior** instalado en el sistema.
- En Windows: marcar la casilla *"Add Python to PATH"* durante la instalación de Python.

---

## 1. Ejecutar desde Código Fuente (Desarrollo)

### En macOS / Linux:
```bash
git clone https://github.com/tecateca12/SebaRockerPlayer.git
cd SebaRockerPlayer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

### En Windows (PowerShell o CMD):
```bat
git clone https://github.com/tecateca12/SebaRockerPlayer.git
cd SebaRockerPlayer
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

---

## 2. Cómo Compilar la App (Generar Ejecutable)

El proyecto incluye scripts automáticos con **PyInstaller** que empaquetan todo (Python, interfaz gráfica y librerías de audio) en una aplicación lista para usar sin consola.

### 🍎 Compilar en macOS (`SebaRockerPlayer.app`)

1. Abrí la Terminal en la carpeta del proyecto y ejecutá:
   ```bash
   chmod +x build/build_mac.sh
   ./build/build_mac.sh
   ```
2. Al finalizar, vas a encontrar la aplicación lista en:
   ```text
   dist/SebaRockerPlayer.app
   ```
3. Podés arrastrar `SebaRockerPlayer.app` directamente a tu carpeta **Aplicaciones (`Applications`)**.

---

### 🪟 Compilar en Windows (`SebaRockerPlayer.exe`)

1. En Windows, entrá a la carpeta `build` y hacé doble clic en **`build_win.bat`** (o ejecutalo desde CMD/PowerShell):
   ```bat
   build\build_win.bat
   ```
2. El script creará automáticamente el entorno virtual (si no existe), instalará las dependencias y compilará todo en un único archivo ejecutable:
   ```text
   dist\SebaRockerPlayer.exe
   ```
3. Podés copiar `SebaRockerPlayer.exe` al Escritorio o a cualquier PC con Windows sin necesidad de instalar Python.

---

## 3. Ejecutar Tests Automatizados

```bash
.venv/bin/python -m unittest discover -s tests -v
```

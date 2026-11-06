# SebaRockerPlayer v0.2 🎸🥁📝

**SebaRockerPlayer** es un reproductor musical dual (**Backing Track + Click**) con **Teleprompter compatible con LivePrompter (`.txt`)**, diseñado para garantizar **sincronización perfecta a nivel de sample (cero desfasaje)** en **Android (Tablet y Mobile)**, **macOS** y **Windows**.

📖 **¿Buscás cómo usar el programa?** Mirá el **[Manual de Uso Básico (MANUAL_DE_USO.md)](./MANUAL_DE_USO.md)**.

---

## Novedades de la versión v0.2

1. **Soporte para Android (Tablet y Mobile `.apk`):**
   - Proyecto Android nativo en `android/` optimizado para **Tablets** (vista dividida + Modo Escenario a pantalla completa y pantalla siempre encendida `KEEP_SCREEN_ON`) y celulares.
2. **Auto-Emparejamiento Triple (`D.wav` + `Clic.mp3` + `L.txt`):**
   - Al abrir un tema o una carpeta, empareja automáticamente:
     - Backing: `<Tema> D.wav` *(o `d.wav`, `.mp3`, `.flac`)*
     - Click: `<Tema> Clic.mp3` *(o `click.mp3`, `.wav`)*
     - Letra: `<Tema> L.txt` *(formato LivePrompter)*
3. **Teleprompter estilo LivePrompter:**
   - Lee `{duration:mm:ss}` del archivo `.txt` (o usa la duración del audio si no está presente) y scrollea suavemente la letra de principio a fin sincronizada al reloj del audio.
   - Resalta estribillos (`{soc}` ... `{eoc}`), soporta timestamps precisos (`{d_time:...}`), pausas (`{pause:...}`), zoom de texto (`A-` / `A+`) y botón **`⛶ Modo Escenario`**.

---

## 1. Ejecutar en Desarrollo (macOS / Windows / Linux)

```bash
git clone https://github.com/tecateca12/SebaRockerPlayer.git
cd SebaRockerPlayer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

---

## 2. Cómo Compilar para cada Plataforma

### 🍎 Compilar en macOS (`SebaRockerPlayer.app`)
```bash
chmod +x build/build_mac.sh
./build/build_mac.sh
```
Genera la aplicación en `dist/SebaRockerPlayer.app`.

### 🪟 Compilar en Windows (`SebaRockerPlayer.exe`)
```bat
build\build_win.bat
```
Genera el ejecutable portable en `dist\SebaRockerPlayer.exe`.

### 🤖 Compilar para Android Tablet / Mobile (`SebaRockerPlayer-Android.apk`)
Requiere JDK 17 y Android SDK (API 34), o se compila automáticamente en la nube con **GitHub Actions** en cada Release:
```bash
cd android
gradle assembleRelease
```
El instalador `.apk` firmado queda listo para instalar en cualquier Tablet o celular Android en:
`android/app/build/outputs/apk/release/app-release.apk`.

---

## 3. Ejecutar Tests Automatizados

```bash
.venv/bin/python -m unittest discover -s tests -v
```

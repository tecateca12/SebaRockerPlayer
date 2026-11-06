# Manual de Uso Básico — SebaRockerPlayer v0.2 🎸🥁📝

**SebaRockerPlayer** reproduce tus **Backing Tracks**, su **Click** y scrollea la **Letra (`.txt`)** al mismo tiempo con sincronía exacta en **Android (Tablet / Celular)**, **Mac** y **Windows**.

---

## 1. ¿Cómo deben llamarse los archivos?

Para que el reproductor cargue el click y la letra automáticamente cuando abrís un tema o una carpeta, los archivos deben estar en la misma carpeta y respetar este formato:

- **Pista de Backing:** `<Nombre del Tema> D.wav` *(o `d.wav`, `.mp3`, `.flac`)*
- **Pista de Click:** `<Nombre del Tema> Clic.mp3` *(o `click.mp3`, `.wav`)*
- **Archivo de Letra (LivePrompter):** `<Nombre del Tema> L.txt` *(o `l.txt`)*

**Ejemplo real:**
- `Mensaka - Agosto D.wav`
- `Mensaka - Agosto Clic.mp3`
- `Mensaka - Agosto L.txt`

En la playlist vas a ver un solo renglón llamado **`Mensaka - Agosto`** con los indicadores **`🎯 OK`** (Click cargado) y **`📝 OK`** (Letra cargada).

---

## 2. Cómo funciona el Teleprompter de Letras (`L.txt`)

El lector de letras es compatible con tus archivos `.txt` de **LivePrompter**:

- **Velocidad de Scroll automática (`{duration:mm:ss}`):**
  - Si el archivo `.txt` tiene la etiqueta `{duration:02:35}`, la letra va a scrollear suavemente de principio a fin en exactamente `02:35` al darle **Play**.
  - Si un `.txt` no tiene `{duration:...}`, usa automáticamente la duración total del archivo de audio.
- **Estribillos resaltados (`{soc}` y `{eoc}`):**
  - Todo el texto entre `{soc}` y `{eoc}` aparece destacado con una barra lateral naranja y letra en negrita.
- **Timestamps intermedios (`{d_time:...}`) y Pausas (`{pause:...}`):**
  - Si tu archivo usa marcas `{d_time:seconds}` o `{pause:seconds}`, el scroll ajusta su velocidad para pasar por esa línea en el segundo exacto.
- **Botones para el escenario (Ideales para Tablet):**
  - **`A-` / `A+`**: Achica o agranda el tamaño de la letra al instante.
  - **`⛶ Modo Escenario`**: Oculta la playlist y el mezclador para que **la letra ocupe toda la pantalla** mientras tocás en vivo.

---

## 3. Cómo cargar canciones en Tablet Android, Mac o Windows

1. **Botón `📁 Carpeta`:**
   - Seleccioná la carpeta de un disco o la carpeta entera de tu banda (busca también adentro de subcarpetas) y carga todos los temas con su click y su letra listos para tocar.
2. **Botón `➕ Tema(s)`:**
   - Elegí los archivos sueltos y el programa los empareja automáticamente.
3. **Arrastrar y Soltar (en Mac y Windows):**
   - Arrastrá cualquier archivo o carpeta directamente adentro de la ventana.

---

## 4. Mezclador y Modos de Reproducción

- **🟢 MASTER (`100%`):** Sube o baja ambas pistas juntas.
- **🔵 BACKING TRACK (`100%`):** Volumen solo de la pista + botones `M` (Mute) y `S` (Solo).
- **🟠 CLICK TRACK (`60%` por defecto):** Volumen solo del click + botones `M` (Mute) y `S` (Solo). Si lo cambiás en un tema, queda guardado en memoria para ese tema.
- **🔄 Modo Continuo (Winamp) vs 🛑 Modo Vivo:** Tocando el botón de modo elegís si al terminar un tema pasa solo al siguiente o si frena esperando a que le des Play.

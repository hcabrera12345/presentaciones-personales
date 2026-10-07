# Demo en vivo: un agente de IA para "Asuntos Centrales"

**Qué muestra:** se le da a un agente de IA una entrevista del canal y, sin edición humana, entrega:

- **5 titulares picantes**, cada uno con su **captura de pantalla estilo noticia** (1280×720, lista para miniatura o post)
- **3 clips cortos verticales** (1080×1920, para Shorts, Reels o TikTok) con el mismo estilo: gancho arriba, subtítulos animados palabra por palabra y la marca del canal
- un **reporte HTML** para mostrar todo en pantalla

```
URL de YouTube ─► 1. descarga ─► 2. transcribe ─► 3. Claude decide ─► 4. capturas ─► 5. clips ─► 6. reporte
                   (yt-dlp)      (Whisper local)   titulares + clips    (Pillow)        (ffmpeg)    (HTML)
```

---

## 1. Preparación (el día anterior)

```bash
# Python 3.10+ y ffmpeg instalados
#   Windows: winget install ffmpeg   ·   Mac: brew install ffmpeg   ·   Linux: apt install ffmpeg
cd demo-agente-video
pip install -r requirements.txt

# Clave de la API de Claude (console.anthropic.com)
export ANTHROPIC_API_KEY="sk-ant-..."        # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

**Ensayo completo** con la entrevista que se va a usar:

```bash
python agente_asuntos_centrales.py "https://www.youtube.com/watch?v=XXXXXXXX"
```

Al final abre `salida/XXXXXXXX/reporte.html`.

### Tiempos aproximados

La transcripción es lo único lento. En una laptop sin GPU, el modelo `small` tarda entre un tercio y la mitad de la duración del video.

| Paso | Entrevista de 15 min | Entrevista de 60 min |
|---|---|---|
| Descarga | ~30 s | ~1–2 min |
| Transcripción (`small`, CPU) | ~5 min | ~20–30 min |
| Análisis con Claude | ~1 min | ~1–2 min |
| Capturas + 3 clips | ~1 min | ~1 min |

**Para el vivo:** usa una entrevista de 10–20 minutos, o deja la transcripción hecha antes (ver la estrategia de abajo). Con `--whisper base` es unas 2–3 veces más rápido, con un poco menos de precisión.

---

## 2. Estrategia para que no falle en vivo

El agente guarda cada paso en la carpeta de salida (`video.mp4`, `transcripcion.json`, `analisis.json`) y **reutiliza lo que ya existe**. Eso permite tres modos de demo:

| Modo | Qué se hace antes | Qué se ve en vivo | Duración en vivo |
|---|---|---|---|
| **A. Seguro** (recomendado) | Descarga + transcripción | Claude pensando y proponiendo, capturas y clips generándose | ~2–3 min |
| **B. Total** | Nada | Todo, desde la URL | depende del largo del video |
| **C. Respaldo** | Todo | Solo abrir `reporte.html` | 0 min |

**Modo A:** ejecuta el agente completo el día anterior. Antes de salir al aire, borra lo que quieres que se genere en vivo:

```bash
cd salida/XXXXXXXX
rm analisis.json            # Windows: del analisis.json
rm -r titulares clips reporte.html
```

En vivo, el mismo comando vuelve a correr: salta descarga y transcripción y hace en directo la parte visible (Claude decide y se generan las piezas). Como Claude no responde dos veces igual, los titulares serán **nuevos** respecto al ensayo, y eso también se puede contar en la demo.

> Guarda una copia de la carpeta del ensayo (modo C) por si falla internet.

---

## 3. Guion sugerido (≈8 minutos)

**0:00 · Gancho**
> "Esta entrevista dura 45 minutos. Un editor tarda medio día en sacarle titulares, miniaturas y clips. Vamos a ver qué hace un agente de IA en tres minutos."

**0:30 · Mostrar el video original** en YouTube (unos segundos).

**1:00 · Lanzar el agente** (copiar la URL y ejecutar):
```bash
python agente_asuntos_centrales.py "https://www.youtube.com/watch?v=XXXXXXXX"
```
Mientras corre, narrar los pasos que aparecen en la terminal (`▶ PASO 1 … PASO 6`).

**2:00 · El momento clave: PASO 3.** Explicar qué le pedimos a Claude:
> "No le pedimos solo 'hazme títulos'. Le dimos el estilo del canal (cintillo rojo, verbos fuertes, cifras) y una regla innegociable: **picante pero verdadero**. Cada titular tiene que estar respaldado por una frase literal del entrevistado, y el agente nos la muestra."

Cuando aparezcan los 5 titulares en la terminal, leerlos en voz alta.

**4:00 · Abrir `reporte.html`.**
- Las 5 capturas: el agente buscó el fotograma más nítido en el instante exacto de la cita y le puso el estilo de noticia.
- Debajo de cada una, la **cita textual** y el minuto: se puede comprobar.
- Reproducir 1 o 2 clips verticales: subtítulos palabra por palabra y el gancho arriba.

**6:00 · Cierre / mensaje**
> "El agente no reemplaza al editor: le entrega 5 opciones y 3 clips en minutos, y el editor elige, corrige y publica. Lo que antes era medio día de trabajo ahora es una revisión de 10 minutos."

**Preguntas típicas**
- *¿Inventa cosas?* No debería: el prompt lo prohíbe y cada titular trae su cita literal y el minuto para verificarla. Aun así, una persona revisa antes de publicar.
- *¿Cuánto cuesta?* Una entrevista de una hora son unos 15–20 mil tokens de entrada. Son centavos de dólar por video en la API de Claude; la transcripción corre gratis en la propia computadora.
- *¿Funciona con cualquier video?* Sí: cualquier URL que soporte yt-dlp o un archivo local (`.mp4`, `.mov`…).

---

## 4. Alternativa: hacerlo "conversando" con Claude Code

Para mostrar a un agente que razona y usa herramientas por su cuenta, abre Claude Code en esta carpeta y escribe:

> Toma esta entrevista del canal Asuntos Centrales: https://www.youtube.com/watch?v=XXXXXXXX
> Quiero 5 titulares picantes con su captura de pantalla estilo noticia y 3 clips cortos verticales con el mismo estilo. Usa el agente `agente_asuntos_centrales.py`, revisa que cada titular esté respaldado por lo que realmente dijo el entrevistado y muéstrame el resultado.

Claude Code ejecuta el script, lee `analisis.json`, comprueba las citas y puede corregir algún titular si se lo pides en vivo (por ejemplo: *"haz el titular 3 más agresivo"* o *"cambia el clip 2 por el momento donde habla del litio"*). Después basta con volver a correr el script para regenerar las piezas.

---

## 5. Personalización rápida

En `agente_asuntos_centrales.py`:

| Qué | Dónde |
|---|---|
| Nombre del canal en las piezas | `CANAL = "ASUNTOS CENTRALES"` |
| Colores (rojo, amarillo) | `ROJO`, `AMARILLO` |
| Estilo editorial y reglas | texto `SISTEMA` |
| Tipografía | `--fuente-letra ruta/a/fuente.ttf` (por defecto busca Arial Black, Impact o Inter Black) |
| Calidad de transcripción | `--whisper base / small / medium / large-v3` |

### Archivos que genera

```
salida/<video>/
├── reporte.html              ← abrir esto en la demo
├── titulares/titular_1..5.jpg
├── clips/clip_1..3.mp4
├── analisis.json             ← lo que decidió Claude (titulares, citas, tiempos)
├── transcripcion.json
└── video.mp4
```

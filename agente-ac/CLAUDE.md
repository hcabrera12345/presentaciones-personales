# Contexto para Claude Code

Agente de IA de contenido para el canal de noticias **Asuntos Centrales** (Bolivia), desarrollado por
Quinto Eje Ingeniería. Uso interno: lo usan el gerente (aprueba) y el equipo de producción.

## Qué hace
Entrevista o streaming (YouTube del canal, otros canales, archivo, documento o enlace) → transcripción →
Claude propone 5 titulares con captura estilo noticia, 3 clips verticales, nota y artes → el equipo revisa
en el panel → el gerente aprueba por WhatsApp (constancia por email) → se publica en Facebook y se
archiva en Google Drive.

## Reglas que no se negocian
- **Picante pero verdadero.** Toda pieza lleva una `cita_textual` que se verifica contra la transcripción
  (`agente/verificacion.py`). Si la cita no aparece, la pieza no se crea. No relajar esta regla.
- **Nada se publica sin aprobación humana.** El agente propone; el gerente decide.
- El material de otros canales (`videos.solo_analisis = true`) nunca se publica.
- Toda acción de un usuario se registra en `auditoria` (`app.db.auditar`).
- Las credenciales viven solo en variables de entorno del servidor; nunca en el código ni en el navegador
  (excepto `SUPABASE_ANON_KEY`, que es pública por diseño).
- No generar imágenes de personas reales con IA: las piezas usan fotogramas reales del video.

## Stack
Python 3.12 · FastAPI + Jinja (panel) · PostgreSQL/Auth/Storage en Supabase · cola en PostgreSQL
(`FOR UPDATE SKIP LOCKED`) · trabajador en Render · Claude (`claude-opus-5-5`, configurable con
`CLAUDE_MODELO`) vía SDK `anthropic` con salidas estructuradas · Whisper vía Groq · ffmpeg + Pillow ·
yt-dlp con proxy residencial (YouTube bloquea IPs de nube) · APIs oficiales de Meta.

## Convenciones
- Código, nombres y comentarios en español, como el resto del proyecto.
- De YouTube se descarga solo el audio y tramos cortos (`agente/medios.Fuente`): el proxy cobra por GB.
- Cambios de esquema: nueva migración numerada en `supabase/migrations/`, nunca editar una ya aplicada.
- Antes de cerrar un cambio: `TEST_DATABASE_URL=... pytest` en verde.

## Plan del mes 1
- Semana 1: documentos PDF/Word y enlaces web como entrada; subida reanudable de archivos grandes;
  probar login, Groq, Storage y proxy con las cuentas reales.
- Semana 2: artes con plantillas (cita destacada, titular, carrusel); ajuste de estilo con ejemplos del
  canal (`estilo_canal`); re-generar la captura al editar un titular.
- Semana 3: `integraciones/` — WhatsApp (aviso + botones + webhook), email de constancia, Drive y
  publicación en Facebook con el token del usuario del sistema.
- Semana 4: marcha blanca con 10 entrevistas reales, monitoreo (errores y costo por trabajo), capacitación.

## Criterios de aceptación
Entrevista de 90 min procesada en menos de 20 min · 5 titulares + 3 clips + 1 nota + 2 artes ·
cero citas inventadas en la marcha blanca · aprobación por WhatsApp y publicación en Facebook funcionando.

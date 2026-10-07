# Agente de IA de contenido · Asuntos Centrales

Sistema interno que toma entrevistas y streamings del canal (o archivos) y propone titulares con
captura estilo noticia, clips verticales y una nota periodística. El equipo revisa en un panel web,
el gerente aprueba por WhatsApp y lo aprobado se publica en Facebook y se archiva en Drive.

Desarrollado por **Quinto Eje Ingeniería**.

## Arquitectura

```
Navegador ──► Panel web (FastAPI, Render) ──► PostgreSQL / Auth / Storage (Supabase)
                                                   ▲
YouTube (proxy) ─► Trabajador (Render) ────────────┘──► Claude (análisis) · Groq (transcripción)
                    cola en PostgreSQL                  Meta: WhatsApp + Facebook · Google Drive
```

| Carpeta | Contenido |
|---|---|
| `agente/` | Núcleo: transcripción, análisis con Claude, verificación de citas, diseño de piezas, medios |
| `app/` | Panel web, API, autenticación, base de datos y cola de trabajos |
| `worker/` | Trabajador: procesa la cola y detecta publicaciones nuevas del canal |
| `integraciones/` | WhatsApp, Facebook, Drive y email (semana 3) |
| `supabase/migrations/` | Esquema de la base de datos |
| `tests/` | Pruebas automáticas |

## Puesta en marcha local

Requisitos: Python 3.12+, ffmpeg y un proyecto de Supabase (o PostgreSQL local para pruebas).

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                  # completar las claves de DESARROLLO

# Base de datos: pegar supabase/migrations/0001_esquema_inicial.sql en el SQL Editor de Supabase

uvicorn app.main:app --reload       # panel en http://localhost:8000
python -m worker.main               # trabajador (otra terminal)
```

Con `AUTH_DESACTIVADA=true` (solo en desarrollo) se entra al panel sin login.

## Pruebas

```bash
pytest                                          # pruebas sin servicios externos
TEST_DATABASE_URL=postgresql://... pytest       # incluye base de datos, cola, panel y flujo completo
```

`TEST_DATABASE_URL` debe apuntar a una base **desechable**: las pruebas borran y recrean el esquema.

## Despliegue

1. Supabase: crear el proyecto (región São Paulo), ejecutar la migración, activar el proveedor
   **Google** en Authentication y agregar `https://<dominio>/login` como URL de redirección.
2. Render: **New → Blueprint** con este repositorio (lee `render.yaml`), y cargar los secretos en
   el Environment Group `agente-ac`.
3. Dominio: apuntar `agente.<dominio-del-canal>` al servicio web de Render.
4. Primer administrador: entrar una vez con Google y luego, en el SQL Editor de Supabase:
   ```sql
   update perfiles set rol = 'admin', activo = true where email = 'correo@ejemplo.com';
   ```

## Estado (base del proyecto)

| Componente | Estado |
|---|---|
| Esquema de base de datos, roles y RLS | ✅ Probado |
| Cola de trabajos con reintentos | ✅ Probado |
| Panel: ingresar enlace o archivo, ver, editar, descartar, regenerar | ✅ Probado |
| Trabajador: transcripción → Claude → verificación de citas → capturas → clips → nota | ✅ Probado con servicios simulados |
| Detección automática de publicaciones nuevas | ✅ Lectura del feed probada |
| Login con Google (Supabase Auth) | Implementado, falta probar con el proyecto real |
| Transcripción Groq, Storage y descarga por proxy | Implementado, falta probar con claves reales |
| Documentos PDF/Word y enlaces web como entrada | Pendiente (semana 1) |
| Subida reanudable de archivos grandes | Pendiente (semana 1) |
| Artes con plantillas | Pendiente (semana 2) |
| WhatsApp, email, Drive y Facebook | Pendiente (semana 3) |

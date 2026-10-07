-- Esquema inicial del Agente de IA de contenido de Asuntos Centrales.
-- El backend y el trabajador se conectan con el rol del servidor (omite RLS);
-- las políticas RLS protegen el acceso directo desde el navegador.

create extension if not exists pgcrypto;

-- ───────── Tipos ─────────
create type rol_usuario      as enum ('admin', 'gerente', 'produccion');
create type origen_material  as enum ('youtube', 'archivo', 'documento', 'enlace');
create type estado_video     as enum ('en_cola', 'procesando', 'listo', 'en_aprobacion',
                                      'aprobado', 'publicado', 'rechazado', 'error');
create type tipo_pieza       as enum ('titular', 'clip', 'nota', 'arte', 'texto_red');
create type estado_pieza     as enum ('propuesta', 'editada', 'aprobada', 'descartada', 'publicada');
create type estado_trabajo   as enum ('pendiente', 'en_proceso', 'completado', 'fallido');
create type decision_aprob   as enum ('aprobado', 'cambios', 'rechazado');

-- ───────── Usuarios (perfil de cada cuenta de Supabase Auth) ─────────
create table perfiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text not null unique,
  nombre      text,
  whatsapp    text,
  rol         rol_usuario not null default 'produccion',
  activo      boolean not null default false,   -- un admin activa cada cuenta nueva
  creado_en   timestamptz not null default now()
);

-- Cada vez que alguien entra con Google por primera vez se crea su perfil, inactivo.
create function crear_perfil() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.perfiles (id, email, nombre)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'full_name', new.email))
  on conflict (id) do nothing;
  return new;
end $$;

create trigger al_crear_usuario after insert on auth.users
  for each row execute function crear_perfil();

-- ───────── Material de entrada ─────────
create table videos (
  id            uuid primary key default gen_random_uuid(),
  origen        origen_material not null,
  url           text,
  youtube_id    text unique,
  archivo_ruta  text,                      -- ruta en Storage si fue subido
  titulo        text not null default '',
  invitado      text,
  resumen       text,
  duracion_s    numeric,
  solo_analisis boolean not null default false,  -- material de otros canales: no se publica
  estado        estado_video not null default 'en_cola',
  error         text,
  creado_por    uuid references perfiles (id),
  creado_en     timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);
create index videos_estado_idx on videos (estado, creado_en desc);

create table transcripciones (
  video_id    uuid primary key references videos (id) on delete cascade,
  idioma      text not null default 'es',
  proveedor   text not null,
  segmentos   jsonb not null,
  texto       text not null,
  creado_en   timestamptz not null default now()
);

-- ───────── Lo que produce el agente ─────────
create table piezas (
  id            uuid primary key default gen_random_uuid(),
  video_id      uuid not null references videos (id) on delete cascade,
  tipo          tipo_pieza not null,
  orden         int not null default 0,
  contenido     jsonb not null,             -- titular, cita, segundo, gancho, texto de la nota…
  archivo_ruta  text,                       -- captura, clip o arte en Storage
  cita_verificada boolean not null default false,
  estado        estado_pieza not null default 'propuesta',
  version       int not null default 1,
  editado_por   uuid references perfiles (id),
  creado_en     timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);
create index piezas_video_idx on piezas (video_id, tipo, orden);

create table aprobaciones (
  id            uuid primary key default gen_random_uuid(),
  video_id      uuid not null references videos (id) on delete cascade,
  canal         text not null check (canal in ('whatsapp', 'panel')),
  decision      decision_aprob,
  comentario    text,
  solicitado_a  uuid references perfiles (id),
  decidido_por  uuid references perfiles (id),
  solicitado_en timestamptz not null default now(),
  decidido_en   timestamptz
);

create table publicaciones (
  id            uuid primary key default gen_random_uuid(),
  pieza_id      uuid not null references piezas (id) on delete cascade,
  red           text not null default 'facebook',
  estado        text not null default 'pendiente' check (estado in ('pendiente', 'publicada', 'error')),
  programada_para timestamptz,
  id_externo    text,
  url           text,
  error         text,
  publicado_en  timestamptz,
  creado_en     timestamptz not null default now()
);

-- ───────── Estilo editorial (versionado, editable sin tocar código) ─────────
create table estilo_canal (
  id            serial primary key,
  instrucciones text not null default '',
  activo        boolean not null default false,
  creado_por    uuid references perfiles (id),
  creado_en     timestamptz not null default now()
);
create unique index un_estilo_activo on estilo_canal (activo) where activo;
insert into estilo_canal (instrucciones, activo) values ('', true);

-- ───────── Cola de trabajos (la consume el trabajador con SKIP LOCKED) ─────────
create table trabajos (
  id            bigserial primary key,
  video_id      uuid references videos (id) on delete cascade,
  tipo          text not null,
  datos         jsonb not null default '{}',
  estado        estado_trabajo not null default 'pendiente',
  intentos      int not null default 0,
  max_intentos  int not null default 3,
  programado_para timestamptz not null default now(),
  iniciado_en   timestamptz,
  terminado_en  timestamptz,
  error         text,
  tokens_entrada int,
  tokens_salida  int,
  costo_usd     numeric(10, 4),
  creado_en     timestamptz not null default now()
);
create index trabajos_pendientes_idx on trabajos (programado_para) where estado = 'pendiente';

-- ───────── Auditoría: quién hizo qué y cuándo ─────────
create table auditoria (
  id          bigserial primary key,
  usuario_id  uuid references perfiles (id),
  accion      text not null,
  entidad     text not null,
  entidad_id  text,
  detalle     jsonb not null default '{}',
  creado_en   timestamptz not null default now()
);
create index auditoria_entidad_idx on auditoria (entidad, entidad_id);

-- ───────── Seguridad a nivel de fila ─────────
-- Lectura solo para usuarios activos; toda escritura pasa por el backend.
create function es_usuario_activo() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from perfiles where id = auth.uid() and activo)
$$;

alter table perfiles        enable row level security;
alter table videos          enable row level security;
alter table transcripciones enable row level security;
alter table piezas          enable row level security;
alter table aprobaciones    enable row level security;
alter table publicaciones   enable row level security;
alter table estilo_canal    enable row level security;
alter table trabajos        enable row level security;
alter table auditoria       enable row level security;

create policy perfil_propio on perfiles for select using (id = auth.uid() or es_usuario_activo());
create policy lectura_videos on videos for select using (es_usuario_activo());
create policy lectura_transcripciones on transcripciones for select using (es_usuario_activo());
create policy lectura_piezas on piezas for select using (es_usuario_activo());
create policy lectura_aprobaciones on aprobaciones for select using (es_usuario_activo());
create policy lectura_publicaciones on publicaciones for select using (es_usuario_activo());
create policy lectura_estilo on estilo_canal for select using (es_usuario_activo());
-- trabajos y auditoria: sin políticas de lectura → solo el backend los ve.

-- ───────── Almacenamiento ─────────
insert into storage.buckets (id, name, public) values ('medios', 'medios', false)
  on conflict (id) do nothing;

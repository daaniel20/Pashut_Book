-- Task 1.3: where the bot keeps orders and photos.
-- Already applied to the Supabase project "pashut-book" (Nov 22, 2026).
-- Kept here as a record, and so the database can be rebuilt elsewhere.

-- One row per album order. A customer's "current" order is their newest one.
create table public.orders (
  id           uuid primary key default gen_random_uuid(),
  phone        text not null,                    -- the customer's WhatsApp number
  status       text not null default 'collecting'
               check (status in ('collecting', 'ready', 'cancelled')),
  step         text not null default 'new',      -- where they are in the conversation
  design       text,
  title        text,
  photo_count  integer not null default 0,
  notes        jsonb not null default '[]'::jsonb, -- messages already sent once
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index orders_phone_created_idx on public.orders (phone, created_at desc);

-- One row per saved photo. The photo itself is in the private "photos" bucket.
create table public.photos (
  id            uuid primary key default gen_random_uuid(),
  order_id      uuid not null references public.orders (id) on delete cascade,
  number        integer not null,                -- 1, 2, 3… in the order received
  wa_media_id   text not null unique,            -- WhatsApp's ID (stops double saving)
  storage_path  text not null,                   -- e.g. <order id>/001.jpg
  mime_type     text not null,
  size_bytes    integer not null,
  created_at    timestamptz not null default now(),
  unique (order_id, number)
);

-- Lock the tables: only the bot's secret key can read or write them.
-- (Row Level Security on, with no rules = the public "publishable" key sees nothing.)
alter table public.orders enable row level security;
alter table public.photos enable row level security;
revoke all on public.orders, public.photos from anon, authenticated;

-- A PRIVATE storage bucket: photos never get a public link.
-- Up to 50 MB per photo (the free plan's maximum), images only.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', false, 52428800,
        array['image/*']);

-- Task 3.3: the order history. One row for every moment of every order
-- (a new step, a photo saved, the album built, a change, the owner's answer…).
-- Numbers and short codes only: never photos, message texts or phone numbers.
-- Run once in Supabase: SQL Editor -> New query -> paste all of this -> Run.
-- (See docs/setup/3.3-order-history.md, step 1.)

create table if not exists public.order_events (
  id          bigint generated always as identity primary key,
  -- Which order. No link that deletes rows with the order: the history stays
  -- even after an order and its photos are cleaned up (task 3.4).
  order_id    uuid not null,
  event       text not null,     -- what happened, e.g. "step", "album_built", "photo_saved"
  step        text,              -- the conversation step at that moment
  photos      integer,           -- how many photos the order had then
  count       integer,           -- the event's main number (photo number, pages, …)
  detail      text,              -- a short code: the new step, "small", "kept", …
  info        jsonb not null default '{}'::jsonb,   -- more numbers, e.g. {"seconds": 41}
  created_at  timestamptz not null default now()
);
create index if not exists order_events_order_idx on public.order_events (order_id, created_at);
create index if not exists order_events_time_idx on public.order_events (created_at);

-- Locked like the other tables: only the bot's secret key can read or write.
alter table public.order_events enable row level security;
revoke all on public.order_events from anon, authenticated;


-- The history, easy to read and to download as a CSV: each order's rows
-- together, oldest order first, with the time since the order started and
-- since the previous row (in seconds), and the order's short code (the
-- first 8 characters, as in the bot's log and the owner's messages).
create or replace view public.order_history with (security_invoker = true) as
select
  left(e.order_id::text, 8)                                           as order_code,
  e.created_at,
  e.event,
  e.detail,
  e.count,
  e.step,
  e.photos,
  round(extract(epoch from e.created_at - min(e.created_at) over o))::int  as seconds_from_start,
  round(extract(epoch from e.created_at - lag(e.created_at) over w))::int  as seconds_since_previous,
  e.info,
  e.order_id,
  e.id
from public.order_events e
window o as (partition by e.order_id),
       w as (partition by e.order_id order by e.created_at, e.id)
order by min(e.created_at) over o, e.order_id, e.created_at, e.id;

revoke all on public.order_history from anon, authenticated;


-- One row per order: the main numbers at a glance (for a spreadsheet).
-- Minutes are counted from the order's start.
create or replace view public.order_summary with (security_invoker = true) as
with ev as (
  select order_id,
         min(created_at)                                                       as started,
         min(created_at) filter (where event = 'step' and detail = 'done')      as summary_at,
         min(created_at) filter (where event = 'previews_sent')                 as first_preview_at,
         min(created_at) filter (where event = 'preview_ok')                    as loved_at,
         min(created_at) filter (where event = 'approved')                      as approved_at,
         min(created_at) filter (where event = 'payment_wait')                  as payment_asked_at,
         min(created_at) filter (where event = 'step' and detail = 'paid')      as paid_at,
         count(*) filter (where event = 'photo_saved')                          as photos_saved,
         count(*) filter (where event = 'photo_saved'
                            and (info->>'without_hd')::boolean)                as photos_without_hd,
         round(sum((info->>'kb')::numeric) filter (where event = 'photo_saved') / 1024, 1)
                                                                                as photos_mb,
         count(*) filter (where event = 'photo_failed')                         as photos_failed,
         count(*) filter (where event = 'album_built')                          as builds,
         count(*) filter (where event like 'used\_%' and event <> 'used_ship_fix') as changes,
         count(*) filter (where event in ('removed', 'replaced'))               as photo_changes,
         count(*) filter (where event = 'owner_msgs')                           as messages_to_owner,
         count(*) filter (where event = 'help_wait')                            as help_asked,
         count(*) filter (where event = 'hd_asked')                             as hd_asked,
         count(*) filter (where event = 'cover_problem')                        as cover_problems
  from public.order_events
  group by order_id
),
last_build as (
  select distinct on (order_id) order_id, count as pages,
         (info->>'photos_in_album')::int as photos_in_album,
         (info->>'full_pages')::int      as full_pages,
         (info->>'seconds')::numeric     as build_seconds
  from public.order_events
  where event = 'album_built'
  order by order_id, created_at desc, id desc
)
select
  left(o.id::text, 8)                                              as order_code,
  o.created_at                                                     as started,
  o.status,
  o.step,
  o.design,
  o.title is not null and o.title <> ''                            as has_title,
  o.photo_count,
  ev.photos_saved,
  ev.photos_without_hd,
  ev.photos_mb,
  ev.photos_failed,
  b.pages,
  b.photos_in_album,
  b.full_pages,
  ev.builds,
  b.build_seconds,
  ev.changes,
  ev.photo_changes,
  ev.hd_asked,
  ev.cover_problems,
  ev.messages_to_owner,
  ev.help_asked,
  round(extract(epoch from ev.summary_at - ev.started) / 60, 1)       as minutes_to_summary,
  round(extract(epoch from ev.first_preview_at - ev.started) / 60, 1) as minutes_to_preview,
  round(extract(epoch from ev.loved_at - ev.started) / 60, 1)         as minutes_to_love,
  round(extract(epoch from ev.approved_at - ev.loved_at) / 60, 1)     as minutes_owner_approval,
  round(extract(epoch from ev.paid_at - ev.payment_asked_at) / 60, 1) as minutes_to_pay,
  o.price,
  o.ship_city,
  o.id                                                             as order_id
from public.orders o
left join ev on ev.order_id = o.id
left join last_build b on b.order_id = o.id
order by o.created_at;

revoke all on public.order_summary from anon, authenticated;

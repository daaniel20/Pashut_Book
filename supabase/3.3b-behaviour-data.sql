-- Task 3.3b: behaviour data. Adds 3 columns to the order history and ready-made
-- views for studying how customers use the bot (funnel, drop-off, friction,
-- weekly trends, repeat customers). Numbers and codes only.
-- Run once in Supabase: SQL Editor -> New query -> paste all of this -> Run.
-- Safe to run again. (See docs/setup/3.3b-behaviour-data.md.)

-- ---------- 1. New columns on every history row ----------
alter table public.order_events
  add column if not exists customer text,      -- anonymous customer key (scrambled phone)
  add column if not exists test     boolean,   -- true = the owner's or family's test phone
  add column if not exists version  text;      -- the bot's version, e.g. "2026-11-26.e83a816"

-- Everything recorded before this task was a test (no real customers yet).
update public.order_events set test = true where test is null;

create index if not exists order_events_event_idx on public.order_events (event, created_at);
create index if not exists order_events_customer_idx on public.order_events (customer);


-- ---------- 2. One row per order: how far it got (the base for the views below) ----------
-- Each "reached_…" column is true if the order ever got to that stage.
create or replace view public.order_stages with (security_invoker = true) as
select st.*,
  -- The furthest stage reached (1-11). Later stages count as having passed the
  -- earlier ones (orders from before 3.3 don't have every moment recorded).
  case
    when st.reached_paid        then 11
    when st.reached_address     then 10
    when st.reached_approved    then 9
    when st.reached_loved       then 8
    when st.reached_opened      then 7
    when st.reached_link        then 6
    when st.reached_summary     then 5
    when st.reached_photos_done then 4
    when st.reached_photos      then 3
    when st.reached_design      then 2
    else 1
  end                                                                     as furthest_stage_no
from (
select
  o.id                                                                    as order_id,
  left(o.id::text, 8)                                                     as order_code,
  o.created_at                                                            as started,
  date_trunc('week', o.created_at)::date                                  as week,
  o.status,
  o.step                                                                  as last_step,
  coalesce(bool_or(e.test), true)                                         as test,
  case when coalesce(bool_or(e.test), true) then 'tests' else 'customers' end as who,
  (array_agg(e.detail order by e.created_at, e.id) filter (where e.event = 'source'))[1]
                                                                          as source,
  max(e.customer)                                                         as customer,
  (array_agg(e.version order by e.created_at, e.id) filter (where e.version is not null))[1]
                                                                          as version,
  o.photo_count,
  true                                                                    as reached_started,
  o.design is not null
    or coalesce(bool_or(e.event = 'step' and e.info->>'from' = 'design'), false)
                                                                          as reached_design,
  o.photo_count > 0
    or coalesce(bool_or(e.event = 'message_in' and e.detail = 'photo'), false)
                                                                          as reached_photos,
  coalesce(bool_or(e.event = 'step' and e.detail in ('cover', 'title', 'done')), false)
    or o.step in ('cover', 'title', 'done')                               as reached_photos_done,
  coalesce(bool_or(e.event = 'step' and e.detail = 'done'), false)
    or o.status in ('ready', 'approved', 'paid')                          as reached_summary,
  coalesce(bool_or(e.event = 'previews_sent'), false)                     as reached_link,
  coalesce(bool_or(e.event = 'album_opened' and e.detail <> 'owner'), false)
                                                                          as reached_opened,
  coalesce(bool_or(e.event = 'preview_ok'), false)                        as reached_loved,
  coalesce(bool_or(e.event = 'approved'), false)
    or o.status in ('approved', 'paid')                                   as reached_approved,
  coalesce(bool_or(e.event = 'payment_wait'), false)                      as reached_address,
  o.status = 'paid'                                                       as reached_paid,
  max(e.created_at) filter (where e.event = 'message_in')                 as last_message_at,
  max(e.created_at)                                                       as last_event_at,
  o.updated_at
from public.orders o
left join public.order_events e on e.order_id = o.id
group by o.id
) st;

revoke all on public.order_stages from anon, authenticated;


-- ---------- 3. The funnel: how many orders reached each stage ----------
-- "who" = customers or tests. percent_of_started / percent_of_previous show
-- where people stop. (An album started over counts as its own order.)
create or replace view public.funnel with (security_invoker = true) as
with stages(stage_no, stage) as (values
    (1, 'started'), (2, 'chose a design'), (3, 'sent photos'), (4, 'finished photos'),
    (5, 'summary'), (6, 'got the link'), (7, 'opened the link'), (8, 'loved it'),
    (9, 'owner approved'), (10, 'gave the address'), (11, 'paid')),
counts as (
  select w.who, st.stage_no, st.stage,
         count(s.order_id) filter (where s.furthest_stage_no >= st.stage_no) as orders
  from (select distinct who from public.order_stages) w
  cross join stages st
  left join public.order_stages s on s.who = w.who
  group by w.who, st.stage_no, st.stage
)
select who, stage_no, stage, orders,
       round(100.0 * orders / nullif(first_value(orders) over w, 0))       as percent_of_started,
       round(100.0 * orders / nullif(lag(orders) over w, 0))               as percent_of_previous
from counts
window w as (partition by who order by stage_no)
order by who, stage_no;

revoke all on public.funnel from anon, authenticated;


-- ---------- 4. Drop-off: unpaid orders, where they stopped and how long ago ----------
create or replace view public.drop_off with (security_invoker = true) as
select
  s.order_code,
  s.who,
  s.source,
  s.started,
  s.last_step,
  (array['started', 'chose a design', 'sent photos', 'finished photos', 'summary',
          'got the link', 'opened the link', 'loved it', 'owner approved',
          'gave the address', 'paid'])[s.furthest_stage_no]               as furthest_stage,
  (select e.event from public.order_events e
    where e.order_id = s.order_id
      and e.event not in ('message_out', 'message_delivered', 'message_read')
    order by e.created_at desc, e.id desc limit 1)                        as last_event,
  coalesce(s.last_message_at, s.updated_at)                               as last_customer_message,
  round(extract(epoch from now() - coalesce(s.last_message_at, s.updated_at)) / 3600, 1)
                                                                          as hours_since,
  s.photo_count,
  s.status,
  s.order_id
from public.order_stages s
where not s.reached_paid
order by coalesce(s.last_message_at, s.updated_at) desc;

revoke all on public.drop_off from anon, authenticated;


-- ---------- 5. Friction: signs that something was hard, per order ----------
-- confused = typed text where a button was expected, and nothing changed.
create or replace view public.friction with (security_invoker = true) as
select
  s.order_code,
  s.who,
  s.started,
  s.last_step,
  count(*) filter (where e.event = 'message_in')                              as messages_in,
  count(*) filter (where e.event = 'message_in' and e.detail = 'text')        as texts,
  count(*) filter (where e.event = 'message_in' and (e.info->>'confused')::boolean)
                                                                              as confused,
  count(*) filter (where e.event = 'message_in' and not (e.info->>'changed')::boolean
                     and e.detail <> 'photo')                                 as changed_nothing,
  count(*) filter (where e.event = 'help_wait')                               as help_asked,
  count(*) filter (where e.event = 'owner_msgs')                              as messages_to_owner,
  count(*) filter (where e.event = 'hd_asked')                                as hd_asked,
  count(*) filter (where e.event = 'photos_deleted_for_hd')                   as hd_resent,
  count(*) filter (where e.event = 'cover_problem')                           as cover_problems,
  count(*) filter (where e.event = 'message_out'
                     and e.detail in ('change_limit', 'owner_limit', 'new_album_limit'))
                                                                              as limits_reached,
  count(*) filter (where e.event = 'photo_failed')                            as photos_failed,
  count(*) filter (where e.event in ('album_failed', 'previews_not_sent'))     as bot_failures,
  count(*) filter (where e.event = 'message_failed')                          as messages_failed,
  count(*) filter (where e.event = 'message_out')                             as messages_out,
  count(*) filter (where e.event = 'message_read')                            as messages_read,
  percentile_cont(0.5) within group (order by (e.info->>'seconds')::numeric)
    filter (where e.event = 'message_read')                                   as median_seconds_to_read,
  s.order_id
from public.order_stages s
left join public.order_events e on e.order_id = s.order_id
group by s.order_id, s.order_code, s.who, s.started, s.last_step
order by s.started;

revoke all on public.friction from anon, authenticated;


-- ---------- 6. Weekly trends ----------
create or replace view public.weekly_trends with (security_invoker = true) as
select
  s.week,
  s.who,
  count(*)                                                     as orders,
  count(*) filter (where s.furthest_stage_no >= 5)              as reached_summary,
  count(*) filter (where s.furthest_stage_no >= 6)              as got_link,
  count(*) filter (where s.furthest_stage_no >= 8)              as loved,
  count(*) filter (where s.reached_paid)                       as paid,
  round(100.0 * count(*) filter (where s.reached_paid) / count(*))     as percent_paid,
  round(avg(s.photo_count) filter (where s.reached_summary), 1)        as avg_photos,
  round(avg(f.confused), 2)                                            as avg_confused,
  round(avg(f.help_asked), 2)                                          as avg_help,
  count(distinct s.customer)                                           as customers,
  string_agg(distinct s.source, ', ')                                  as sources,
  min(s.version)                                                       as first_version,
  max(s.version)                                                       as last_version
from public.order_stages s
join public.friction f on f.order_id = s.order_id
group by s.week, s.who
order by s.week, s.who;

revoke all on public.weekly_trends from anon, authenticated;


-- ---------- 7. Customers (by anonymous key): repeat customers ----------
create or replace view public.customers with (security_invoker = true) as
select
  s.customer,
  bool_or(s.test)                                              as test,
  count(*)                                                     as orders,
  count(*) filter (where s.furthest_stage_no >= 5)              as albums_finished,
  count(*) filter (where s.reached_paid)                       as albums_paid,
  min(s.started)                                               as first_order,
  max(s.started)                                               as last_order,
  string_agg(distinct s.source, ', ')                          as sources
from public.order_stages s
where s.customer is not null
group by s.customer
order by min(s.started);

revoke all on public.customers from anon, authenticated;


-- ---------- 8. The album page: visits per order ----------
create or replace view public.album_page_visits with (security_invoker = true) as
select
  left(e.order_id::text, 8)                                                   as order_code,
  bool_or(e.test)                                                             as test,
  count(*) filter (where e.event = 'album_opened' and e.detail <> 'owner')    as opens,
  count(distinct e.info->>'device') filter (where e.detail <> 'owner')        as devices,
  count(*) filter (where e.event = 'album_opened' and e.detail = 'phone')     as opens_on_phone,
  count(*) filter (where e.event = 'album_opened' and e.detail = 'computer')  as opens_on_computer,
  count(*) filter (where e.event = 'album_opened' and e.detail = 'owner')     as owner_opens,
  max(e.count) filter (where e.event = 'album_seen' and e.detail <> 'owner')  as max_scroll_percent,
  max((e.info->>'seconds')::int) filter (where e.event = 'album_seen' and e.detail <> 'owner')
                                                                              as longest_visit_seconds,
  min(e.created_at) filter (where e.event = 'album_opened' and e.detail <> 'owner')
                                                                              as first_open,
  e.order_id
from public.order_events e
where e.event in ('album_opened', 'album_seen')
group by e.order_id
order by min(e.created_at);

revoke all on public.album_page_visits from anon, authenticated;

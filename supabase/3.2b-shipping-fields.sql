-- Task 3.2 (after the owner's phone test, Nov 26, 2026): the shipping details
-- as separate fields, asked one by one, instead of one "address" message.
-- Run once in Supabase: SQL Editor -> New query -> paste all of this -> Run.

alter table public.orders
  add column if not exists ship_name   text,   -- the person who gets the album
  add column if not exists ship_street text,   -- street and house number (and flat, floor)
  add column if not exists ship_city   text,   -- the city (useful for the owner's data)
  add column if not exists ship_phone  text;   -- the courier's number, 05X-XXX-XXXX

-- The single-message address from the first 3.2 build is no longer used
-- (it only held test data).
alter table public.orders drop column if exists shipping_address;

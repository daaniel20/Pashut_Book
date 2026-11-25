-- Task 3.2: the shipping address, the price and the payment of each order.
-- Run once in Supabase: SQL Editor -> New query -> paste all of this -> Run.
-- (See docs/setup/3.2-photo-changes-and-payment.md, step 1.)

alter table public.orders
  add column if not exists shipping_address text,          -- typed by the customer, for the courier
  add column if not exists price            integer,       -- what the customer pays, in shekels (album + shipping)
  add column if not exists paid_at          timestamptz;   -- when the owner tapped "payment received"

-- Two new statuses: "approved" (the owner approved; address and payment next)
-- and "paid" (the owner received the money; the album goes to print).
alter table public.orders drop constraint if exists orders_status_check;
alter table public.orders add constraint orders_status_check
  check (status in ('collecting', 'ready', 'approved', 'paid', 'cancelled'));

-- Basket Watch — database schema.
--
-- Run this once in the Supabase SQL editor (Dashboard → SQL → New query).
-- It is written to be re-runnable: every object is created only if missing.
--
-- Two rules shape everything here:
--   1. A receipt photo is never stored. Only the numbers read off it live in
--      these tables.
--   2. Row Level Security is the real access control. A user can only ever see
--      their own rows, enforced by Postgres itself — a bug in the application
--      cannot leak one customer's receipts to another.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- profiles --
-- One row per signed-up person, carrying their plan. auth.users is Supabase's
-- own table; we never write to it.
create table if not exists public.profiles (
  id                  uuid primary key references auth.users(id) on delete cascade,
  email               text,
  plan                text not null default 'free' check (plan in ('free', 'pro')),
  plan_status         text not null default 'active' check (plan_status in ('active', 'past_due', 'cancelled')),
  plan_renews_at      timestamptz,
  billing_provider    text,
  billing_customer_id text,
  created_at          timestamptz not null default now()
);

-- A profile appears the moment someone signs up, whatever the sign-up method.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- receipts --
create table if not exists public.receipts (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  merchant_name   text not null,
  merchant_slug   text not null,
  branch          text,
  purchased_at    timestamptz not null,
  currency        text not null default 'ILS',
  total           numeric(12,2) not null,
  vat_amount      numeric(12,2),
  vat_rate        numeric(5,4),
  items_count     integer,
  document_number text,
  created_at      timestamptz not null default now()
);

-- Scanning the same bill twice should update it, not double it.
create unique index if not exists receipts_natural_key
  on public.receipts (user_id, merchant_slug, purchased_at, total);
create index if not exists receipts_by_user_date
  on public.receipts (user_id, purchased_at desc);

-- ----------------------------------------------------------- receipt_items --
-- The line items are their own table on purpose: every comparison in the app
-- (price per kg, same product across stores, the basket index) runs over lines,
-- not over receipts.
create table if not exists public.receipt_items (
  id          bigserial primary key,
  receipt_id  uuid not null references public.receipts(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  line        integer not null,
  barcode     text,
  name        text not null,
  name_en     text,
  category    text not null,
  quantity    numeric(12,3) not null,
  unit        text not null,
  unit_price  numeric(12,2) not null,
  total       numeric(12,2) not null,
  -- normalised to a comparable basis: per kg, per litre or per item
  base_price  numeric(12,4),
  base_qty    numeric(12,4),
  base_unit   text,
  product_key text,
  confidence  numeric(3,2)
);

create index if not exists items_by_user on public.receipt_items (user_id);
create index if not exists items_by_product on public.receipt_items (user_id, product_key);

-- ------------------------------------------------------------- scan_events --
-- Quota accounting and cost telemetry. One row per scan attempt, successful or
-- not, so spend can be traced per user without touching their receipts.
create table if not exists public.scan_events (
  id            bigserial primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  created_at    timestamptz not null default now(),
  ok            boolean not null,
  model         text,
  input_tokens  integer,
  output_tokens integer,
  cost_usd      numeric(10,5),
  error         text
);

create index if not exists scan_events_by_user_month
  on public.scan_events (user_id, created_at desc);

-- ------------------------------------------------------------ price_points --
-- The anonymous layer: what a product cost at a shop on a day. No user_id, no
-- link back to a person — this is what makes the app worth more as more people
-- use it, without any of them being identifiable in it.
create table if not exists public.price_points (
  id            bigserial primary key,
  product_key   text not null,
  barcode       text,
  name          text,
  merchant_slug text not null,
  observed_on   date not null,
  base_price    numeric(12,4) not null,
  base_unit     text not null,
  created_at    timestamptz not null default now()
);

create unique index if not exists price_points_unique
  on public.price_points (product_key, merchant_slug, observed_on);

-- ---------------------------------------------------------------- policies --
alter table public.profiles      enable row level security;
alter table public.receipts      enable row level security;
alter table public.receipt_items enable row level security;
alter table public.scan_events   enable row level security;
alter table public.price_points  enable row level security;

drop policy if exists "own profile"        on public.profiles;
drop policy if exists "own profile update" on public.profiles;
drop policy if exists "own receipts"       on public.receipts;
drop policy if exists "own items"          on public.receipt_items;
drop policy if exists "own scan events"    on public.scan_events;
drop policy if exists "read prices"        on public.price_points;

-- Read your own profile; change nothing about your own plan (only the billing
-- webhook, which runs with the service key, may do that).
create policy "own profile" on public.profiles
  for select using (auth.uid() = id);
create policy "own profile update" on public.profiles
  for update using (auth.uid() = id)
  with check (auth.uid() = id and plan = (select plan from public.profiles p where p.id = auth.uid()));

create policy "own receipts" on public.receipts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own items" on public.receipt_items
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Usage is readable by its owner and written only by the server.
create policy "own scan events" on public.scan_events
  for select using (auth.uid() = user_id);

-- Everyone signed in reads the shared price index; only the server writes it.
create policy "read prices" on public.price_points
  for select to authenticated using (true);

-- ----------------------------------------------------------------- helpers --
-- Scans used in the current calendar month, for the quota check.
create or replace function public.scans_this_month(uid uuid)
returns integer
language sql
stable
security definer set search_path = public
as $$
  select count(*)::int
  from public.scan_events
  where user_id = uid
    and ok
    and created_at >= date_trunc('month', now());
$$;

-- ==========================================================
-- PWMU AI Control Room — Supabase Schema
-- Supabase Dashboard -> SQL Editor me isko run karo.
-- ==========================================================

-- 0. User profiles (extra fields beyond Supabase Auth's email/password)
create table if not exists profiles (
    id          uuid primary key references auth.users(id) on delete cascade,
    name        text not null,
    pwm_unit    text not null,
    district    text not null,
    email       text not null,
    created_at  timestamptz not null default now()
);

alter table profiles enable row level security;
-- Users can read/update only their own profile row
create policy "Users read own profile" on profiles for select using (auth.uid() = id);
create policy "Users update own profile" on profiles for update using (auth.uid() = id);
-- Sign-up insert happens via service_role from the backend, which bypasses RLS —
-- but this policy lets it also work if you ever call it with the anon key from a
-- logged-in session:
create policy "Users insert own profile" on profiles for insert with check (auth.uid() = id);

-- 1. Number plate detections
create table if not exists plate_detections (
    id            bigint generated always as identity primary key,
    plate_number  text not null,
    confidence    numeric,
    image_url     text,
    detected_at   timestamptz not null default now(),
    created_at    timestamptz not null default now()
);

create index if not exists idx_plate_detected_at on plate_detections (detected_at desc);

-- 2. Thief / loitering / unattended-object alerts
create table if not exists thief_alerts (
    id            bigint generated always as identity primary key,
    reason        text not null,               -- 'LOITERING THREAT!' or 'UNATTENDED OBJECT!'
    tracked_ids   text,                          -- stringified list of track IDs in zone
    image_url     text,
    detected_at   timestamptz not null default now(),
    created_at    timestamptz not null default now()
);

create index if not exists idx_thief_detected_at on thief_alerts (detected_at desc);

-- 3. (Optional) Waste segregation session summary — agar aage chal ke
--    per-session waste counts bhi DB me store karne ho to yeh use karo.
create table if not exists waste_sessions (
    id            bigint generated always as identity primary key,
    class_label   text not null,
    count         integer not null default 0,
    session_at    timestamptz not null default now()
);

-- ==========================================================
-- Row Level Security (RLS) — demo ke liye simple "allow all" policy.
-- Production me service_role key backend se use karo (jaisa is app me hai),
-- to RLS bypass ho jaata hai — yeh policies sirf anon/public access ke liye hain
-- agar tum frontend se direct Supabase client use karoge.
-- ==========================================================
alter table plate_detections enable row level security;
alter table thief_alerts enable row level security;
alter table waste_sessions enable row level security;

create policy "Allow read for all" on plate_detections for select using (true);
create policy "Allow insert for all" on plate_detections for insert with check (true);

create policy "Allow read for all" on thief_alerts for select using (true);
create policy "Allow insert for all" on thief_alerts for insert with check (true);

create policy "Allow read for all" on waste_sessions for select using (true);
create policy "Allow insert for all" on waste_sessions for insert with check (true);

-- ==========================================================
-- STORAGE BUCKETS
-- SQL se bucket nahi bantа reliably har Supabase version me — agar insert
-- fail ho jaye, manually banao: Storage -> New Bucket -> Public: ON
--   1. pwmu-captures       (legacy/shared bucket)
--   2. anpr-detections     (number plate images)
--   3. security-detections (theft/anomaly alert images)
-- ==========================================================
insert into storage.buckets (id, name, public) values
    ('pwmu-captures', 'pwmu-captures', true),
    ('anpr-detections', 'anpr-detections', true),
    ('security-detections', 'security-detections', true)
on conflict (id) do nothing;

-- CRITICAL: a "public" bucket only means public READ. Uploads (INSERT) are
-- still blocked by Storage RLS unless you add a policy OR use the
-- service_role key (which bypasses RLS entirely — recommended for this
-- backend-only Flask app, since the key never reaches the browser).
-- Run these too, in case you're using the anon key instead:
create policy "Public read - pwmu captures" on storage.objects for select using (bucket_id = 'pwmu-captures');
create policy "Allow uploads - pwmu captures" on storage.objects for insert with check (bucket_id = 'pwmu-captures');

create policy "Public read - anpr" on storage.objects for select using (bucket_id = 'anpr-detections');
create policy "Allow uploads - anpr" on storage.objects for insert with check (bucket_id = 'anpr-detections');

create policy "Public read - security" on storage.objects for select using (bucket_id = 'security-detections');
create policy "Allow uploads - security" on storage.objects for insert with check (bucket_id = 'security-detections');

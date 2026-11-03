-- database/changes.sql
-- Changes made in the Supabase SQL editor after schema.sql was written, in the order they were applied.
-- This is a RECORD, not a script to re-run: the statements aren't idempotent (adding a column twice fails).
-- ORDER MATTERS: rpe is retyped before e1rm exists, because Postgres refuses to change the type
-- of a column that a generated column reads.

-- 0. to_kgs existed before this file; recorded here because the generated columns depend on it.
--    GOTCHA: a NULL unit falls into ELSE and is returned unchanged, i.e. treated as kg.
--    So weight_kgs / e1rm are only meaningful for rows whose weight_unit is set (the comp lifts).
--    A second overload for numeric inputs also exists; its body wasn't checked.
create or replace function public.to_kgs(value double precision, unit text)
returns double precision
language sql
immutable      -- generated columns require this
as $$
  select case when unit = 'lbs' then value / 2.20462 else value end;
$$;

-- 1. sessions: tie each session to its program week and record its day within that week.
--    present_date becomes optional, because migrated data has no real calendar dates.
alter table sessions add column program_week_id uuid references program_weeks(id);
alter table sessions add column day_number int;
alter table sessions alter column present_date drop not null;

-- 2. pipeline_rejects: quarantine table for rows the pipeline can't load.
--    Created but not written to yet; rejected rows only exist in memory during a run.
create table pipeline_rejects (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients(id),
    source_file text not null,
    tab_name text,
    block_number int,
    week_number int,
    day_number int,
    field_name text not null,
    raw_value text,                  -- text on purpose: the value failed to fit its real type
    rejection_reason text not null,
    created_at timestamptz not null default now()
);

-- 3. session_exercises: the source sheets don't say primary vs accessory, so role is filled in later.
alter table session_exercises alter column exercise_role drop not null;

-- 4. training_log.rpe: half-point RPEs (6.5, 7.5) don't fit an integer column.
--    The existing CHECK (rpe between 1 and 10) is unchanged and still rejects anything outside 1-10.
alter table training_log alter column rpe type numeric(3,1);

-- 5. training_log: fields the spreadsheet can't always supply are allowed to be null.
--    Unreadable loads (like '4 plates') keep a null weight and move the raw text into notes.
alter table training_log alter column set_type drop not null;
alter table training_log alter column weight_value drop not null;

-- 6. training_log: the coach's prescribed values, stored as informational fields.
alter table training_log add column prescribed_rpe numeric(3,1);
alter table training_log add column prescribed_backoff_pct numeric(5,2);   -- percent below the top set

-- 7. training_log: derived columns, recomputed automatically when weight, unit, reps, or rpe change.
--    The unit has to be set before weight_kgs and e1rm mean anything.
alter table training_log add column weight_kgs float
    generated always as (to_kgs(weight_value, weight_unit)) stored;
alter table training_log add column volume_kgs float
    generated always as (to_kgs(weight_value, weight_unit) * reps) stored;
alter table training_log add column e1rm float      -- Brzycki with RPE-to-RIR adjustment
    generated always as (
        to_kgs(weight_value, weight_unit) * 36 / nullif(37 - (reps + (10 - rpe)), 0)  -- nullif avoids divide-by-zero
    ) stored;

-- 8. Data cleanup (not schema): exercise names had an invisible trailing newline, which broke exact matching.
update exercises set name = trim(both E' \t\n\r' from name);

-- Constraints that exist and are relevant (unchanged by the above):
--   training_log.set_type    check in ('Top Set', 'Backdown')   -- null passes; the pipeline sends null
--   training_log.rpe         check between 1 and 10
--   training_log.weight_unit check in ('kg', 'lbs')
--   session_exercises        unique (session_id, exercise_id)
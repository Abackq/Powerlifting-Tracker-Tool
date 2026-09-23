-- ============================================================
-- SCHEMA — Powerlifting Tracker
-- Run order matters: functions before the tables that call them,
-- and tables before other tables that reference them via foreign key.
-- ============================================================


-- ============ Functions ============

-- Converts a weight value into kg, regardless of which unit it was
-- originally entered in. Used by training_log's generated columns
-- (weight_kgs, volume_kgs, e1rm) so the kg/lbs conversion logic exists
-- in exactly one place, instead of being duplicated in every column
-- that needs a weight in kg. training_log is kg-canonical to match
-- how intermediate lifters typically track lifted weight.
CREATE OR REPLACE FUNCTION to_kgs(value float, unit text)
RETURNS float
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN unit = 'lbs' THEN value / 2.20462
    ELSE value
  END;
$$;

-- Converts a weight value into lbs. Used by body_metrics'
-- bodyweight_lbs generated column — bodyweight is lbs-canonical for
-- this business (opposite of training_log), since bodyweight is
-- predominantly tracked in lbs while lifted weight is tracked in kg.
CREATE OR REPLACE FUNCTION to_lbs(value float, unit text)
RETURNS float
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN unit = 'kg' THEN value * 2.20462
    ELSE value
  END;
$$;


-- ============ clients ============
-- One row per client. Top of the reference chain — every other table
-- eventually traces back to here, directly or through a join chain.

CREATE TABLE clients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- This row's own identity. Other tables reference clients(id), NOT
  -- clients.auth_user_id — that's a separate link (client -> login).

  auth_user_id uuid UNIQUE REFERENCES auth.users(id) NOT NULL,
  -- Points to a row in auth.users (Supabase's built-in login table).
  -- UNIQUE = one login can only ever be linked to one client row.
  -- NOT NULL — clients always sign up first, then create their profile
  -- (self-service onboarding), so a client row never exists without
  -- a real login behind it.

  first_name text,
  last_name text,

  gender character,
  -- Fixed single character ('M'/'F') — intentional, not free text.

  weightclass_kgs float,
  federation text,
  start_date date,
  goals text,
  notes text
);


-- ============ exercises ============
-- Shared reference list of every liftable movement. Admin-managed —
-- clients never create or edit rows here, only reference them.

CREATE TABLE exercises (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  name text UNIQUE,
  -- UNIQUE so the same exercise can't accidentally get inserted twice
  -- under slightly different names.

  -- category values: 'Competition Lift' (Squat/Bench/Deadlift ->
  -- triggers Volume/Est1RM), 'Accessory' (everything else). CHECK
  -- locks this to exactly two values so a typo can never silently
  -- break downstream Volume/Est1RM logic.
  category text CHECK (category in ('Competition Lift', 'Accessory')),

  equipment text CHECK (equipment in ('Barbell', 'Machine', 'Dumbbell', 'Cable', 'Squat Safety Bar', 'Body Weight'))
);


-- ============ sessions ============
-- One row = one training day for one client. Actual exercises/sets
-- live in training_log (via session_exercises), not here — this table
-- just marks "this client trained on this date."

CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  client_id uuid REFERENCES clients(id) NOT NULL,
  -- Links this session to the client who trained it.

  present_date date NOT NULL
  -- Required, but auto-filled by the app (defaults to today) — low
  -- friction in practice. Needed for the program_weeks date-range JOIN.
  -- Note: this table originally also had a manual "week" column,
  -- later dropped once program_weeks could derive week via date range
  -- instead — single source of truth, no redundant manual entry.
);


-- ============ session_exercises ============
-- Bridge table connecting sessions and exercises, with the exercise's
-- role in that specific session attached to the pairing itself. Exists
-- so exercise_role is decided once per exercise-per-session (e.g.
-- "Squat = Primary today"), instead of being repeated on every
-- individual set in training_log.

CREATE TABLE session_exercises (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  session_id uuid REFERENCES sessions(id) NOT NULL,
  exercise_id uuid REFERENCES exercises(id) NOT NULL,

  exercise_role text CHECK (exercise_role in ('Primary', 'Secondary', 'Tertiary', 'Quaternary')) NOT NULL,

  UNIQUE (session_id, exercise_id)
  -- Prevents the same exercise from being tagged twice within one
  -- session with conflicting roles. Unlike program_weeks, there's no
  -- legitimate "repeat" case here — a duplicate would always be a
  -- mistake, never an intentional redo.
);


-- ============ training_log ============
-- One row = one individual set. References session_exercises (not
-- sessions/exercises directly) — this means exercise_role is inherited
-- automatically from session_exercises for every set, rather than
-- needing to be re-entered on each individual row.

CREATE TABLE training_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  session_exercise_id uuid REFERENCES session_exercises(id) NOT NULL,

  set_number int,
  reps int,

  rpe int CHECK (rpe between 1 and 10),
  -- Nullable — e.g. accessory work you don't always track RPE on.
  -- e1rm will just come out null for that row too, no error.

  weight_value float,
  -- The raw number the user typed in, in whichever unit they picked.

  weight_unit text CHECK (weight_unit in ('kg', 'lbs')),

  notes text,

  weight_kgs float GENERATED ALWAYS AS (to_kgs(weight_value, weight_unit)) STORED,
  -- Canonical value, always in kg. Stored (not recomputed downstream)
  -- because it needs to be safely summed/averaged across many rows in
  -- Power BI without every consumer re-implementing the kg/lbs branch.

  volume_kgs float GENERATED ALWAYS AS (to_kgs(weight_value, weight_unit) * reps) STORED,

  -- Brzycki formula w/ RPE->RIR adjustment: effective_reps = reps + (10 - rpe)
  -- Meaningful for Competition Lift rows; computed for all rows regardless —
  -- filter by exercises.category at query time (JOIN), not here, since
  -- generated columns can't see across tables.
  e1rm float GENERATED ALWAYS AS (
    to_kgs(weight_value, weight_unit) * 36 / (37 - (reps + (10 - rpe)))
  ) STORED,

  set_type text CHECK (set_type in ('Top Set', 'Backdown')) NOT NULL
);


-- ============ program_weeks ============
-- Coach- or self-programmer-populated. Defines the date range each
-- program week covers, so sessions/nutrition_log/body_metrics/
-- sleep_metrics can all derive "which week is this?" via a date-range
-- JOIN, instead of each table needing its own manually-entered week
-- column. Writable by the user, not just a coach — this system also
-- serves self-programming lifters who know their own block dates.

CREATE TABLE program_weeks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  client_id uuid REFERENCES clients(id) NOT NULL,

  block int NOT NULL,
  -- Which training block this is. Needed because week resets every
  -- block (back to 1 after week 4/8) — without block, no way to tell
  -- Block 1 Week 1 apart from Block 2 Week 1 for the same client.

  week int NOT NULL,

  repeat_number int NOT NULL DEFAULT 1,
  -- 1 = first time doing this block/week. 2+ = a repeat. Lets analysis
  -- tell an original week's performance apart from a repeat, instead
  -- of blending both into one data point.

  week_start_date date NOT NULL,
  week_end_date date NOT NULL
  -- No UNIQUE constraint on (client_id, block, week) — repeats are
  -- expected and intentional. What actually prevents ambiguity is that
  -- repeats happen at later, non-overlapping dates, so a session's
  -- date only ever matches one program_weeks row at query time.
);


-- ============ nutrition_log ============
-- One row = one nutrition entry. Clients can log once a day as a
-- single 'Daily Total', or split across multiple entries per day.
-- App should show a disclaimer: pick one style per day, don't mix
-- 'Daily Total' with other entries the same day, or totals double-count.

CREATE TABLE nutrition_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  client_id uuid REFERENCES clients(id) NOT NULL,

  present_date date NOT NULL,

  meal_type text CHECK (meal_type in ('Breakfast', 'Lunch', 'Dinner', 'Snack', 'Pre-Workout', 'Post-Workout', 'Rest of Day', 'Daily Total')),
  -- Nullable — optional categorization, not structural identity.

  calories int,
  carbs_grams int,
  protein_grams int,
  fats_grams int,
  -- All nullable. Real usage is messy — eating out, estimating, or
  -- just not logging some days. AVG()/SUM() in Power BI skip nulls
  -- automatically rather than treating them as zero.

  notes text
);


-- ============ body_metrics ============
-- One row = one bodyweight check-in. Separate from nutrition_log since
-- bodyweight is logged on its own cadence, independent of meals.

CREATE TABLE body_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  client_id uuid REFERENCES clients(id) NOT NULL,

  present_date date NOT NULL,

  bodyweight_value float,
  bodyweight_unit text CHECK (bodyweight_unit in ('kg', 'lbs')),

  bodyweight_lbs float GENERATED ALWAYS AS (to_lbs(bodyweight_value, bodyweight_unit)) STORED
  -- Canonical value, always in lbs (opposite of training_log, which
  -- is kg-canonical) — bodyweight is predominantly tracked in lbs
  -- for this business.
);


-- ============ sleep_metrics ============
-- One row = one sleep check-in, logged once a day, independent of
-- training/nutrition/bodyweight.

CREATE TABLE sleep_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  client_id uuid REFERENCES clients(id) NOT NULL,

  present_date date NOT NULL,

  hours_slept float,
  -- Nullable — a client may skip logging sleep some days.

  sleep_quality int CHECK (sleep_quality between 1 and 5)
  -- Subjective 1-5 rating, 5 = best.
);

-- ============================================================
-- RLS POLICIES — Powerlifting Tracker
-- Every table enforces "you only see/touch your own data" via
-- Supabase's auth.uid(), which returns the currently logged-in
-- user's id. Tables without a direct auth_user_id column look it
-- up through clients first (shallow join), or through one or more
-- additional tables for anything further removed (nested join).
--
-- Verified end-to-end via Supabase's Role-impersonation feature in
-- the SQL Editor: two test clients + test data confirmed each client
-- can only see their own rows across clients, sessions, training_log
-- (via session_exercises), and program_weeks. One real bug was found
-- and fixed during testing: session_exercises initially had RLS
-- enabled with zero policies, which silently blocked training_log's
-- policy from working at all, since its subquery reads from
-- session_exercises. Lesson: a policy can be logically correct and
-- still fail if a table it depends on has no policies of its own.
--
-- Access pattern per table is deliberate, not uniform:
--   - clients: full CRUD (self-service signup + profile management)
--   - sessions / session_exercises / training_log / program_weeks /
--     nutrition_log / body_metrics / sleep_metrics: SELECT, INSERT,
--     UPDATE — no DELETE, since logged data should be correctable,
--     not removable
--   - exercises: SELECT open to any authenticated user (shared
--     reference list) — no INSERT/UPDATE/DELETE for regular users,
--     admin-only
--
-- Admin/coach access (you, via Power BI or the SQL Editor) bypasses
-- RLS entirely by connecting through Supabase's elevated
-- service-role key, not through any policy exception here.
-- ============================================================


-- ============ clients ============
-- Direct auth_user_id column — no subquery needed.

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

CREATE POLICY clients_select_own ON clients
FOR SELECT
USING (auth_user_id = auth.uid());

CREATE POLICY clients_insert_own ON clients
FOR INSERT
WITH CHECK (auth_user_id = auth.uid());

CREATE POLICY clients_update_own ON clients
FOR UPDATE
USING (auth_user_id = auth.uid())
WITH CHECK (auth_user_id = auth.uid());

CREATE POLICY clients_delete_own ON clients
FOR DELETE
USING (auth_user_id = auth.uid());


-- ============ sessions ============
-- Has client_id directly — shallow subquery.

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY sessions_select_own ON sessions
FOR SELECT
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY sessions_insert_own ON sessions
FOR INSERT
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY sessions_update_own ON sessions
FOR UPDATE
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
)
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);
-- No DELETE — training history is correctable, not removable.


-- ============ session_exercises ============
-- No direct client_id — has session_id. Shallow-through-sessions
-- subquery, same depth as sessions itself. This table's policies were
-- initially missing entirely, which silently broke training_log's
-- policy (see note at top of file) — a required dependency, not
-- optional, since training_log's subquery reads from this table.

ALTER TABLE session_exercises ENABLE ROW LEVEL SECURITY;

CREATE POLICY session_exercises_select_own ON session_exercises
FOR SELECT
USING (
  session_id IN (
    SELECT id FROM sessions
    WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
  )
);

CREATE POLICY session_exercises_insert_own ON session_exercises
FOR INSERT
WITH CHECK (
  session_id IN (
    SELECT id FROM sessions
    WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
  )
);

CREATE POLICY session_exercises_update_own ON session_exercises
FOR UPDATE
USING (
  session_id IN (
    SELECT id FROM sessions
    WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
  )
)
WITH CHECK (
  session_id IN (
    SELECT id FROM sessions
    WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
  )
);
-- No DELETE — a mistagged role can be corrected via UPDATE.


-- ============ training_log ============
-- No direct client_id — only session_exercise_id. Needs a three-level
-- lookup: find my own client id, then all session ids belonging to
-- that client, then all session_exercise ids tied to those sessions,
-- then check if this row's session_exercise_id is one of those.

ALTER TABLE training_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY training_log_select_own ON training_log
FOR SELECT
USING (
  session_exercise_id IN (
    SELECT id FROM session_exercises
    WHERE session_id IN (
      SELECT id FROM sessions
      WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
    )
  )
);

CREATE POLICY training_log_insert_own ON training_log
FOR INSERT
WITH CHECK (
  session_exercise_id IN (
    SELECT id FROM session_exercises
    WHERE session_id IN (
      SELECT id FROM sessions
      WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
    )
  )
);

CREATE POLICY training_log_update_own ON training_log
FOR UPDATE
USING (
  session_exercise_id IN (
    SELECT id FROM session_exercises
    WHERE session_id IN (
      SELECT id FROM sessions
      WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
    )
  )
)
WITH CHECK (
  session_exercise_id IN (
    SELECT id FROM session_exercises
    WHERE session_id IN (
      SELECT id FROM sessions
      WHERE client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
    )
  )
);
-- No DELETE — same reasoning as sessions.


-- ============ program_weeks ============
-- Has client_id directly — shallow subquery. Writable by the user
-- (not just a coach) since this system also serves self-programming
-- lifters who know their own block dates.

ALTER TABLE program_weeks ENABLE ROW LEVEL SECURITY;

CREATE POLICY program_weeks_select_own ON program_weeks
FOR SELECT
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY program_weeks_insert_own ON program_weeks
FOR INSERT
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY program_weeks_update_own ON program_weeks
FOR UPDATE
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
)
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);
-- No DELETE — correctable, not removable.


-- ============ nutrition_log ============
-- Has client_id directly — shallow subquery.

ALTER TABLE nutrition_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY nutrition_log_select_own ON nutrition_log
FOR SELECT
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY nutrition_log_insert_own ON nutrition_log
FOR INSERT
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY nutrition_log_update_own ON nutrition_log
FOR UPDATE
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
)
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);
-- No DELETE — correctable, not removable.


-- ============ body_metrics ============
-- Has client_id directly — shallow subquery.

ALTER TABLE body_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY body_metrics_select_own ON body_metrics
FOR SELECT
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY body_metrics_insert_own ON body_metrics
FOR INSERT
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY body_metrics_update_own ON body_metrics
FOR UPDATE
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
)
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);
-- No DELETE — correctable, not removable.


-- ============ sleep_metrics ============
-- Has client_id directly — shallow subquery.

ALTER TABLE sleep_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY sleep_metrics_select_own ON sleep_metrics
FOR SELECT
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY sleep_metrics_insert_own ON sleep_metrics
FOR INSERT
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);

CREATE POLICY sleep_metrics_update_own ON sleep_metrics
FOR UPDATE
USING (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
)
WITH CHECK (
  client_id = (SELECT id FROM clients WHERE auth_user_id = auth.uid())
);
-- No DELETE — correctable, not removable.


-- ============ exercises ============
-- Shared reference list, not per-client data — no ownership check
-- needed. Any authenticated user can read the full list; no
-- INSERT/UPDATE/DELETE policy exists for regular users, so writes
-- stay admin-only by default (no policy = no permission).

ALTER TABLE exercises ENABLE ROW LEVEL SECURITY;

CREATE POLICY exercises_select_all ON exercises
FOR SELECT
USING (true);

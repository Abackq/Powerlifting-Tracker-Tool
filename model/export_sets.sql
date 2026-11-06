-- model/export_sets.sql
-- Exports one client's usable comp-lift sets for the load-prediction model.
-- Replace <client-id> with the client's id before running. Do NOT commit a real id.
-- Output: one row per set, with a week index that runs across all blocks.
with weeks as (
  select id, block, week,
         row_number() over (order by block, week) as week_index
  from program_weeks
  where client_id = '<client-id>'
)
select
  case when e.name = 'Comp Deadlift' then 'Deadlift' else e.name end as lift,  -- same lift, two names
  w.block, w.week, w.week_index,
  s.day_number, tl.set_number,
  tl.reps, tl.rpe, tl.prescribed_rpe, tl.prescribed_backoff_pct,
  tl.weight_kgs, tl.e1rm
from training_log tl
join session_exercises se on se.id = tl.session_exercise_id
join exercises e on e.id = se.exercise_id
join sessions s on s.id = se.session_id
join weeks w on w.id = s.program_week_id
where e.name in ('Comp Squat', 'Comp Bench', 'Deadlift', 'Comp Deadlift')
  and tl.weight_kgs is not null
  and tl.rpe is not null
order by w.week_index, s.day_number, tl.set_number;
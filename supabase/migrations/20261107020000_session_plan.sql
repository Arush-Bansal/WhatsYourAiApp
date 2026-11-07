-- Session goal, mode, and the 1–9 plan pointers (PlanSkill).
alter table wa_agent.sessions add column if not exists goal text not null default '';
alter table wa_agent.sessions add column if not exists mode text not null default 'explore';
alter table wa_agent.sessions add column if not exists plan jsonb not null default '[]'::jsonb;

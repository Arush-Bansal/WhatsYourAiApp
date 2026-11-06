-- Storage for the WhatsApp design-guidelines agent. Isolated in its own schema.
create schema if not exists wa_agent;

create table if not exists wa_agent.processed_messages (
  message_id text primary key,
  created_at timestamptz not null default now()
);

create table if not exists wa_agent.form_sessions (
  wa_id text primary key,
  form_id text not null,
  step int not null default 0,
  answers jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists wa_agent.form_submissions (
  id bigint generated always as identity primary key,
  wa_id text not null,
  form_id text not null,
  answers jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists form_submissions_wa_id_idx on wa_agent.form_submissions (wa_id, created_at desc);

-- No access through the public Supabase APIs; the bot connects with its own role.
alter table wa_agent.processed_messages enable row level security;
alter table wa_agent.form_sessions enable row level security;
alter table wa_agent.form_submissions enable row level security;

do $$
begin
  if not exists (select from pg_roles where rolname = 'wa_agent_bot') then
    create role wa_agent_bot login;
  end if;
end $$;
grant usage on schema wa_agent to wa_agent_bot;
grant select, insert, update, delete on all tables in schema wa_agent to wa_agent_bot;
grant usage, select on all sequences in schema wa_agent to wa_agent_bot;
create policy bot_all on wa_agent.processed_messages for all to wa_agent_bot using (true) with check (true);
create policy bot_all on wa_agent.form_sessions for all to wa_agent_bot using (true) with check (true);
create policy bot_all on wa_agent.form_submissions for all to wa_agent_bot using (true) with check (true);

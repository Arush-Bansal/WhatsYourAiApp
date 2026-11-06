-- Brands (long-term memory card per brand) and chat sessions (rolling summaries).
create table if not exists wa_agent.brands (
  id bigint generated always as identity primary key,
  wa_id text not null,
  name text not null default 'My brand',
  card jsonb not null default '{}'::jsonb,
  active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists brands_one_active on wa_agent.brands (wa_id) where active;
create index if not exists brands_wa_idx on wa_agent.brands (wa_id);

create table if not exists wa_agent.sessions (
  id bigint generated always as identity primary key,
  wa_id text not null,
  brand_id bigint not null references wa_agent.brands (id) on delete cascade,
  summary text not null default '',
  summarised boolean not null default false,
  created_at timestamptz not null default now(),
  last_at timestamptz not null default now()
);
create index if not exists sessions_wa_idx on wa_agent.sessions (wa_id, id desc);
create index if not exists sessions_brand_idx on wa_agent.sessions (brand_id, id desc);

alter table wa_agent.messages add column if not exists session_id bigint;
alter table wa_agent.messages add column if not exists compacted boolean not null default false;
create index if not exists messages_session_idx on wa_agent.messages (session_id, id);

alter table wa_agent.brands enable row level security;
alter table wa_agent.sessions enable row level security;
create policy bot_all on wa_agent.brands for all to wa_agent_bot using (true) with check (true);
create policy bot_all on wa_agent.sessions for all to wa_agent_bot using (true) with check (true);
grant select, insert, update, delete on all tables in schema wa_agent to wa_agent_bot;
grant usage, select on all sequences in schema wa_agent to wa_agent_bot;

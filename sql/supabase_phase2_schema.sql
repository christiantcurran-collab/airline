create extension if not exists pgcrypto;

create table if not exists ticket_events (
    id uuid default gen_random_uuid() primary key,
    ticket_number text not null,
    event_sequence integer not null,
    event_type text not null,
    source_system text not null,
    occurred_at timestamptz not null,
    payload jsonb not null,
    ingested_at timestamptz default now(),
    unique (ticket_number, event_sequence)
);

create index if not exists idx_ticket_events_ticket on ticket_events (ticket_number, event_sequence);

create table if not exists ticket_current_state (
    ticket_number text primary key,
    status text not null,
    pnr text,
    passenger_name text,
    origin text,
    destination text,
    gross_amount decimal,
    currency text,
    event_count integer,
    last_event_type text,
    last_modified timestamptz,
    coupon_statuses jsonb default '{}'::jsonb,
    updated_at timestamptz default now()
);

create table if not exists coupon_matches (
    id uuid default gen_random_uuid() primary key,
    ticket_number text not null,
    coupon_number integer not null,
    status text not null check (status in ('matched', 'unmatched_issued', 'unmatched_flown', 'suspense')),
    issued_event_id uuid references ticket_events(id),
    flown_event_id uuid references ticket_events(id),
    issued_at timestamptz,
    flown_at timestamptz,
    matched_at timestamptz,
    days_in_suspense integer default 0,
    notes text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (ticket_number, coupon_number)
);

create table if not exists recon_results (
    id uuid default gen_random_uuid() primary key,
    ticket_number text not null,
    coupon_number integer,
    recon_type text not null check (recon_type in ('ticket_coupon', 'coupon_settlement', 'three_way')),
    status text not null check (status in ('matched', 'break')),
    break_type text check (break_type in ('timing', 'fare_mismatch', 'missing_coupon', 'duplicate_lift', 'missing_settlement')),
    severity text check (severity in ('low', 'medium', 'high')),
    our_amount decimal,
    their_amount decimal,
    difference decimal,
    resolution text check (resolution in ('unresolved', 'auto_resolved', 'manually_resolved', 'escalated')),
    resolution_notes text,
    created_at timestamptz default now(),
    resolved_at timestamptz
);

create table if not exists audit_log (
    id uuid default gen_random_uuid() primary key,
    timestamp timestamptz default now(),
    action text not null,
    component text not null,
    ticket_number text,
    input_event_ids uuid[],
    output_reference text,
    detail jsonb,
    raw_source_hash text
);

create index if not exists idx_audit_ticket on audit_log (ticket_number);
create index if not exists idx_audit_component on audit_log (component);
create index if not exists idx_audit_timestamp on audit_log (timestamp);

create table if not exists dag_runs (
    id uuid default gen_random_uuid() primary key,
    dag_name text not null,
    status text not null check (status in ('pending', 'running', 'succeeded', 'failed')),
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz default now()
);

create table if not exists task_runs (
    id uuid default gen_random_uuid() primary key,
    dag_run_id uuid references dag_runs(id),
    task_name text not null,
    status text not null check (status in ('pending', 'running', 'succeeded', 'failed', 'skipped')),
    depends_on text[],
    started_at timestamptz,
    completed_at timestamptz,
    error_message text,
    result jsonb
);

create table if not exists settlements (
    id uuid default gen_random_uuid() primary key,
    ticket_number text not null,
    counterparty text not null,
    counterparty_type text not null check (counterparty_type in ('gds_agent', 'ota', 'interline_partner')),
    our_amount decimal not null,
    their_amount decimal,
    currency text not null,
    status text not null check (status in ('calculated', 'validated', 'submitted', 'confirmed', 'reconciled', 'disputed', 'compensated')),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create table if not exists settlement_saga_log (
    id uuid default gen_random_uuid() primary key,
    settlement_id uuid references settlements(id),
    from_status text not null,
    to_status text not null,
    action text not null,
    detail jsonb,
    timestamp timestamptz default now()
);


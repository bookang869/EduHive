-- Run this in your Supabase SQL editor (or psql) to provision the Phase 1a/1b schema.

create extension if not exists vector;

create table if not exists users (
    id          uuid primary key default gen_random_uuid(),
    google_sub  text unique not null,
    email       text not null,
    name        text,
    created_at  timestamptz default now()
);

create table if not exists study_sets (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid references users(id),
    thread_id   text unique,
    created_at  timestamptz default now()
);

create table if not exists files (
    id              uuid primary key default gen_random_uuid(),
    study_set_id    uuid not null references study_sets(id) on delete cascade,
    storage_path    text not null,
    filename        text not null,
    extracted_text  text,
    page_count      int,
    status          text not null default 'pending',
    created_at      timestamptz default now()
);

create table if not exists file_chunks (
    id           uuid primary key default gen_random_uuid(),
    file_id      uuid not null references files(id) on delete cascade,
    study_set_id uuid not null references study_sets(id) on delete cascade,
    content      text not null,
    embedding    vector(1536),
    chunk_index  int not null,
    created_at   timestamptz default now()
);

create table if not exists web_chunks (
    id           uuid primary key default gen_random_uuid(),
    study_set_id uuid not null references study_sets(id) on delete cascade,
    query        text,
    content      text not null,
    embedding    vector(1536),
    created_at   timestamptz default now()
);

create table if not exists topic_scores (
    id           uuid primary key default gen_random_uuid(),
    study_set_id uuid not null references study_sets(id) on delete cascade,
    topic        text not null,
    score        int not null check (score between 1 and 10),
    reason       text
);

create table if not exists study_guides (
    id           uuid primary key default gen_random_uuid(),
    study_set_id uuid not null references study_sets(id) on delete cascade,
    content_md   text not null,
    created_at   timestamptz default now()
);

create table if not exists flashcards (
    id           uuid primary key default gen_random_uuid(),
    study_set_id uuid not null references study_sets(id) on delete cascade,
    front        text not null,
    back         text not null,
    topic        text not null
);

create table if not exists quizzes (
    id              uuid primary key default gen_random_uuid(),
    study_set_id    uuid not null references study_sets(id) on delete cascade,
    questions_json  jsonb not null,
    created_at      timestamptz default now()
);

create table if not exists quiz_attempts (
    id           uuid primary key default gen_random_uuid(),
    quiz_id      uuid not null references quizzes(id) on delete cascade,
    user_id      uuid references users(id),
    score        int not null,
    wrong_topics jsonb,
    taken_at     timestamptz default now()
);

-- ivfflat indexes for cosine similarity search (lists=100 suits up to ~1M rows)
create index if not exists file_chunks_embedding_idx
    on file_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists web_chunks_embedding_idx
    on web_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

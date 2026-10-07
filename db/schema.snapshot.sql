-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -
COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';

-- Name: EXTENSION citext; Type: COMMENT; Schema: -
COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';

-- Name: EXTENSION ltree; Type: COMMENT; Schema: -
COMMENT ON EXTENSION ltree IS 'data type for hierarchical tree-like structures';

-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -
COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';

-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -
COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';

-- Name: EXTENSION vector; Type: COMMENT; Schema: -
COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';

-- Name: btree_gist; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

-- Name: citext; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;

-- Name: ltree; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS ltree WITH SCHEMA public;

-- Name: pg_trgm; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;

-- Name: pgcrypto; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- Name: vector; Type: EXTENSION; Schema: -
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- Name: aip_meta; Type: SCHEMA; Schema: -
CREATE SCHEMA aip_meta;

ALTER SCHEMA aip_meta OWNER TO aip_owner;

-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: aip_meta
ALTER TABLE ONLY aip_meta.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

-- Name: alembic_version; Type: TABLE; Schema: aip_meta
CREATE TABLE aip_meta.alembic_version (
    version_num character varying(32) NOT NULL
);

ALTER TABLE aip_meta.alembic_version OWNER TO aip_owner;

-- Name: job_events job_events_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_pkey PRIMARY KEY (id);

-- Name: job_events uq_job_events_job_id_seq; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT uq_job_events_job_id_seq UNIQUE (job_id, seq);

-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);

-- Name: jobs uq_jobs_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_id_tenant_id UNIQUE (id, tenant_id);

-- Name: job_events fk_job_events_job_id_tenant_id_jobs; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT fk_job_events_job_id_tenant_id_jobs FOREIGN KEY (job_id, tenant_id) REFERENCES public.jobs(id, tenant_id);

-- Name: ix_job_events_tenant_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_job_events_tenant_id_occurred_at ON public.job_events USING btree (tenant_id, occurred_at);

-- Name: ix_jobs_correlation_id; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_correlation_id ON public.jobs USING btree (correlation_id);

-- Name: ix_jobs_tenant_id_requested_by_created_at; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_tenant_id_requested_by_created_at ON public.jobs USING btree (tenant_id, requested_by, created_at DESC) WHERE (deleted_at IS NULL);

-- Name: ix_jobs_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_tenant_id_status ON public.jobs USING btree (tenant_id, status) WHERE (deleted_at IS NULL);

-- Name: uq_jobs_tenant_id_job_type_idempotency_key; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_jobs_tenant_id_job_type_idempotency_key ON public.jobs USING btree (tenant_id, job_type, idempotency_key) WHERE (idempotency_key IS NOT NULL);

-- Name: job_events tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.job_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: jobs tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.jobs USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: job_events; Type: ROW SECURITY; Schema: public
ALTER TABLE public.job_events ENABLE ROW LEVEL SECURITY;

-- Name: jobs; Type: ROW SECURITY; Schema: public
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Name: job_events; Type: TABLE; Schema: public
CREATE TABLE public.job_events (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL,
    seq integer NOT NULL,
    from_status text,
    to_status text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_job_events_from_status CHECK ((from_status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text]))),
    CONSTRAINT ck_job_events_seq CHECK ((seq >= 1)),
    CONSTRAINT ck_job_events_to_status CHECK ((to_status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))
);

ALTER TABLE ONLY public.job_events FORCE ROW LEVEL SECURITY;

ALTER TABLE public.job_events OWNER TO aip_owner;

-- Name: jobs; Type: TABLE; Schema: public
CREATE TABLE public.jobs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    job_type text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    idempotency_key text,
    correlation_id uuid NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    result_ref text,
    error text,
    requested_by uuid,
    procrastinate_job_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_jobs_attempts CHECK ((attempts >= 0)),
    CONSTRAINT ck_jobs_idempotency_key CHECK ((idempotency_key <> ''::text)),
    CONSTRAINT ck_jobs_job_type CHECK ((job_type <> ''::text)),
    CONSTRAINT ck_jobs_status CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))
);

ALTER TABLE ONLY public.jobs FORCE ROW LEVEL SECURITY;

ALTER TABLE public.jobs OWNER TO aip_owner;

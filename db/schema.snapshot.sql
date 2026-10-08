-- Name: SCHEMA aip_meta; Type: ACL; Schema: -
GRANT USAGE ON SCHEMA aip_meta TO aip_app;

-- Name: SCHEMA public; Type: ACL; Schema: -
GRANT USAGE ON SCHEMA public TO aip_app;
GRANT USAGE ON SCHEMA public TO aip_jobs;
GRANT USAGE ON SCHEMA public TO aip_readonly;

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

-- Name: TABLE alembic_version; Type: ACL; Schema: aip_meta
GRANT SELECT ON TABLE aip_meta.alembic_version TO aip_app;

-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: aip_meta
ALTER TABLE ONLY aip_meta.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

-- Name: alembic_version; Type: TABLE; Schema: aip_meta
CREATE TABLE aip_meta.alembic_version (
    version_num character varying(32) NOT NULL
);

ALTER TABLE aip_meta.alembic_version OWNER TO aip_owner;

-- Name: COLUMN jobs.attempts; Type: ACL; Schema: public
GRANT UPDATE(attempts) ON TABLE public.jobs TO aip_jobs;

-- Name: COLUMN jobs.error; Type: ACL; Schema: public
GRANT UPDATE(error) ON TABLE public.jobs TO aip_jobs;

-- Name: COLUMN jobs.procrastinate_job_id; Type: ACL; Schema: public
GRANT UPDATE(procrastinate_job_id) ON TABLE public.jobs TO aip_jobs;

-- Name: COLUMN jobs.result_ref; Type: ACL; Schema: public
GRANT UPDATE(result_ref) ON TABLE public.jobs TO aip_jobs;

-- Name: COLUMN jobs.status; Type: ACL; Schema: public
GRANT UPDATE(status) ON TABLE public.jobs TO aip_jobs;

-- Name: COLUMN jobs.updated_at; Type: ACL; Schema: public
GRANT UPDATE(updated_at) ON TABLE public.jobs TO aip_jobs;

-- Name: FUNCTION identity_resolve_login(p_kind text, p_key public.citext); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) TO aip_app;

-- Name: TABLE deployment_regions; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.deployment_regions TO aip_app;
GRANT SELECT ON TABLE public.deployment_regions TO aip_jobs;
GRANT SELECT ON TABLE public.deployment_regions TO aip_readonly;

-- Name: TABLE job_events; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.job_events TO aip_app;
GRANT SELECT,INSERT ON TABLE public.job_events TO aip_jobs;
GRANT SELECT ON TABLE public.job_events TO aip_readonly;

-- Name: TABLE jobs; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.jobs TO aip_app;
GRANT SELECT ON TABLE public.jobs TO aip_readonly;
GRANT SELECT ON TABLE public.jobs TO aip_jobs;

-- Name: TABLE tenants; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.tenants TO aip_app;
GRANT SELECT ON TABLE public.tenants TO aip_readonly;

-- Name: deployment_regions pk_deployment_regions; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.deployment_regions
    ADD CONSTRAINT pk_deployment_regions PRIMARY KEY (code);

-- Name: job_events pk_job_events; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT pk_job_events PRIMARY KEY (id);

-- Name: job_events uq_job_events_job_id_seq; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT uq_job_events_job_id_seq UNIQUE (job_id, seq);

-- Name: jobs pk_jobs; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT pk_jobs PRIMARY KEY (id);

-- Name: jobs uq_jobs_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_id_tenant_id UNIQUE (id, tenant_id);

-- Name: login_directory login_directory_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT login_directory_pkey PRIMARY KEY (id);

-- Name: login_directory uq_login_directory_kind_key; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT uq_login_directory_kind_key UNIQUE (kind, key);

-- Name: tenants pk_tenants; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT pk_tenants PRIMARY KEY (id);

-- Name: tenants uq_tenants_slug; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT uq_tenants_slug UNIQUE (slug);

-- Name: job_events fk_job_events_job_id_tenant_id_jobs; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT fk_job_events_job_id_tenant_id_jobs FOREIGN KEY (job_id, tenant_id) REFERENCES public.jobs(id, tenant_id);

-- Name: login_directory fk_login_directory_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT fk_login_directory_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenants fk_tenants_region_code_deployment_regions; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT fk_tenants_region_code_deployment_regions FOREIGN KEY (region_code) REFERENCES public.deployment_regions(code);

-- Name: identity_resolve_login(text, public.citext); Type: FUNCTION; Schema: public
CREATE FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) RETURNS TABLE(tenant_id uuid, idp_alias text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT d.tenant_id, d.idp_alias
      FROM public.login_directory AS d
      WHERE d.kind = p_kind AND d.key = p_key
    $$;

ALTER FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) OWNER TO aip_owner;

-- Name: ix_job_events_tenant_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_job_events_tenant_id_occurred_at ON public.job_events USING btree (tenant_id, occurred_at);

-- Name: ix_jobs_correlation_id; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_correlation_id ON public.jobs USING btree (correlation_id);

-- Name: ix_jobs_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_tenant_id ON public.jobs USING btree (tenant_id);

-- Name: ix_jobs_tenant_id_requested_by_created_at; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_tenant_id_requested_by_created_at ON public.jobs USING btree (tenant_id, requested_by, created_at DESC) WHERE (deleted_at IS NULL);

-- Name: ix_jobs_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_jobs_tenant_id_status ON public.jobs USING btree (tenant_id, status) WHERE (deleted_at IS NULL);

-- Name: ix_login_directory_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_login_directory_tenant_id ON public.login_directory USING btree (tenant_id);

-- Name: ix_tenants_region_code; Type: INDEX; Schema: public
CREATE INDEX ix_tenants_region_code ON public.tenants USING btree (region_code);

-- Name: ix_tenants_status; Type: INDEX; Schema: public
CREATE INDEX ix_tenants_status ON public.tenants USING btree (status);

-- Name: uq_jobs_tenant_id_job_type_idempotency_key; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_jobs_tenant_id_job_type_idempotency_key ON public.jobs USING btree (tenant_id, job_type, idempotency_key) WHERE (idempotency_key IS NOT NULL);

-- Name: job_events tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.job_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: jobs tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.jobs USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenants tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenants USING ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: job_events; Type: ROW SECURITY; Schema: public
ALTER TABLE public.job_events ENABLE ROW LEVEL SECURITY;

-- Name: jobs; Type: ROW SECURITY; Schema: public
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Name: tenants; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

-- Name: deployment_regions; Type: TABLE; Schema: public
CREATE TABLE public.deployment_regions (
    code text NOT NULL,
    label_key text NOT NULL,
    in_country_only boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_deployment_regions_code CHECK ((code ~ '^[a-z]{2}(-[a-z]+)+-[0-9]+$'::text)),
    CONSTRAINT ck_deployment_regions_label_key CHECK ((label_key ~ '^[a-z][a-z0-9_.]*$'::text))
);

ALTER TABLE public.deployment_regions OWNER TO aip_owner;

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

-- Name: login_directory; Type: TABLE; Schema: public
CREATE TABLE public.login_directory (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind text NOT NULL,
    key public.citext NOT NULL,
    tenant_id uuid NOT NULL,
    idp_alias text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_login_directory_kind CHECK ((kind = ANY (ARRAY['email_domain'::text, 'tenant_slug'::text])))
);

ALTER TABLE public.login_directory OWNER TO aip_owner;

-- Name: tenants; Type: TABLE; Schema: public
CREATE TABLE public.tenants (
    id uuid NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    deployment_shape text DEFAULT 'pooled'::text NOT NULL,
    region_code text NOT NULL,
    kms_key_ref text,
    status text DEFAULT 'provisioning'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenants_deployment_shape CHECK ((deployment_shape = ANY (ARRAY['pooled'::text, 'siloed'::text]))),
    CONSTRAINT ck_tenants_id CHECK ((id <> '00000000-0000-0000-0000-000000000000'::uuid)),
    CONSTRAINT ck_tenants_kms_key_ref CHECK ((kms_key_ref <> ''::text)),
    CONSTRAINT ck_tenants_name CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT ck_tenants_slug CHECK ((slug ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'::text)),
    CONSTRAINT ck_tenants_status CHECK ((status = ANY (ARRAY['provisioning'::text, 'active'::text, 'suspended'::text, 'offboarding'::text, 'offboarded'::text])))
);

ALTER TABLE ONLY public.tenants FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenants OWNER TO aip_owner;

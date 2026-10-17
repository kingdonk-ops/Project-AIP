-- Name: SCHEMA aip_meta; Type: ACL; Schema: -
GRANT USAGE ON SCHEMA aip_meta TO aip_app;

-- Name: SCHEMA public; Type: ACL; Schema: -
GRANT USAGE ON SCHEMA public TO aip_app;
GRANT USAGE ON SCHEMA public TO aip_jobs;
GRANT USAGE ON SCHEMA public TO aip_readonly;
GRANT USAGE ON SCHEMA public TO aip_audit_writer;

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

-- Name: COLUMN domain_events.attempts; Type: ACL; Schema: public
GRANT UPDATE(attempts) ON TABLE public.domain_events TO aip_jobs;

-- Name: COLUMN domain_events.dead_lettered_at; Type: ACL; Schema: public
GRANT UPDATE(dead_lettered_at) ON TABLE public.domain_events TO aip_jobs;

-- Name: COLUMN domain_events.last_error; Type: ACL; Schema: public
GRANT UPDATE(last_error) ON TABLE public.domain_events TO aip_jobs;

-- Name: COLUMN domain_events.next_attempt_at; Type: ACL; Schema: public
GRANT UPDATE(next_attempt_at) ON TABLE public.domain_events TO aip_jobs;

-- Name: COLUMN domain_events.published_at; Type: ACL; Schema: public
GRANT UPDATE(published_at) ON TABLE public.domain_events TO aip_jobs;

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

-- Name: COLUMN procrastinate_events.at; Type: ACL; Schema: public
GRANT INSERT(at) ON TABLE public.procrastinate_events TO aip_app;

-- Name: COLUMN procrastinate_events.job_id; Type: ACL; Schema: public
GRANT INSERT(job_id) ON TABLE public.procrastinate_events TO aip_app;

-- Name: COLUMN procrastinate_events.type; Type: ACL; Schema: public
GRANT INSERT(type) ON TABLE public.procrastinate_events TO aip_app;

-- Name: COLUMN procrastinate_jobs.args; Type: ACL; Schema: public
GRANT INSERT(args) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.id; Type: ACL; Schema: public
GRANT SELECT(id) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.lock; Type: ACL; Schema: public
GRANT INSERT(lock) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.priority; Type: ACL; Schema: public
GRANT INSERT(priority) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.queue_name; Type: ACL; Schema: public
GRANT INSERT(queue_name) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.queueing_lock; Type: ACL; Schema: public
GRANT INSERT(queueing_lock) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.scheduled_at; Type: ACL; Schema: public
GRANT INSERT(scheduled_at) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: COLUMN procrastinate_jobs.task_name; Type: ACL; Schema: public
GRANT INSERT(task_name) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: FUNCTION access_sync_permissions(p_catalogue jsonb); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.access_sync_permissions(p_catalogue jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION public.access_sync_permissions(p_catalogue jsonb) TO aip_app;

-- Name: FUNCTION aip_convert_to_partitioned(p_table text); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.aip_convert_to_partitioned(p_table text) FROM PUBLIC;

-- Name: FUNCTION aip_ensure_partitions(p_table text, p_months_ahead integer); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.aip_ensure_partitions(p_table text, p_months_ahead integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.aip_ensure_partitions(p_table text, p_months_ahead integer) TO aip_jobs;

-- Name: FUNCTION domain_events_write_once(); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.domain_events_write_once() FROM PUBLIC;

-- Name: FUNCTION identity_register_email(p_email public.citext, p_tenant uuid); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_register_email(p_email public.citext, p_tenant uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_register_email(p_email public.citext, p_tenant uuid) TO aip_app;

-- Name: FUNCTION identity_resolve_login(p_kind text, p_key public.citext); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) TO aip_app;

-- Name: FUNCTION identity_resolve_session(p_sid_hash bytea); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_resolve_session(p_sid_hash bytea) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_resolve_session(p_sid_hash bytea) TO aip_app;

-- Name: FUNCTION identity_sessions_by_kc_sid(p_kc_sid text); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_sessions_by_kc_sid(p_kc_sid text) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_sessions_by_kc_sid(p_kc_sid text) TO aip_app;

-- Name: FUNCTION outbox_dead_letters(lim integer, after uuid); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.outbox_dead_letters(lim integer, after uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.outbox_dead_letters(lim integer, after uuid) TO aip_app;

-- Name: FUNCTION outbox_discard(event_id uuid, reason text, actor uuid); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.outbox_discard(event_id uuid, reason text, actor uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.outbox_discard(event_id uuid, reason text, actor uuid) TO aip_app;

-- Name: FUNCTION outbox_retry(event_id uuid); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.outbox_retry(event_id uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.outbox_retry(event_id uuid) TO aip_app;

-- Name: FUNCTION platform_event_counts(since timestamp with time zone); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.platform_event_counts(since timestamp with time zone) FROM PUBLIC;
GRANT ALL ON FUNCTION public.platform_event_counts(since timestamp with time zone) TO aip_app;

-- Name: FUNCTION tenancy_has_real_customer(); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.tenancy_has_real_customer() FROM PUBLIC;
GRANT ALL ON FUNCTION public.tenancy_has_real_customer() TO aip_app;

-- Name: SEQUENCE procrastinate_events_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_events_id_seq TO aip_jobs;
GRANT USAGE ON SEQUENCE public.procrastinate_events_id_seq TO aip_app;

-- Name: SEQUENCE procrastinate_jobs_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_jobs_id_seq TO aip_jobs;
GRANT USAGE ON SEQUENCE public.procrastinate_jobs_id_seq TO aip_app;

-- Name: SEQUENCE procrastinate_periodic_defers_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_periodic_defers_id_seq TO aip_jobs;

-- Name: TABLE access_reviews; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.access_reviews TO aip_app;
GRANT SELECT ON TABLE public.access_reviews TO aip_readonly;

-- Name: TABLE access_settings; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.access_settings TO aip_app;
GRANT SELECT ON TABLE public.access_settings TO aip_readonly;

-- Name: TABLE app_user; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.app_user TO aip_app;
GRANT SELECT ON TABLE public.app_user TO aip_readonly;

-- Name: TABLE audit_chain_checkpoints; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.audit_chain_checkpoints TO aip_audit_writer;
GRANT SELECT ON TABLE public.audit_chain_checkpoints TO aip_app;
GRANT SELECT ON TABLE public.audit_chain_checkpoints TO aip_readonly;

-- Name: TABLE audit_chain_heads; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.audit_chain_heads TO aip_audit_writer;
GRANT SELECT ON TABLE public.audit_chain_heads TO aip_readonly;

-- Name: TABLE audit_log; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.audit_log TO aip_audit_writer;
GRANT SELECT ON TABLE public.audit_log TO aip_app;
GRANT SELECT ON TABLE public.audit_log TO aip_readonly;

-- Name: TABLE auth_event; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.auth_event TO aip_app;
GRANT SELECT ON TABLE public.auth_event TO aip_readonly;

-- Name: TABLE breach_incidents; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.breach_incidents TO aip_app;
GRANT SELECT ON TABLE public.breach_incidents TO aip_readonly;

-- Name: TABLE control_records; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.control_records TO aip_app;
GRANT SELECT ON TABLE public.control_records TO aip_readonly;

-- Name: TABLE data_map_entries; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.data_map_entries TO aip_app;
GRANT SELECT ON TABLE public.data_map_entries TO aip_readonly;

-- Name: TABLE deployment_regions; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.deployment_regions TO aip_app;
GRANT SELECT ON TABLE public.deployment_regions TO aip_jobs;
GRANT SELECT ON TABLE public.deployment_regions TO aip_readonly;

-- Name: TABLE domain_events; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.domain_events TO aip_app;
GRANT SELECT,INSERT ON TABLE public.domain_events TO aip_jobs;
GRANT SELECT ON TABLE public.domain_events TO aip_readonly;

-- Name: TABLE evidence_items; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.evidence_items TO aip_app;
GRANT SELECT ON TABLE public.evidence_items TO aip_readonly;

-- Name: TABLE glossary_entry; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.glossary_entry TO aip_app;
GRANT SELECT ON TABLE public.glossary_entry TO aip_readonly;

-- Name: TABLE job_events; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.job_events TO aip_app;
GRANT SELECT,INSERT ON TABLE public.job_events TO aip_jobs;
GRANT SELECT ON TABLE public.job_events TO aip_readonly;

-- Name: TABLE jobs; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.jobs TO aip_app;
GRANT SELECT ON TABLE public.jobs TO aip_readonly;
GRANT SELECT ON TABLE public.jobs TO aip_jobs;

-- Name: TABLE locale_settings; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.locale_settings TO aip_app;
GRANT SELECT ON TABLE public.locale_settings TO aip_readonly;

-- Name: TABLE organisations; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.organisations TO aip_app;
GRANT SELECT ON TABLE public.organisations TO aip_readonly;

-- Name: TABLE partition_settings; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.partition_settings TO aip_jobs;

-- Name: TABLE permission; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.permission TO aip_app;
GRANT SELECT ON TABLE public.permission TO aip_readonly;

-- Name: TABLE platform_event_status; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.platform_event_status TO aip_app;
GRANT SELECT ON TABLE public.platform_event_status TO aip_readonly;

-- Name: TABLE procrastinate_events; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_events TO aip_jobs;

-- Name: TABLE procrastinate_jobs; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_jobs TO aip_jobs;

-- Name: TABLE procrastinate_periodic_defers; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_periodic_defers TO aip_jobs;

-- Name: TABLE procrastinate_workers; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_workers TO aip_jobs;

-- Name: TABLE projects; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.projects TO aip_app;
GRANT SELECT ON TABLE public.projects TO aip_readonly;

-- Name: TABLE provenance_entries; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.provenance_entries TO aip_app;
GRANT SELECT ON TABLE public.provenance_entries TO aip_readonly;

-- Name: TABLE record_links; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.record_links TO aip_app;
GRANT SELECT ON TABLE public.record_links TO aip_readonly;

-- Name: TABLE restore_test_records; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.restore_test_records TO aip_app;
GRANT SELECT ON TABLE public.restore_test_records TO aip_readonly;

-- Name: TABLE role; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.role TO aip_app;
GRANT SELECT ON TABLE public.role TO aip_readonly;

-- Name: TABLE role_assignment; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.role_assignment TO aip_app;
GRANT SELECT ON TABLE public.role_assignment TO aip_readonly;

-- Name: TABLE role_permission; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.role_permission TO aip_app;
GRANT SELECT ON TABLE public.role_permission TO aip_readonly;

-- Name: TABLE security_audit_events; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.security_audit_events TO aip_audit_writer;
GRANT SELECT ON TABLE public.security_audit_events TO aip_app;
GRANT SELECT ON TABLE public.security_audit_events TO aip_readonly;

-- Name: TABLE sites; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.sites TO aip_app;
GRANT SELECT ON TABLE public.sites TO aip_readonly;

-- Name: TABLE tenant_auth_policy; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_auth_policy TO aip_app;
GRANT SELECT ON TABLE public.tenant_auth_policy TO aip_readonly;

-- Name: TABLE tenant_entitlement_override; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_entitlement_override TO aip_app;
GRANT SELECT ON TABLE public.tenant_entitlement_override TO aip_readonly;

-- Name: TABLE tenant_feature_flags; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_feature_flags TO aip_app;
GRANT SELECT ON TABLE public.tenant_feature_flags TO aip_readonly;

-- Name: TABLE tenant_membership; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_membership TO aip_app;
GRANT SELECT ON TABLE public.tenant_membership TO aip_readonly;

-- Name: TABLE tenant_subscription; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_subscription TO aip_app;
GRANT SELECT ON TABLE public.tenant_subscription TO aip_readonly;

-- Name: TABLE tenant_usage; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.tenant_usage TO aip_app;
GRANT SELECT ON TABLE public.tenant_usage TO aip_readonly;

-- Name: TABLE tenants; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.tenants TO aip_app;
GRANT SELECT ON TABLE public.tenants TO aip_readonly;

-- Name: TABLE term_alias; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.term_alias TO aip_app;
GRANT SELECT ON TABLE public.term_alias TO aip_readonly;

-- Name: TABLE term_key; Type: ACL; Schema: public
GRANT SELECT ON TABLE public.term_key TO aip_app;
GRANT SELECT ON TABLE public.term_key TO aip_readonly;

-- Name: TABLE term_override; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.term_override TO aip_app;
GRANT SELECT ON TABLE public.term_override TO aip_readonly;

-- Name: TABLE term_pack; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.term_pack TO aip_app;
GRANT SELECT ON TABLE public.term_pack TO aip_readonly;

-- Name: TABLE term_pack_version; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.term_pack_version TO aip_app;
GRANT SELECT ON TABLE public.term_pack_version TO aip_readonly;

-- Name: TABLE upload_sessions; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.upload_sessions TO aip_app;
GRANT SELECT ON TABLE public.upload_sessions TO aip_readonly;

-- Name: TABLE user_session; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.user_session TO aip_app;
GRANT SELECT ON TABLE public.user_session TO aip_readonly;

-- Name: TABLE workflow_definition_audit; Type: ACL; Schema: public
GRANT SELECT,INSERT ON TABLE public.workflow_definition_audit TO aip_app;
GRANT SELECT ON TABLE public.workflow_definition_audit TO aip_readonly;

-- Name: TABLE workflow_definitions; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.workflow_definitions TO aip_app;
GRANT SELECT ON TABLE public.workflow_definitions TO aip_readonly;

-- Name: TABLE workflow_instances; Type: ACL; Schema: public
GRANT SELECT,INSERT,UPDATE ON TABLE public.workflow_instances TO aip_app;
GRANT SELECT ON TABLE public.workflow_instances TO aip_readonly;

-- Name: access_reviews pk_access_reviews; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.access_reviews
    ADD CONSTRAINT pk_access_reviews PRIMARY KEY (id);

-- Name: access_settings pk_access_settings; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.access_settings
    ADD CONSTRAINT pk_access_settings PRIMARY KEY (id);

-- Name: app_user pk_app_user; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.app_user
    ADD CONSTRAINT pk_app_user PRIMARY KEY (id);

-- Name: app_user uq_app_user_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.app_user
    ADD CONSTRAINT uq_app_user_id_tenant_id UNIQUE (id, tenant_id);

-- Name: audit_chain_checkpoints pk_audit_chain_checkpoints; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.audit_chain_checkpoints
    ADD CONSTRAINT pk_audit_chain_checkpoints PRIMARY KEY (tenant_id, stream, segment);

-- Name: audit_chain_heads pk_audit_chain_heads; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.audit_chain_heads
    ADD CONSTRAINT pk_audit_chain_heads PRIMARY KEY (tenant_id, stream);

-- Name: audit_log pk_audit_log; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT pk_audit_log PRIMARY KEY (id);

-- Name: audit_log uq_audit_log_tenant_id_stream_seq; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT uq_audit_log_tenant_id_stream_seq UNIQUE (tenant_id, stream, seq);

-- Name: auth_event pk_auth_event; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.auth_event
    ADD CONSTRAINT pk_auth_event PRIMARY KEY (id);

-- Name: breach_incidents pk_breach_incidents; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.breach_incidents
    ADD CONSTRAINT pk_breach_incidents PRIMARY KEY (id);

-- Name: control_records pk_control_records; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.control_records
    ADD CONSTRAINT pk_control_records PRIMARY KEY (id);

-- Name: control_records uq_control_records_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.control_records
    ADD CONSTRAINT uq_control_records_id_tenant_id UNIQUE (id, tenant_id);

-- Name: data_map_entries pk_data_map_entries; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.data_map_entries
    ADD CONSTRAINT pk_data_map_entries PRIMARY KEY (id);

-- Name: deployment_regions pk_deployment_regions; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.deployment_regions
    ADD CONSTRAINT pk_deployment_regions PRIMARY KEY (code);

-- Name: domain_events pk_domain_events; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.domain_events
    ADD CONSTRAINT pk_domain_events PRIMARY KEY (id);

-- Name: evidence_items pk_evidence_items; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT pk_evidence_items PRIMARY KEY (id, created_at);

-- Name: evidence_items_default evidence_items_default_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.evidence_items_default
    ADD CONSTRAINT evidence_items_default_pkey PRIMARY KEY (id, created_at);

-- Name: glossary_entry pk_glossary_entry; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.glossary_entry
    ADD CONSTRAINT pk_glossary_entry PRIMARY KEY (id);

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

-- Name: locale_settings pk_locale_settings; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.locale_settings
    ADD CONSTRAINT pk_locale_settings PRIMARY KEY (id);

-- Name: login_directory login_directory_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT login_directory_pkey PRIMARY KEY (id);

-- Name: login_directory uq_login_directory_kind_key; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT uq_login_directory_kind_key UNIQUE (kind, key);

-- Name: organisations pk_organisations; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.organisations
    ADD CONSTRAINT pk_organisations PRIMARY KEY (id);

-- Name: organisations uq_organisations_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.organisations
    ADD CONSTRAINT uq_organisations_id_tenant_id UNIQUE (id, tenant_id);

-- Name: partition_settings pk_partition_settings; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.partition_settings
    ADD CONSTRAINT pk_partition_settings PRIMARY KEY (table_name);

-- Name: permission pk_permission; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.permission
    ADD CONSTRAINT pk_permission PRIMARY KEY (code);

-- Name: platform_event_status pk_platform_event_status; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.platform_event_status
    ADD CONSTRAINT pk_platform_event_status PRIMARY KEY (event_name, event_version);

-- Name: procrastinate_events procrastinate_events_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_events
    ADD CONSTRAINT procrastinate_events_pkey PRIMARY KEY (id);

-- Name: procrastinate_jobs procrastinate_jobs_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_jobs
    ADD CONSTRAINT procrastinate_jobs_pkey PRIMARY KEY (id);

-- Name: procrastinate_periodic_defers procrastinate_periodic_defers_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_periodic_defers
    ADD CONSTRAINT procrastinate_periodic_defers_pkey PRIMARY KEY (id);

-- Name: procrastinate_periodic_defers procrastinate_periodic_defers_unique; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_periodic_defers
    ADD CONSTRAINT procrastinate_periodic_defers_unique UNIQUE (task_name, periodic_id, defer_timestamp);

-- Name: procrastinate_workers procrastinate_workers_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_workers
    ADD CONSTRAINT procrastinate_workers_pkey PRIMARY KEY (id);

-- Name: projects pk_projects; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT pk_projects PRIMARY KEY (id);

-- Name: projects uq_projects_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT uq_projects_id_tenant_id UNIQUE (id, tenant_id);

-- Name: provenance_entries pk_provenance_entries; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.provenance_entries
    ADD CONSTRAINT pk_provenance_entries PRIMARY KEY (id, created_at);

-- Name: provenance_entries_default provenance_entries_default_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.provenance_entries_default
    ADD CONSTRAINT provenance_entries_default_pkey PRIMARY KEY (id, created_at);

-- Name: record_links pk_record_links; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.record_links
    ADD CONSTRAINT pk_record_links PRIMARY KEY (id);

-- Name: restore_test_records pk_restore_test_records; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.restore_test_records
    ADD CONSTRAINT pk_restore_test_records PRIMARY KEY (id, created_at);

-- Name: restore_test_records_default restore_test_records_default_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.restore_test_records_default
    ADD CONSTRAINT restore_test_records_default_pkey PRIMARY KEY (id, created_at);

-- Name: role pk_role; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role
    ADD CONSTRAINT pk_role PRIMARY KEY (id);

-- Name: role uq_role_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role
    ADD CONSTRAINT uq_role_id_tenant_id UNIQUE (id, tenant_id);

-- Name: role_assignment pk_role_assignment; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT pk_role_assignment PRIMARY KEY (id);

-- Name: role_permission pk_role_permission; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_permission
    ADD CONSTRAINT pk_role_permission PRIMARY KEY (id);

-- Name: security_audit_events pk_security_audit_events; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.security_audit_events
    ADD CONSTRAINT pk_security_audit_events PRIMARY KEY (id);

-- Name: security_audit_events uq_security_audit_events_tenant_id_seq; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.security_audit_events
    ADD CONSTRAINT uq_security_audit_events_tenant_id_seq UNIQUE (tenant_id, seq);

-- Name: sites pk_sites; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.sites
    ADD CONSTRAINT pk_sites PRIMARY KEY (id);

-- Name: sites uq_sites_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.sites
    ADD CONSTRAINT uq_sites_id_tenant_id UNIQUE (id, tenant_id);

-- Name: tenant_auth_policy pk_tenant_auth_policy; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_auth_policy
    ADD CONSTRAINT pk_tenant_auth_policy PRIMARY KEY (tenant_id);

-- Name: tenant_entitlement_override pk_tenant_entitlement_override; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_entitlement_override
    ADD CONSTRAINT pk_tenant_entitlement_override PRIMARY KEY (id);

-- Name: tenant_feature_flags pk_tenant_feature_flags; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_feature_flags
    ADD CONSTRAINT pk_tenant_feature_flags PRIMARY KEY (id);

-- Name: tenant_membership pk_tenant_membership; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_membership
    ADD CONSTRAINT pk_tenant_membership PRIMARY KEY (id);

-- Name: tenant_subscription pk_tenant_subscription; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_subscription
    ADD CONSTRAINT pk_tenant_subscription PRIMARY KEY (id);

-- Name: tenant_subscription uq_tenant_subscription_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_subscription
    ADD CONSTRAINT uq_tenant_subscription_tenant_id UNIQUE (tenant_id);

-- Name: tenant_usage pk_tenant_usage; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_usage
    ADD CONSTRAINT pk_tenant_usage PRIMARY KEY (id);

-- Name: tenant_usage uq_tenant_usage_tenant_id_period; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_usage
    ADD CONSTRAINT uq_tenant_usage_tenant_id_period UNIQUE (tenant_id, period);

-- Name: tenants pk_tenants; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT pk_tenants PRIMARY KEY (id);

-- Name: tenants uq_tenants_slug; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT uq_tenants_slug UNIQUE (slug);

-- Name: term_alias pk_term_alias; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_alias
    ADD CONSTRAINT pk_term_alias PRIMARY KEY (id);

-- Name: term_key pk_term_key; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_key
    ADD CONSTRAINT pk_term_key PRIMARY KEY (id);

-- Name: term_override pk_term_override; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_override
    ADD CONSTRAINT pk_term_override PRIMARY KEY (id);

-- Name: term_pack pk_term_pack; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack
    ADD CONSTRAINT pk_term_pack PRIMARY KEY (id);

-- Name: term_pack uq_term_pack_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack
    ADD CONSTRAINT uq_term_pack_id_tenant_id UNIQUE (id, tenant_id);

-- Name: term_pack_version pk_term_pack_version; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack_version
    ADD CONSTRAINT pk_term_pack_version PRIMARY KEY (id);

-- Name: term_pack_version uq_term_pack_version_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack_version
    ADD CONSTRAINT uq_term_pack_version_id_tenant_id UNIQUE (id, tenant_id);

-- Name: upload_sessions pk_upload_sessions; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.upload_sessions
    ADD CONSTRAINT pk_upload_sessions PRIMARY KEY (id);

-- Name: user_session pk_user_session; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.user_session
    ADD CONSTRAINT pk_user_session PRIMARY KEY (id);

-- Name: user_session uq_user_session_sid_hash; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.user_session
    ADD CONSTRAINT uq_user_session_sid_hash UNIQUE (sid_hash);

-- Name: workflow_definition_audit pk_workflow_definition_audit; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definition_audit
    ADD CONSTRAINT pk_workflow_definition_audit PRIMARY KEY (id, created_at);

-- Name: workflow_definition_audit_default workflow_definition_audit_default_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definition_audit_default
    ADD CONSTRAINT workflow_definition_audit_default_pkey PRIMARY KEY (id, created_at);

-- Name: workflow_definitions pk_workflow_definitions; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT pk_workflow_definitions PRIMARY KEY (id);

-- Name: workflow_definitions uq_workflow_definitions_id_tenant_id; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT uq_workflow_definitions_id_tenant_id UNIQUE (id, tenant_id);

-- Name: workflow_definitions uq_workflow_definitions_key_version; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT uq_workflow_definitions_key_version UNIQUE (tenant_id, key, version);

-- Name: workflow_instances pk_workflow_instances; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_instances
    ADD CONSTRAINT pk_workflow_instances PRIMARY KEY (id);

-- Name: procrastinate_events id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_events ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_events_id_seq'::regclass);

-- Name: procrastinate_jobs id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_jobs ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_jobs_id_seq'::regclass);

-- Name: procrastinate_periodic_defers id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_periodic_defers ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_periodic_defers_id_seq'::regclass);

-- Name: access_settings fk_access_settings_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.access_settings
    ADD CONSTRAINT fk_access_settings_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: app_user fk_app_user_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.app_user
    ADD CONSTRAINT fk_app_user_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: auth_event fk_auth_event_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.auth_event
    ADD CONSTRAINT fk_auth_event_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: auth_event fk_auth_event_user_id_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.auth_event
    ADD CONSTRAINT fk_auth_event_user_id_tenant_id_app_user FOREIGN KEY (user_id, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: evidence_items fk_evidence_items_control_id_tenant_id_control_records; Type: FK CONSTRAINT; Schema: public
ALTER TABLE public.evidence_items
    ADD CONSTRAINT fk_evidence_items_control_id_tenant_id_control_records FOREIGN KEY (control_id, tenant_id) REFERENCES public.control_records(id, tenant_id);

-- Name: job_events fk_job_events_job_id_tenant_id_jobs; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT fk_job_events_job_id_tenant_id_jobs FOREIGN KEY (job_id, tenant_id) REFERENCES public.jobs(id, tenant_id);

-- Name: login_directory fk_login_directory_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT fk_login_directory_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: procrastinate_events procrastinate_events_job_id_fkey; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_events
    ADD CONSTRAINT procrastinate_events_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.procrastinate_jobs(id) ON DELETE CASCADE;

-- Name: procrastinate_jobs procrastinate_jobs_worker_id_fkey; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_jobs
    ADD CONSTRAINT procrastinate_jobs_worker_id_fkey FOREIGN KEY (worker_id) REFERENCES public.procrastinate_workers(id) ON DELETE SET NULL;

-- Name: procrastinate_periodic_defers procrastinate_periodic_defers_job_id_fkey; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.procrastinate_periodic_defers
    ADD CONSTRAINT procrastinate_periodic_defers_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.procrastinate_jobs(id);

-- Name: projects fk_projects_region_deployment_regions; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_region_deployment_regions FOREIGN KEY (region) REFERENCES public.deployment_regions(code);

-- Name: projects fk_projects_site_id_tenant_id_sites; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_site_id_tenant_id_sites FOREIGN KEY (site_id, tenant_id) REFERENCES public.sites(id, tenant_id);

-- Name: record_links fk_record_links_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.record_links
    ADD CONSTRAINT fk_record_links_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: role fk_role_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role
    ADD CONSTRAINT fk_role_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: role_assignment fk_role_assignment_approved_by_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT fk_role_assignment_approved_by_tenant_id_app_user FOREIGN KEY (approved_by, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: role_assignment fk_role_assignment_created_by_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT fk_role_assignment_created_by_tenant_id_app_user FOREIGN KEY (created_by, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: role_assignment fk_role_assignment_project_id_tenant_id_projects; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT fk_role_assignment_project_id_tenant_id_projects FOREIGN KEY (project_id, tenant_id) REFERENCES public.projects(id, tenant_id);

-- Name: role_assignment fk_role_assignment_role_id_tenant_id_role; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT fk_role_assignment_role_id_tenant_id_role FOREIGN KEY (role_id, tenant_id) REFERENCES public.role(id, tenant_id);

-- Name: role_assignment fk_role_assignment_user_id_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_assignment
    ADD CONSTRAINT fk_role_assignment_user_id_tenant_id_app_user FOREIGN KEY (user_id, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: role_permission fk_role_permission_permission_code_permission; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_permission
    ADD CONSTRAINT fk_role_permission_permission_code_permission FOREIGN KEY (permission_code) REFERENCES public.permission(code);

-- Name: role_permission fk_role_permission_role_id_tenant_id_role; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.role_permission
    ADD CONSTRAINT fk_role_permission_role_id_tenant_id_role FOREIGN KEY (role_id, tenant_id) REFERENCES public.role(id, tenant_id);

-- Name: tenant_auth_policy fk_tenant_auth_policy_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_auth_policy
    ADD CONSTRAINT fk_tenant_auth_policy_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenant_entitlement_override fk_tenant_entitlement_override_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_entitlement_override
    ADD CONSTRAINT fk_tenant_entitlement_override_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenant_feature_flags fk_tenant_feature_flags_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_feature_flags
    ADD CONSTRAINT fk_tenant_feature_flags_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenant_membership fk_tenant_membership_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_membership
    ADD CONSTRAINT fk_tenant_membership_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenant_membership fk_tenant_membership_user_id_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_membership
    ADD CONSTRAINT fk_tenant_membership_user_id_tenant_id_app_user FOREIGN KEY (user_id, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: tenant_subscription fk_tenant_subscription_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_subscription
    ADD CONSTRAINT fk_tenant_subscription_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenant_usage fk_tenant_usage_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenant_usage
    ADD CONSTRAINT fk_tenant_usage_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: tenants fk_tenants_region_code_deployment_regions; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT fk_tenants_region_code_deployment_regions FOREIGN KEY (region_code) REFERENCES public.deployment_regions(code);

-- Name: term_override fk_term_override_key_term_key; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_override
    ADD CONSTRAINT fk_term_override_key_term_key FOREIGN KEY (key) REFERENCES public.term_key(key);

-- Name: term_pack fk_term_pack_active_version_id_tenant_id_term_pack_version; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack
    ADD CONSTRAINT fk_term_pack_active_version_id_tenant_id_term_pack_version FOREIGN KEY (active_version_id, tenant_id) REFERENCES public.term_pack_version(id, tenant_id);

-- Name: term_pack_version fk_term_pack_version_pack_id_tenant_id_term_pack; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.term_pack_version
    ADD CONSTRAINT fk_term_pack_version_pack_id_tenant_id_term_pack FOREIGN KEY (pack_id, tenant_id) REFERENCES public.term_pack(id, tenant_id);

-- Name: user_session fk_user_session_user_id_tenant_id_app_user; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.user_session
    ADD CONSTRAINT fk_user_session_user_id_tenant_id_app_user FOREIGN KEY (user_id, tenant_id) REFERENCES public.app_user(id, tenant_id);

-- Name: workflow_definition_audit fk_workflow_definition_audit_definition; Type: FK CONSTRAINT; Schema: public
ALTER TABLE public.workflow_definition_audit
    ADD CONSTRAINT fk_workflow_definition_audit_definition FOREIGN KEY (definition_id, tenant_id) REFERENCES public.workflow_definitions(id, tenant_id);

-- Name: workflow_definitions fk_workflow_definitions_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT fk_workflow_definitions_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: workflow_instances fk_workflow_instances_definition; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_instances
    ADD CONSTRAINT fk_workflow_instances_definition FOREIGN KEY (definition_id, tenant_id) REFERENCES public.workflow_definitions(id, tenant_id);

-- Name: workflow_instances fk_workflow_instances_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public
ALTER TABLE ONLY public.workflow_instances
    ADD CONSTRAINT fk_workflow_instances_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

-- Name: access_settings_version_guard(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.access_settings_version_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    BEGIN
      IF NEW.access_version <= OLD.access_version THEN
        RAISE EXCEPTION 'access_version must increase' USING ERRCODE = '23514';
      END IF;
      IF NEW.deleted_at IS NOT NULL OR NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id THEN
        RAISE EXCEPTION 'access_settings rows are never deleted or moved' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$;

ALTER FUNCTION public.access_settings_version_guard() OWNER TO aip_owner;

-- Name: access_sync_permissions(jsonb); Type: FUNCTION; Schema: public
CREATE FUNCTION public.access_sync_permissions(p_catalogue jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    DECLARE
      v_modules text[];
    BEGIN
      IF p_catalogue IS NULL OR jsonb_typeof(p_catalogue) <> 'array'
         OR jsonb_array_length(p_catalogue) = 0 THEN
        RAISE EXCEPTION 'access_sync_permissions: empty or invalid catalogue'
          USING ERRCODE = '22023';
      END IF;
      PERFORM pg_advisory_xact_lock(hashtext('access_sync_permissions'));
      IF EXISTS (
        SELECT 1
        FROM jsonb_to_recordset(p_catalogue) AS e(code text, is_privileged boolean)
        JOIN public.permission AS p ON p.code = e.code
        WHERE p.is_privileged AND NOT coalesce(e.is_privileged, false)
      ) THEN
        RAISE EXCEPTION 'access_sync_permissions: a privileged permission cannot be downgraded'
          USING ERRCODE = '42501';
      END IF;
      SELECT array_agg(DISTINCT e.module_id) INTO v_modules
      FROM jsonb_to_recordset(p_catalogue) AS e(module_id text);

      INSERT INTO public.permission AS p (code, module_id, description, is_privileged)
      SELECT e.code, e.module_id, e.description, coalesce(e.is_privileged, false)
      FROM jsonb_to_recordset(p_catalogue)
        AS e(code text, module_id text, description text, is_privileged boolean)
      ON CONFLICT (code) DO UPDATE
        SET module_id = excluded.module_id,
            description = excluded.description,
            is_privileged = excluded.is_privileged,
            deprecated_at = NULL,
            updated_at = now()
        WHERE (p.module_id, p.description, p.is_privileged, p.deprecated_at)
          IS DISTINCT FROM (excluded.module_id, excluded.description, excluded.is_privileged, NULL);

      UPDATE public.permission AS p
        SET deprecated_at = now(), updated_at = now()
        WHERE p.deprecated_at IS NULL
          AND p.module_id = ANY (v_modules)
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_to_recordset(p_catalogue) AS e(code text) WHERE e.code = p.code
          );
    END;
    $$;

ALTER FUNCTION public.access_sync_permissions(p_catalogue jsonb) OWNER TO aip_owner;

-- Name: aip_convert_to_partitioned(text); Type: FUNCTION; Schema: public
CREATE FUNCTION public.aip_convert_to_partitioned(p_table text) RETURNS bigint
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    DECLARE
      v_new text := p_table || '_p';
      v_old regclass := to_regclass(format('public.%I', p_table));
      v_target regclass := to_regclass(format('public.%I', v_new));
      v_cols text;
      v_old_count bigint;
      v_new_count bigint;
      v_old_sum text;
      v_new_sum text;
      v_name text;
    BEGIN
      IF v_old IS NULL OR (SELECT relkind FROM pg_class WHERE oid = v_old) <> 'r' THEN
        RAISE EXCEPTION 'aip_convert_to_partitioned: % is not a plain table', p_table
          USING ERRCODE = '42809';
      END IF;
      IF v_target IS NULL OR (SELECT relkind FROM pg_class WHERE oid = v_target) <> 'p' THEN
        RAISE EXCEPTION 'aip_convert_to_partitioned: render % from append_only_table.sql.tpl first',
          v_new USING ERRCODE = '42809';
      END IF;
      EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', p_table);

      SELECT string_agg(format('%I', a.attname), ', ' ORDER BY a.attnum) INTO v_cols
      FROM pg_attribute AS a
      WHERE a.attrelid = v_target AND a.attnum > 0 AND NOT a.attisdropped;

      EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', p_table);
      EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', v_new);
      EXECUTE format('INSERT INTO public.%I (%s) SELECT %s FROM public.%I',
                     v_new, v_cols, v_cols, p_table);
      EXECUTE format('SELECT count(*), md5(string_agg(ROW(%s)::text, '','' ORDER BY id)) '
                     'FROM public.%I', v_cols, p_table)
        INTO v_old_count, v_old_sum;
      EXECUTE format('SELECT count(*), md5(string_agg(ROW(%s)::text, '','' ORDER BY id)) '
                     'FROM public.%I', v_cols, v_new)
        INTO v_new_count, v_new_sum;
      IF v_old_count <> v_new_count OR v_old_sum IS DISTINCT FROM v_new_sum THEN
        RAISE EXCEPTION
          'aip_convert_to_partitioned: % copy differs (count % -> %, checksum % -> %)',
          p_table, v_old_count, v_new_count, v_old_sum, v_new_sum;
      END IF;

      EXECUTE format('DROP TABLE public.%I', p_table);
      EXECUTE format('ALTER TABLE public.%I RENAME TO %I', v_new, p_table);
      EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', p_table);
      -- The template names follow the table: pk_/ix_<table>_p..., <table>_p_default, ...
      FOR v_name IN
        SELECT c.relname FROM pg_index AS i JOIN pg_class AS c ON c.oid = i.indexrelid
        WHERE i.indrelid = v_target AND strpos(c.relname, v_new) > 0
      LOOP
        EXECUTE format('ALTER INDEX public.%I RENAME TO %I',
                       v_name, replace(v_name, v_new, p_table));
      END LOOP;
      FOR v_name IN
        SELECT c.relname FROM pg_inherits AS h JOIN pg_class AS c ON c.oid = h.inhrelid
        WHERE h.inhparent = v_target AND left(c.relname, length(v_new) + 1) = v_new || '_'
      LOOP
        EXECUTE format('ALTER TABLE public.%I RENAME TO %I',
                       v_name, p_table || substr(v_name, length(v_new) + 1));
      END LOOP;
      RETURN v_new_count;
    END
    $$;

ALTER FUNCTION public.aip_convert_to_partitioned(p_table text) OWNER TO aip_owner;

-- Name: aip_ensure_partitions(text, integer); Type: FUNCTION; Schema: public
CREATE FUNCTION public.aip_ensure_partitions(p_table text, p_months_ahead integer) RETURNS SETOF text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $_$
    DECLARE
      v_parent regclass;
      v_column text;
      v_default text;
      v_month timestamp := date_trunc('month', now() AT TIME ZONE 'UTC');
      v_from timestamptz;
      v_to timestamptz;
      v_name text;
    BEGIN
      IF p_months_ahead IS NULL OR p_months_ahead NOT BETWEEN 0 AND 24 THEN
        RAISE EXCEPTION 'aip_ensure_partitions: months_ahead must be 0 to 24, got %', p_months_ahead
          USING ERRCODE = '22023';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.partition_settings AS s WHERE s.table_name = p_table) THEN
        RAISE EXCEPTION 'aip_ensure_partitions: % is not listed in partition_settings', p_table
          USING ERRCODE = '22023';
      END IF;
      SELECT pt.partrelid, a.attname, d.relname INTO v_parent, v_column, v_default
      FROM pg_partitioned_table AS pt
      JOIN pg_class AS c ON c.oid = pt.partrelid
      JOIN pg_attribute AS a ON a.attrelid = pt.partrelid AND a.attnum = pt.partattrs[0]
      LEFT JOIN pg_class AS d ON d.oid = pt.partdefid
      WHERE c.relnamespace = 'public'::regnamespace AND c.relname = p_table
        AND pt.partstrat = 'r' AND pt.partnatts = 1 AND a.atttypid = 'timestamptz'::regtype;
      IF v_parent IS NULL THEN
        RAISE EXCEPTION 'aip_ensure_partitions: % is not range-partitioned on a timestamptz column',
          p_table USING ERRCODE = '22023';
      END IF;

      FOR i IN 0..p_months_ahead LOOP
        v_from := (v_month + make_interval(months => i)) AT TIME ZONE 'UTC';
        v_to := (v_month + make_interval(months => i + 1)) AT TIME ZONE 'UTC';
        v_name := p_table || '_' || to_char(v_month + make_interval(months => i), 'YYYY_MM');
        CONTINUE WHEN to_regclass(format('public.%I', v_name)) IS NOT NULL;

        EXECUTE format('CREATE TABLE public.%I '
                       '(LIKE public.%I INCLUDING DEFAULTS INCLUDING CONSTRAINTS)',
                       v_name, p_table);
        IF v_default IS NOT NULL THEN
          -- Attaching scans the default partition anyway; lock it first so no row for this month
          -- can arrive between the move and the attach.
          EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', v_default);
          EXECUTE format('WITH moved AS (DELETE FROM public.%I '
                         'WHERE %I >= $1 AND %I < $2 RETURNING *) '
                         'INSERT INTO public.%I SELECT * FROM moved',
                         v_default, v_column, v_column, v_name)
            USING v_from, v_to;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ATTACH PARTITION public.%I '
                       'FOR VALUES FROM (%L) TO (%L)',
                       p_table, v_name, v_from, v_to);
        RETURN NEXT v_name;
      END LOOP;
    END
    $_$;

ALTER FUNCTION public.aip_ensure_partitions(p_table text, p_months_ahead integer) OWNER TO aip_owner;

-- Name: audit_log_forbid_mutation(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.audit_log_forbid_mutation() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
    BEGIN
      RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'restrict_violation';
    END
    $$;

ALTER FUNCTION public.audit_log_forbid_mutation() OWNER TO aip_owner;

-- Name: domain_events_write_once(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.domain_events_write_once() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    BEGIN
      IF OLD.published_at IS NOT NULL
         AND NEW.published_at IS DISTINCT FROM OLD.published_at THEN
        RAISE EXCEPTION 'domain_events.published_at is write-once' USING ERRCODE = '55000';
      END IF;
      IF OLD.discarded_at IS NOT NULL AND (
           NEW.discarded_at IS DISTINCT FROM OLD.discarded_at
           OR NEW.discarded_by IS DISTINCT FROM OLD.discarded_by
           OR NEW.discard_reason IS DISTINCT FROM OLD.discard_reason) THEN
        RAISE EXCEPTION 'domain_events discard columns are write-once' USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END;
    $$;

ALTER FUNCTION public.domain_events_write_once() OWNER TO aip_owner;

-- Name: identity_register_email(public.citext, uuid); Type: FUNCTION; Schema: public
CREATE FUNCTION public.identity_register_email(p_email public.citext, p_tenant uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    DECLARE
      v_owner uuid;
    BEGIN
      IF p_tenant IS NULL OR p_email IS NULL
         OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id', true), '')::uuid THEN
        RAISE EXCEPTION 'TENANT_CONTEXT_MISMATCH' USING ERRCODE = '42501';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM public.app_user AS u
        WHERE u.tenant_id = p_tenant AND u.email = p_email
          AND u.deleted_at IS NULL AND NOT u.sso_managed
      ) THEN
        RAISE EXCEPTION 'EMAIL_NOT_A_LOCAL_USER' USING ERRCODE = '42501';
      END IF;
      INSERT INTO public.login_directory (kind, key, tenant_id, idp_alias)
      VALUES ('email', p_email, p_tenant, NULL)
      ON CONFLICT (kind, key) DO NOTHING;
      SELECT d.tenant_id INTO v_owner
      FROM public.login_directory AS d
      WHERE d.kind = 'email' AND d.key = p_email;
      IF v_owner IS DISTINCT FROM p_tenant THEN
        RAISE EXCEPTION 'EMAIL_IN_OTHER_TENANT' USING ERRCODE = 'P0001';
      END IF;
    END;
    $$;

ALTER FUNCTION public.identity_register_email(p_email public.citext, p_tenant uuid) OWNER TO aip_owner;

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

-- Name: identity_resolve_session(bytea); Type: FUNCTION; Schema: public
CREATE FUNCTION public.identity_resolve_session(p_sid_hash bytea) RETURNS TABLE(tenant_id uuid, user_id uuid, session_id uuid, aal smallint, amr text[], authenticated_at timestamp with time zone, audience text, last_seen_at timestamp with time zone, idle_seconds integer, idle_expires_at timestamp with time zone, absolute_expires_at timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT s.tenant_id, s.user_id, s.id, s.aal, s.amr, s.authenticated_at, s.audience,
             s.last_seen_at, s.idle_seconds, s.idle_expires_at, s.absolute_expires_at
      FROM user_session s
      WHERE s.sid_hash = p_sid_hash
        AND s.revoked_at IS NULL AND s.deleted_at IS NULL
        AND s.idle_expires_at > now() AND s.absolute_expires_at > now()
    $$;

ALTER FUNCTION public.identity_resolve_session(p_sid_hash bytea) OWNER TO aip_owner;

-- Name: identity_sessions_by_kc_sid(text); Type: FUNCTION; Schema: public
CREATE FUNCTION public.identity_sessions_by_kc_sid(p_kc_sid text) RETURNS TABLE(tenant_id uuid, session_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT s.tenant_id, s.id FROM user_session s
      WHERE s.kc_sid = p_kc_sid AND s.revoked_at IS NULL AND s.deleted_at IS NULL
    $$;

ALTER FUNCTION public.identity_sessions_by_kc_sid(p_kc_sid text) OWNER TO aip_owner;

-- Name: outbox_dead_letters(integer, uuid); Type: FUNCTION; Schema: public
CREATE FUNCTION public.outbox_dead_letters(lim integer, after uuid) RETURNS TABLE(id uuid, tenant_id uuid, event_name text, event_version integer, attempts integer, last_error text, dead_lettered_at timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT d.id, d.tenant_id, d.event_name, d.event_version, d.attempts, d.last_error,
             d.dead_lettered_at
      FROM public.domain_events AS d
      WHERE d.dead_lettered_at IS NOT NULL
        AND d.discarded_at IS NULL
        AND d.published_at IS NULL
        AND (after IS NULL OR d.id > after)
      ORDER BY d.id
      LIMIT least(greatest(coalesce(lim, 50), 1), 500);
    $$;

ALTER FUNCTION public.outbox_dead_letters(lim integer, after uuid) OWNER TO aip_owner;

-- Name: outbox_discard(uuid, text, uuid); Type: FUNCTION; Schema: public
CREATE FUNCTION public.outbox_discard(event_id uuid, reason text, actor uuid) RETURNS TABLE(event_name text, event_version integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    BEGIN
      IF reason IS NULL OR btrim(reason) = '' THEN
        RAISE EXCEPTION 'a discard reason is required' USING ERRCODE = '22023';
      END IF;
      RETURN QUERY
      UPDATE public.domain_events AS d
         SET discarded_at = now(), discarded_by = actor, discard_reason = btrim(reason)
       WHERE d.id = event_id
         AND d.dead_lettered_at IS NOT NULL
         AND d.discarded_at IS NULL
         AND d.published_at IS NULL
      RETURNING d.event_name, d.event_version;
    END;
    $$;

ALTER FUNCTION public.outbox_discard(event_id uuid, reason text, actor uuid) OWNER TO aip_owner;

-- Name: outbox_retry(uuid); Type: FUNCTION; Schema: public
CREATE FUNCTION public.outbox_retry(event_id uuid) RETURNS TABLE(event_name text, event_version integer)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      UPDATE public.domain_events AS d
         SET dead_lettered_at = NULL, attempts = 0, next_attempt_at = NULL
       WHERE d.id = event_id
         AND d.dead_lettered_at IS NOT NULL
         AND d.discarded_at IS NULL
         AND d.published_at IS NULL
      RETURNING d.event_name, d.event_version;
    $$;

ALTER FUNCTION public.outbox_retry(event_id uuid) OWNER TO aip_owner;

-- Name: platform_event_counts(timestamp with time zone); Type: FUNCTION; Schema: public
CREATE FUNCTION public.platform_event_counts(since timestamp with time zone) RETURNS TABLE(event_name text, event_version integer, published bigint, failed bigint)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT d.event_name, d.event_version,
             count(*) FILTER (WHERE d.published_at IS NOT NULL) AS published,
             count(*) FILTER (WHERE d.dead_lettered_at IS NOT NULL) AS failed
      FROM public.domain_events AS d
      WHERE d.occurred_at >= since
      GROUP BY d.event_name, d.event_version;
    $$;

ALTER FUNCTION public.platform_event_counts(since timestamp with time zone) OWNER TO aip_owner;

-- Name: procrastinate_cancel_job_v1(bigint, boolean, boolean); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_cancel_job_v1(job_id bigint, abort boolean, delete_job boolean) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status = 'todo'
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        IF abort THEN
            UPDATE procrastinate_jobs
            SET abort_requested = true,
                status = CASE status
                    WHEN 'todo' THEN 'cancelled'::procrastinate_job_status ELSE status
                END
            WHERE id = job_id AND status IN ('todo', 'doing')
            RETURNING id INTO _job_id;
        ELSE
            UPDATE procrastinate_jobs
            SET status = 'cancelled'::procrastinate_job_status
            WHERE id = job_id AND status = 'todo'
            RETURNING id INTO _job_id;
        END IF;
    END IF;
    RETURN _job_id;
END;
$$;

ALTER FUNCTION public.procrastinate_cancel_job_v1(job_id bigint, abort boolean, delete_job boolean) OWNER TO aip_owner;

-- Name: procrastinate_defer_jobs_v1(public.procrastinate_job_to_defer_v1[]); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_defer_jobs_v1(jobs public.procrastinate_job_to_defer_v1[]) RETURNS bigint[]
    LANGUAGE plpgsql
    AS $$
DECLARE
    job_ids bigint[];
BEGIN
    WITH inserted_jobs AS (
        INSERT INTO procrastinate_jobs (queue_name, task_name, priority, lock, queueing_lock, args, scheduled_at)
        SELECT (job).queue_name,
               (job).task_name,
               (job).priority,
               (job).lock,
               (job).queueing_lock,
               (job).args,
               (job).scheduled_at
        FROM unnest(jobs) AS job
        RETURNING id
    )
    SELECT array_agg(id) FROM inserted_jobs INTO job_ids;

    RETURN job_ids;
END;
$$;

ALTER FUNCTION public.procrastinate_defer_jobs_v1(jobs public.procrastinate_job_to_defer_v1[]) OWNER TO aip_owner;

-- Name: procrastinate_defer_periodic_job_v2(character varying, character varying, character varying, character varying, integer, character varying, bigint, jsonb); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_defer_periodic_job_v2(_queue_name character varying, _lock character varying, _queueing_lock character varying, _task_name character varying, _priority integer, _periodic_id character varying, _defer_timestamp bigint, _args jsonb) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
	_job_id bigint;
	_defer_id bigint;
BEGIN
    INSERT
        INTO procrastinate_periodic_defers (task_name, periodic_id, defer_timestamp)
        VALUES (_task_name, _periodic_id, _defer_timestamp)
        ON CONFLICT DO NOTHING
        RETURNING id into _defer_id;

    IF _defer_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE procrastinate_periodic_defers
        SET job_id = (
            SELECT COALESCE((
                SELECT unnest(procrastinate_defer_jobs_v1(
                    ARRAY[
                        ROW(
                            _queue_name,
                            _task_name,
                            _priority,
                            _lock,
                            _queueing_lock,
                            _args,
                            NULL::timestamptz
                        )
                    ]::procrastinate_job_to_defer_v1[]
                ))
            ), NULL)
        )
        WHERE id = _defer_id
        RETURNING job_id INTO _job_id;

    DELETE
        FROM procrastinate_periodic_defers
        USING (
            SELECT id
            FROM procrastinate_periodic_defers
            WHERE procrastinate_periodic_defers.task_name = _task_name
            AND procrastinate_periodic_defers.periodic_id = _periodic_id
            AND procrastinate_periodic_defers.defer_timestamp < _defer_timestamp
            ORDER BY id
            FOR UPDATE
        ) to_delete
        WHERE procrastinate_periodic_defers.id = to_delete.id;

    RETURN _job_id;
END;
$$;

ALTER FUNCTION public.procrastinate_defer_periodic_job_v2(_queue_name character varying, _lock character varying, _queueing_lock character varying, _task_name character varying, _priority integer, _periodic_id character varying, _defer_timestamp bigint, _args jsonb) OWNER TO aip_owner;

-- Name: procrastinate_fetch_job_v2(character varying[], bigint); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_fetch_job_v2(target_queue_names character varying[], p_worker_id bigint) RETURNS public.procrastinate_jobs
    LANGUAGE plpgsql
    AS $$
DECLARE
	found_jobs procrastinate_jobs;
BEGIN
    WITH candidate AS (
        SELECT jobs.*
            FROM procrastinate_jobs AS jobs
            WHERE
                -- reject the job if its lock has earlier or higher priority jobs
                NOT EXISTS (
                    SELECT 1
                        FROM procrastinate_jobs AS other_jobs
                        WHERE
                            jobs.lock IS NOT NULL
                            AND other_jobs.lock = jobs.lock
                            AND (
                                -- job with same lock is already running
                                other_jobs.status = 'doing'
                                OR
                                -- job with same lock is waiting and has higher priority (or same priority but was queued first)
                                (
                                    other_jobs.status = 'todo'
                                    AND (
                                        other_jobs.priority > jobs.priority
                                        OR (
                                        other_jobs.priority = jobs.priority
                                        AND other_jobs.id < jobs.id
                                        )
                                    )
                                )
                            )
                )
                AND jobs.status = 'todo'
                AND (target_queue_names IS NULL OR jobs.queue_name = ANY( target_queue_names ))
                AND (jobs.scheduled_at IS NULL OR jobs.scheduled_at <= now())
            ORDER BY jobs.priority DESC, jobs.id ASC LIMIT 1
            FOR UPDATE OF jobs SKIP LOCKED
    )
    UPDATE procrastinate_jobs
        SET status = 'doing', worker_id = p_worker_id
        FROM candidate
        WHERE procrastinate_jobs.id = candidate.id
        RETURNING procrastinate_jobs.* INTO found_jobs;

 RETURN found_jobs;
END;
$$;

ALTER FUNCTION public.procrastinate_fetch_job_v2(target_queue_names character varying[], p_worker_id bigint) OWNER TO aip_owner;

-- Name: procrastinate_finish_job_v1(bigint, public.procrastinate_job_status, boolean); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_finish_job_v1(job_id bigint, end_status public.procrastinate_job_status, delete_job boolean) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF end_status NOT IN ('succeeded', 'failed', 'aborted') THEN
        RAISE 'End status should be either "succeeded", "failed" or "aborted" (job id: %)', job_id;
    END IF;
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = end_status,
            abort_requested = false,
            attempts = CASE status
                WHEN 'doing' THEN attempts + 1 ELSE attempts
            END
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" or "todo" status (job id: %)', job_id;
    END IF;
END;
$$;

ALTER FUNCTION public.procrastinate_finish_job_v1(job_id bigint, end_status public.procrastinate_job_status, delete_job boolean) OWNER TO aip_owner;

-- Name: procrastinate_notify_queue_abort_job_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_notify_queue_abort_job_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'abort_job_requested', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_notify_queue_abort_job_v1() OWNER TO aip_owner;

-- Name: procrastinate_notify_queue_job_inserted_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_notify_queue_job_inserted_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'job_inserted', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_notify_queue_job_inserted_v1() OWNER TO aip_owner;

-- Name: procrastinate_prune_stalled_workers_v1(double precision); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_prune_stalled_workers_v1(seconds_since_heartbeat double precision) RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    DELETE FROM procrastinate_workers
    WHERE last_heartbeat < NOW() - (seconds_since_heartbeat || 'SECOND')::INTERVAL
    RETURNING procrastinate_workers.id;
END;
$$;

ALTER FUNCTION public.procrastinate_prune_stalled_workers_v1(seconds_since_heartbeat double precision) OWNER TO aip_owner;

-- Name: procrastinate_register_worker_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_register_worker_v1() RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    INSERT INTO procrastinate_workers DEFAULT VALUES
    RETURNING procrastinate_workers.id;
END;
$$;

ALTER FUNCTION public.procrastinate_register_worker_v1() OWNER TO aip_owner;

-- Name: procrastinate_retry_job_v1(bigint, timestamp with time zone, integer, character varying, character varying); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_retry_job_v1(job_id bigint, retry_at timestamp with time zone, new_priority integer, new_queue_name character varying, new_lock character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
BEGIN
    SELECT abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status = 'doing'
    FOR UPDATE
    INTO _abort_requested;
    IF _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" status (job id: %)', job_id;
    END IF;
END;
$$;

ALTER FUNCTION public.procrastinate_retry_job_v1(job_id bigint, retry_at timestamp with time zone, new_priority integer, new_queue_name character varying, new_lock character varying) OWNER TO aip_owner;

-- Name: procrastinate_retry_job_v2(bigint, timestamp with time zone, integer, character varying, character varying); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_retry_job_v2(job_id bigint, retry_at timestamp with time zone, new_priority integer, new_queue_name character varying, new_lock character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
    _current_status procrastinate_job_status;
BEGIN
    SELECT status, abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status IN ('doing', 'failed')
    FOR UPDATE
    INTO _current_status, _abort_requested;
    IF _current_status = 'doing' AND _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status IN ('doing', 'failed')
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or has an invalid status to retry (job id: %)', job_id;
    END IF;

END;
$$;

ALTER FUNCTION public.procrastinate_retry_job_v2(job_id bigint, retry_at timestamp with time zone, new_priority integer, new_queue_name character varying, new_lock character varying) OWNER TO aip_owner;

-- Name: procrastinate_trigger_abort_requested_events_procedure_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_trigger_abort_requested_events_procedure_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'abort_requested'::procrastinate_job_event_type);
    RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_trigger_abort_requested_events_procedure_v1() OWNER TO aip_owner;

-- Name: procrastinate_trigger_function_scheduled_events_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_trigger_function_scheduled_events_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type, at)
        VALUES (NEW.id, 'scheduled'::procrastinate_job_event_type, NEW.scheduled_at);

	RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_trigger_function_scheduled_events_v1() OWNER TO aip_owner;

-- Name: procrastinate_trigger_function_status_events_insert_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_trigger_function_status_events_insert_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'deferred'::procrastinate_job_event_type);
	RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_trigger_function_status_events_insert_v1() OWNER TO aip_owner;

-- Name: procrastinate_trigger_function_status_events_update_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_trigger_function_status_events_update_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    WITH t AS (
        SELECT CASE
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND NEW.status = 'doing'::procrastinate_job_status
                THEN 'started'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'deferred_for_retry'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'failed'::procrastinate_job_status
                THEN 'failed'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'succeeded'::procrastinate_job_status
                THEN 'succeeded'::procrastinate_job_event_type
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND (
                    NEW.status = 'cancelled'::procrastinate_job_status
                    OR NEW.status = 'failed'::procrastinate_job_status
                    OR NEW.status = 'succeeded'::procrastinate_job_status
                )
                THEN 'cancelled'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'aborted'::procrastinate_job_status
                THEN 'aborted'::procrastinate_job_event_type
            WHEN OLD.status = 'failed'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'retried'::procrastinate_job_event_type
            ELSE NULL
        END as event_type
    )
    INSERT INTO procrastinate_events(job_id, type)
        SELECT NEW.id, t.event_type
        FROM t
        WHERE t.event_type IS NOT NULL;
	RETURN NEW;
END;
$$;

ALTER FUNCTION public.procrastinate_trigger_function_status_events_update_v1() OWNER TO aip_owner;

-- Name: procrastinate_unlink_periodic_defers_v1(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_unlink_periodic_defers_v1() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE procrastinate_periodic_defers
    SET job_id = NULL
    WHERE job_id = OLD.id;
    RETURN OLD;
END;
$$;

ALTER FUNCTION public.procrastinate_unlink_periodic_defers_v1() OWNER TO aip_owner;

-- Name: procrastinate_unregister_worker_v1(bigint); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_unregister_worker_v1(worker_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    DELETE FROM procrastinate_workers
    WHERE id = worker_id;
END;
$$;

ALTER FUNCTION public.procrastinate_unregister_worker_v1(worker_id bigint) OWNER TO aip_owner;

-- Name: procrastinate_update_heartbeat_v1(bigint); Type: FUNCTION; Schema: public
CREATE FUNCTION public.procrastinate_update_heartbeat_v1(worker_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE procrastinate_workers
    SET last_heartbeat = NOW()
    WHERE id = worker_id;
END;
$$;

ALTER FUNCTION public.procrastinate_update_heartbeat_v1(worker_id bigint) OWNER TO aip_owner;

-- Name: security_audit_events_forbid_mutation(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.security_audit_events_forbid_mutation() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
    BEGIN
      RAISE EXCEPTION 'security_audit_events is append-only' USING ERRCODE = 'restrict_violation';
    END
    $$;

ALTER FUNCTION public.security_audit_events_forbid_mutation() OWNER TO aip_owner;

-- Name: tenancy_has_real_customer(); Type: FUNCTION; Schema: public
CREATE FUNCTION public.tenancy_has_real_customer() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
      SELECT EXISTS (SELECT 1 FROM tenants WHERE is_real_customer AND deleted_at IS NULL)
    $$;

ALTER FUNCTION public.tenancy_has_real_customer() OWNER TO aip_owner;

-- Name: evidence_items_default_tenant_id_control_id_collected_at_idx; Type: INDEX; Schema: public
CREATE INDEX evidence_items_default_tenant_id_control_id_collected_at_idx ON public.evidence_items_default USING btree (tenant_id, control_id, collected_at DESC);

-- Name: evidence_items_default_tenant_id_idx; Type: INDEX; Schema: public
CREATE INDEX evidence_items_default_tenant_id_idx ON public.evidence_items_default USING btree (tenant_id);

-- Name: idx_procrastinate_jobs_worker_not_null; Type: INDEX; Schema: public
CREATE INDEX idx_procrastinate_jobs_worker_not_null ON public.procrastinate_jobs USING btree (worker_id) WHERE ((worker_id IS NOT NULL) AND (status = 'doing'::public.procrastinate_job_status));

-- Name: idx_procrastinate_workers_last_heartbeat; Type: INDEX; Schema: public
CREATE INDEX idx_procrastinate_workers_last_heartbeat ON public.procrastinate_workers USING btree (last_heartbeat);

-- Name: ix_access_reviews_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_access_reviews_tenant_id ON public.access_reviews USING btree (tenant_id);

-- Name: ix_access_settings_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_access_settings_tenant_id ON public.access_settings USING btree (tenant_id);

-- Name: ix_app_user_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_app_user_tenant_id ON public.app_user USING btree (tenant_id);

-- Name: ix_app_user_tenant_id_organisation_id; Type: INDEX; Schema: public
CREATE INDEX ix_app_user_tenant_id_organisation_id ON public.app_user USING btree (tenant_id, organisation_id);

-- Name: ix_app_user_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_app_user_tenant_id_status ON public.app_user USING btree (tenant_id, status) WHERE (deleted_at IS NULL);

-- Name: ix_audit_log_asset_path; Type: INDEX; Schema: public
CREATE INDEX ix_audit_log_asset_path ON public.audit_log USING gist (asset_path);

-- Name: ix_audit_log_flags; Type: INDEX; Schema: public
CREATE INDEX ix_audit_log_flags ON public.audit_log USING gin (flags) WHERE (flags <> '{}'::text[]);

-- Name: ix_audit_log_record_table_record_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_audit_log_record_table_record_id_occurred_at ON public.audit_log USING btree (record_table, record_id, occurred_at);

-- Name: ix_audit_log_tenant_id_actor_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_audit_log_tenant_id_actor_id_occurred_at ON public.audit_log USING btree (tenant_id, actor_id, occurred_at);

-- Name: ix_audit_log_tenant_id_project_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_audit_log_tenant_id_project_id_occurred_at ON public.audit_log USING btree (tenant_id, project_id, occurred_at DESC);

-- Name: ix_auth_event_tenant_id_event_type_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_auth_event_tenant_id_event_type_occurred_at ON public.auth_event USING btree (tenant_id, event_type, occurred_at);

-- Name: ix_auth_event_tenant_id_user_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_auth_event_tenant_id_user_id_occurred_at ON public.auth_event USING btree (tenant_id, user_id, occurred_at DESC);

-- Name: ix_breach_incidents_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_breach_incidents_tenant_id ON public.breach_incidents USING btree (tenant_id);

-- Name: ix_breach_incidents_tenant_id_assessment_due_at; Type: INDEX; Schema: public
CREATE INDEX ix_breach_incidents_tenant_id_assessment_due_at ON public.breach_incidents USING btree (tenant_id, assessment_due_at) WHERE (status = ANY (ARRAY['open'::text, 'assessing'::text]));

-- Name: ix_breach_incidents_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_breach_incidents_tenant_id_status ON public.breach_incidents USING btree (tenant_id, status);

-- Name: ix_control_records_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_control_records_tenant_id ON public.control_records USING btree (tenant_id);

-- Name: ix_control_records_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_control_records_tenant_id_status ON public.control_records USING btree (tenant_id, status);

-- Name: ix_data_map_entries_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_data_map_entries_tenant_id ON public.data_map_entries USING btree (tenant_id);

-- Name: ix_data_map_entries_tenant_id_classification; Type: INDEX; Schema: public
CREATE INDEX ix_data_map_entries_tenant_id_classification ON public.data_map_entries USING btree (tenant_id, classification);

-- Name: ix_domain_events_aggregate_type_aggregate_id; Type: INDEX; Schema: public
CREATE INDEX ix_domain_events_aggregate_type_aggregate_id ON public.domain_events USING btree (aggregate_type, aggregate_id);

-- Name: ix_domain_events_asset_id; Type: INDEX; Schema: public
CREATE INDEX ix_domain_events_asset_id ON public.domain_events USING btree (asset_id);

-- Name: ix_domain_events_event_name_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_domain_events_event_name_occurred_at ON public.domain_events USING btree (event_name, occurred_at);

-- Name: ix_domain_events_pending; Type: INDEX; Schema: public
CREATE INDEX ix_domain_events_pending ON public.domain_events USING btree (occurred_at) WHERE ((published_at IS NULL) AND (dead_lettered_at IS NULL) AND (discarded_at IS NULL));

-- Name: ix_domain_events_tenant_id_dead_letter; Type: INDEX; Schema: public
CREATE INDEX ix_domain_events_tenant_id_dead_letter ON public.domain_events USING btree (tenant_id) WHERE ((dead_lettered_at IS NOT NULL) AND (discarded_at IS NULL));

-- Name: ix_evidence_items_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_evidence_items_tenant_id ON ONLY public.evidence_items USING btree (tenant_id);

-- Name: ix_evidence_items_tenant_id_control_id_collected_at; Type: INDEX; Schema: public
CREATE INDEX ix_evidence_items_tenant_id_control_id_collected_at ON ONLY public.evidence_items USING btree (tenant_id, control_id, collected_at DESC);

-- Name: ix_glossary_entry_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_glossary_entry_tenant_id ON public.glossary_entry USING btree (tenant_id);

-- Name: ix_glossary_entry_tenant_id_abbreviation; Type: INDEX; Schema: public
CREATE INDEX ix_glossary_entry_tenant_id_abbreviation ON public.glossary_entry USING btree (tenant_id, abbreviation);

-- Name: ix_glossary_entry_tenant_id_neutral_concept_code; Type: INDEX; Schema: public
CREATE INDEX ix_glossary_entry_tenant_id_neutral_concept_code ON public.glossary_entry USING btree (tenant_id, neutral_concept_code);

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

-- Name: ix_locale_settings_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_locale_settings_tenant_id ON public.locale_settings USING btree (tenant_id);

-- Name: ix_login_directory_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_login_directory_tenant_id ON public.login_directory USING btree (tenant_id);

-- Name: ix_organisations_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_organisations_tenant_id ON public.organisations USING btree (tenant_id);

-- Name: ix_organisations_tenant_id_org_type; Type: INDEX; Schema: public
CREATE INDEX ix_organisations_tenant_id_org_type ON public.organisations USING btree (tenant_id, org_type);

-- Name: ix_permission_module_id; Type: INDEX; Schema: public
CREATE INDEX ix_permission_module_id ON public.permission USING btree (module_id);

-- Name: ix_projects_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_projects_tenant_id ON public.projects USING btree (tenant_id);

-- Name: ix_projects_tenant_id_site_id; Type: INDEX; Schema: public
CREATE INDEX ix_projects_tenant_id_site_id ON public.projects USING btree (tenant_id, site_id);

-- Name: ix_projects_tenant_id_status; Type: INDEX; Schema: public
CREATE INDEX ix_projects_tenant_id_status ON public.projects USING btree (tenant_id, status);

-- Name: ix_provenance_entries_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_provenance_entries_tenant_id ON ONLY public.provenance_entries USING btree (tenant_id);

-- Name: ix_provenance_entries_tenant_id_recorded_at; Type: INDEX; Schema: public
CREATE INDEX ix_provenance_entries_tenant_id_recorded_at ON ONLY public.provenance_entries USING btree (tenant_id, recorded_at DESC);

-- Name: ix_record_links_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_record_links_tenant_id ON public.record_links USING btree (tenant_id);

-- Name: ix_record_links_to; Type: INDEX; Schema: public
CREATE INDEX ix_record_links_to ON public.record_links USING btree (tenant_id, to_type, to_id) WHERE (deleted_at IS NULL);

-- Name: ix_restore_test_records_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_restore_test_records_tenant_id ON ONLY public.restore_test_records USING btree (tenant_id);

-- Name: ix_restore_test_records_tenant_id_created_at; Type: INDEX; Schema: public
CREATE INDEX ix_restore_test_records_tenant_id_created_at ON ONLY public.restore_test_records USING btree (tenant_id, created_at DESC);

-- Name: ix_role_assignment_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_assignment_tenant_id ON public.role_assignment USING btree (tenant_id);

-- Name: ix_role_assignment_tenant_id_project_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_assignment_tenant_id_project_id ON public.role_assignment USING btree (tenant_id, project_id);

-- Name: ix_role_assignment_tenant_id_role_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_assignment_tenant_id_role_id ON public.role_assignment USING btree (tenant_id, role_id);

-- Name: ix_role_assignment_tenant_id_user_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_assignment_tenant_id_user_id ON public.role_assignment USING btree (tenant_id, user_id);

-- Name: ix_role_permission_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_permission_tenant_id ON public.role_permission USING btree (tenant_id);

-- Name: ix_role_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_role_tenant_id ON public.role USING btree (tenant_id);

-- Name: ix_security_audit_events_tenant_id_actor_id_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_security_audit_events_tenant_id_actor_id_occurred_at ON public.security_audit_events USING btree (tenant_id, actor_id, occurred_at);

-- Name: ix_security_audit_events_tenant_id_event_type_occurred_at; Type: INDEX; Schema: public
CREATE INDEX ix_security_audit_events_tenant_id_event_type_occurred_at ON public.security_audit_events USING btree (tenant_id, event_type, occurred_at);

-- Name: ix_sites_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_sites_tenant_id ON public.sites USING btree (tenant_id);

-- Name: ix_tenant_entitlement_override_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_entitlement_override_tenant_id ON public.tenant_entitlement_override USING btree (tenant_id);

-- Name: ix_tenant_entitlement_override_tenant_id_key; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_entitlement_override_tenant_id_key ON public.tenant_entitlement_override USING btree (tenant_id, key) WHERE (deleted_at IS NULL);

-- Name: ix_tenant_feature_flags_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_feature_flags_tenant_id ON public.tenant_feature_flags USING btree (tenant_id);

-- Name: ix_tenant_membership_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_membership_tenant_id ON public.tenant_membership USING btree (tenant_id);

-- Name: ix_tenant_membership_tenant_id_user_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_membership_tenant_id_user_id ON public.tenant_membership USING btree (tenant_id, user_id);

-- Name: ix_tenant_subscription_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_subscription_tenant_id ON public.tenant_subscription USING btree (tenant_id);

-- Name: ix_tenant_usage_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_tenant_usage_tenant_id ON public.tenant_usage USING btree (tenant_id);

-- Name: ix_tenants_region_code; Type: INDEX; Schema: public
CREATE INDEX ix_tenants_region_code ON public.tenants USING btree (region_code);

-- Name: ix_tenants_status; Type: INDEX; Schema: public
CREATE INDEX ix_tenants_status ON public.tenants USING btree (status);

-- Name: ix_term_alias_alias_trgm; Type: INDEX; Schema: public
CREATE INDEX ix_term_alias_alias_trgm ON public.term_alias USING gin (alias public.gin_trgm_ops);

-- Name: ix_term_alias_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_alias_tenant_id ON public.term_alias USING btree (tenant_id);

-- Name: ix_term_key_module_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_key_module_id ON public.term_key USING btree (module_id);

-- Name: ix_term_key_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_key_tenant_id ON public.term_key USING btree (tenant_id);

-- Name: ix_term_override_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_override_tenant_id ON public.term_override USING btree (tenant_id);

-- Name: ix_term_override_tenant_id_key; Type: INDEX; Schema: public
CREATE INDEX ix_term_override_tenant_id_key ON public.term_override USING btree (tenant_id, key);

-- Name: ix_term_pack_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_pack_tenant_id ON public.term_pack USING btree (tenant_id);

-- Name: ix_term_pack_version_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_term_pack_version_tenant_id ON public.term_pack_version USING btree (tenant_id);

-- Name: ix_upload_sessions_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_upload_sessions_tenant_id ON public.upload_sessions USING btree (tenant_id);

-- Name: ix_upload_sessions_tenant_requested_by_created; Type: INDEX; Schema: public
CREATE INDEX ix_upload_sessions_tenant_requested_by_created ON public.upload_sessions USING btree (tenant_id, requested_by, created_at DESC);

-- Name: ix_upload_sessions_tenant_status_expires; Type: INDEX; Schema: public
CREATE INDEX ix_upload_sessions_tenant_status_expires ON public.upload_sessions USING btree (tenant_id, status, expires_at);

-- Name: ix_user_session_kc_sid; Type: INDEX; Schema: public
CREATE INDEX ix_user_session_kc_sid ON public.user_session USING btree (kc_sid) WHERE (revoked_at IS NULL);

-- Name: ix_user_session_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_user_session_tenant_id ON public.user_session USING btree (tenant_id);

-- Name: ix_user_session_tenant_id_user_id; Type: INDEX; Schema: public
CREATE INDEX ix_user_session_tenant_id_user_id ON public.user_session USING btree (tenant_id, user_id) WHERE (revoked_at IS NULL);

-- Name: ix_workflow_definition_audit_definition_id; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_definition_audit_definition_id ON ONLY public.workflow_definition_audit USING btree (tenant_id, definition_id, created_at);

-- Name: ix_workflow_definition_audit_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_definition_audit_tenant_id ON ONLY public.workflow_definition_audit USING btree (tenant_id);

-- Name: ix_workflow_definitions_resolve; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_definitions_resolve ON public.workflow_definitions USING btree (tenant_id, record_type, project_id, status) WHERE (deleted_at IS NULL);

-- Name: ix_workflow_definitions_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_definitions_tenant_id ON public.workflow_definitions USING btree (tenant_id);

-- Name: ix_workflow_instances_definition_id; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_instances_definition_id ON public.workflow_instances USING btree (tenant_id, definition_id);

-- Name: ix_workflow_instances_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_workflow_instances_tenant_id ON public.workflow_instances USING btree (tenant_id);

-- Name: procrastinate_events_job_id_fkey_v1; Type: INDEX; Schema: public
CREATE INDEX procrastinate_events_job_id_fkey_v1 ON public.procrastinate_events USING btree (job_id);

-- Name: procrastinate_jobs_id_lock_idx_v1; Type: INDEX; Schema: public
CREATE INDEX procrastinate_jobs_id_lock_idx_v1 ON public.procrastinate_jobs USING btree (id, lock) WHERE (status = ANY (ARRAY['todo'::public.procrastinate_job_status, 'doing'::public.procrastinate_job_status]));

-- Name: procrastinate_jobs_lock_idx_v1; Type: INDEX; Schema: public
CREATE UNIQUE INDEX procrastinate_jobs_lock_idx_v1 ON public.procrastinate_jobs USING btree (lock) WHERE (status = 'doing'::public.procrastinate_job_status);

-- Name: procrastinate_jobs_priority_idx_v1; Type: INDEX; Schema: public
CREATE INDEX procrastinate_jobs_priority_idx_v1 ON public.procrastinate_jobs USING btree (priority DESC, id) WHERE (status = 'todo'::public.procrastinate_job_status);

-- Name: procrastinate_jobs_queue_name_idx_v1; Type: INDEX; Schema: public
CREATE INDEX procrastinate_jobs_queue_name_idx_v1 ON public.procrastinate_jobs USING btree (queue_name);

-- Name: procrastinate_jobs_queueing_lock_idx_v1; Type: INDEX; Schema: public
CREATE UNIQUE INDEX procrastinate_jobs_queueing_lock_idx_v1 ON public.procrastinate_jobs USING btree (queueing_lock) WHERE (status = 'todo'::public.procrastinate_job_status);

-- Name: procrastinate_periodic_defers_job_id_fkey_v1; Type: INDEX; Schema: public
CREATE INDEX procrastinate_periodic_defers_job_id_fkey_v1 ON public.procrastinate_periodic_defers USING btree (job_id);

-- Name: provenance_entries_default_tenant_id_idx; Type: INDEX; Schema: public
CREATE INDEX provenance_entries_default_tenant_id_idx ON public.provenance_entries_default USING btree (tenant_id);

-- Name: provenance_entries_default_tenant_id_recorded_at_idx; Type: INDEX; Schema: public
CREATE INDEX provenance_entries_default_tenant_id_recorded_at_idx ON public.provenance_entries_default USING btree (tenant_id, recorded_at DESC);

-- Name: restore_test_records_default_tenant_id_created_at_idx; Type: INDEX; Schema: public
CREATE INDEX restore_test_records_default_tenant_id_created_at_idx ON public.restore_test_records_default USING btree (tenant_id, created_at DESC);

-- Name: restore_test_records_default_tenant_id_idx; Type: INDEX; Schema: public
CREATE INDEX restore_test_records_default_tenant_id_idx ON public.restore_test_records_default USING btree (tenant_id);

-- Name: uq_access_reviews_tenant_id_quarter; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_access_reviews_tenant_id_quarter ON public.access_reviews USING btree (tenant_id, quarter) WHERE (deleted_at IS NULL);

-- Name: uq_access_settings_tenant_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_access_settings_tenant_id ON public.access_settings USING btree (tenant_id) WHERE (deleted_at IS NULL);

-- Name: uq_app_user_tenant_id_email; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_app_user_tenant_id_email ON public.app_user USING btree (tenant_id, email) WHERE (deleted_at IS NULL);

-- Name: uq_app_user_tenant_id_keycloak_user_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_app_user_tenant_id_keycloak_user_id ON public.app_user USING btree (tenant_id, keycloak_user_id) WHERE (keycloak_user_id IS NOT NULL);

-- Name: uq_audit_log_tenant_id_source_event_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_audit_log_tenant_id_source_event_id ON public.audit_log USING btree (tenant_id, source_event_id) WHERE (source_event_id IS NOT NULL);

-- Name: uq_control_records_tenant_id_control_key; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_control_records_tenant_id_control_key ON public.control_records USING btree (tenant_id, control_key) WHERE (deleted_at IS NULL);

-- Name: uq_jobs_tenant_id_job_type_idempotency_key; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_jobs_tenant_id_job_type_idempotency_key ON public.jobs USING btree (tenant_id, job_type, idempotency_key) WHERE (idempotency_key IS NOT NULL);

-- Name: uq_locale_settings_tenant_id_project_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_locale_settings_tenant_id_project_id ON public.locale_settings USING btree (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)) WHERE (deleted_at IS NULL);

-- Name: uq_organisations_tenant_id_lower_name; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_organisations_tenant_id_lower_name ON public.organisations USING btree (tenant_id, lower(name)) WHERE (deleted_at IS NULL);

-- Name: uq_projects_tenant_id_upper_code; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_projects_tenant_id_upper_code ON public.projects USING btree (tenant_id, upper(code)) WHERE (deleted_at IS NULL);

-- Name: uq_role_assignment_live; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_role_assignment_live ON public.role_assignment USING btree (tenant_id, user_id, role_id, scope_type, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)) WHERE ((deleted_at IS NULL) AND (scope_type = ANY (ARRAY['tenant'::text, 'project'::text])));

-- Name: uq_role_permission_role_id_permission_code; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_role_permission_role_id_permission_code ON public.role_permission USING btree (role_id, permission_code) WHERE (deleted_at IS NULL);

-- Name: uq_role_tenant_id_code; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_role_tenant_id_code ON public.role USING btree (tenant_id, code) WHERE (deleted_at IS NULL);

-- Name: uq_security_audit_events_tenant_id_source_event_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_security_audit_events_tenant_id_source_event_id ON public.security_audit_events USING btree (tenant_id, source_event_id) WHERE (source_event_id IS NOT NULL);

-- Name: uq_sites_tenant_id_upper_code; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_sites_tenant_id_upper_code ON public.sites USING btree (tenant_id, upper(code)) WHERE (deleted_at IS NULL);

-- Name: uq_tenant_membership_tenant_id_user_id_organisation_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_tenant_membership_tenant_id_user_id_organisation_id ON public.tenant_membership USING btree (tenant_id, user_id, organisation_id) NULLS NOT DISTINCT WHERE (deleted_at IS NULL);

-- Name: uq_term_alias_tenant_id_alias_target_type_locale; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_term_alias_tenant_id_alias_target_type_locale ON public.term_alias USING btree (tenant_id, alias, target_type, locale) WHERE (deleted_at IS NULL);

-- Name: uq_term_key_key; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_term_key_key ON public.term_key USING btree (key);

-- Name: uq_term_override_scope_key_locale; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_term_override_scope_key_locale ON public.term_override USING btree (tenant_id, level, COALESCE(client_org_id, project_id, '00000000-0000-0000-0000-000000000000'::uuid), key, locale) WHERE (deleted_at IS NULL);

-- Name: uq_term_pack_tenant_id_code; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_term_pack_tenant_id_code ON public.term_pack USING btree (tenant_id, code);

-- Name: uq_term_pack_version_pack_id_version; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_term_pack_version_pack_id_version ON public.term_pack_version USING btree (pack_id, version);

-- Name: uq_upload_sessions_client_request_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX uq_upload_sessions_client_request_id ON public.upload_sessions USING btree (tenant_id, requested_by, client_request_id) WHERE (client_request_id IS NOT NULL);

-- Name: ux_record_links_live; Type: INDEX; Schema: public
CREATE UNIQUE INDEX ux_record_links_live ON public.record_links USING btree (tenant_id, from_type, from_id, to_type, to_id, link_kind) WHERE (deleted_at IS NULL);

-- Name: ux_tenant_feature_flags_live; Type: INDEX; Schema: public
CREATE UNIQUE INDEX ux_tenant_feature_flags_live ON public.tenant_feature_flags USING btree (tenant_id, flag) WHERE (deleted_at IS NULL);

-- Name: ux_workflow_definitions_active; Type: INDEX; Schema: public
CREATE UNIQUE INDEX ux_workflow_definitions_active ON public.workflow_definitions USING btree (tenant_id, key, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)) WHERE (status = 'active'::text);

-- Name: ux_workflow_instances_client_generated_id; Type: INDEX; Schema: public
CREATE UNIQUE INDEX ux_workflow_instances_client_generated_id ON public.workflow_instances USING btree (tenant_id, client_generated_id);

-- Name: ux_workflow_instances_record; Type: INDEX; Schema: public
CREATE UNIQUE INDEX ux_workflow_instances_record ON public.workflow_instances USING btree (tenant_id, record_type, record_id) WHERE (deleted_at IS NULL);

-- Name: workflow_definition_audit_def_tenant_id_definition_id_creat_idx; Type: INDEX; Schema: public
CREATE INDEX workflow_definition_audit_def_tenant_id_definition_id_creat_idx ON public.workflow_definition_audit_default USING btree (tenant_id, definition_id, created_at);

-- Name: workflow_definition_audit_default_tenant_id_idx; Type: INDEX; Schema: public
CREATE INDEX workflow_definition_audit_default_tenant_id_idx ON public.workflow_definition_audit_default USING btree (tenant_id);

-- Name: evidence_items_default_pkey; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.pk_evidence_items ATTACH PARTITION public.evidence_items_default_pkey;

-- Name: evidence_items_default_tenant_id_control_id_collected_at_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_evidence_items_tenant_id_control_id_collected_at ATTACH PARTITION public.evidence_items_default_tenant_id_control_id_collected_at_idx;

-- Name: evidence_items_default_tenant_id_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_evidence_items_tenant_id ATTACH PARTITION public.evidence_items_default_tenant_id_idx;

-- Name: provenance_entries_default_pkey; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.pk_provenance_entries ATTACH PARTITION public.provenance_entries_default_pkey;

-- Name: provenance_entries_default_tenant_id_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_provenance_entries_tenant_id ATTACH PARTITION public.provenance_entries_default_tenant_id_idx;

-- Name: provenance_entries_default_tenant_id_recorded_at_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_provenance_entries_tenant_id_recorded_at ATTACH PARTITION public.provenance_entries_default_tenant_id_recorded_at_idx;

-- Name: restore_test_records_default_pkey; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.pk_restore_test_records ATTACH PARTITION public.restore_test_records_default_pkey;

-- Name: restore_test_records_default_tenant_id_created_at_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_restore_test_records_tenant_id_created_at ATTACH PARTITION public.restore_test_records_default_tenant_id_created_at_idx;

-- Name: restore_test_records_default_tenant_id_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_restore_test_records_tenant_id ATTACH PARTITION public.restore_test_records_default_tenant_id_idx;

-- Name: workflow_definition_audit_def_tenant_id_definition_id_creat_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_workflow_definition_audit_definition_id ATTACH PARTITION public.workflow_definition_audit_def_tenant_id_definition_id_creat_idx;

-- Name: workflow_definition_audit_default_pkey; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.pk_workflow_definition_audit ATTACH PARTITION public.workflow_definition_audit_default_pkey;

-- Name: workflow_definition_audit_default_tenant_id_idx; Type: INDEX ATTACH; Schema: public
ALTER INDEX public.ix_workflow_definition_audit_tenant_id ATTACH PARTITION public.workflow_definition_audit_default_tenant_id_idx;

-- Name: access_reviews tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.access_reviews USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: access_settings tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.access_settings USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: app_user tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.app_user USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: audit_chain_checkpoints tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.audit_chain_checkpoints USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: audit_chain_heads tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.audit_chain_heads USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: audit_log tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.audit_log USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: auth_event tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.auth_event USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: breach_incidents tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.breach_incidents USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: control_records tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.control_records USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: data_map_entries tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.data_map_entries USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: domain_events dispatcher_select; Type: POLICY; Schema: public
CREATE POLICY dispatcher_select ON public.domain_events FOR SELECT TO aip_jobs USING (true);

-- Name: domain_events dispatcher_update; Type: POLICY; Schema: public
CREATE POLICY dispatcher_update ON public.domain_events FOR UPDATE TO aip_jobs USING (true) WITH CHECK (true);

-- Name: domain_events outbox_owner_update; Type: POLICY; Schema: public
CREATE POLICY outbox_owner_update ON public.domain_events FOR UPDATE TO aip_owner USING (true) WITH CHECK (true);

-- Name: domain_events platform_counts_owner_read; Type: POLICY; Schema: public
CREATE POLICY platform_counts_owner_read ON public.domain_events FOR SELECT TO aip_owner USING (true);

-- Name: domain_events tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.domain_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: evidence_items tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.evidence_items USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: glossary_entry platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.glossary_entry FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: glossary_entry tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.glossary_entry USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: job_events tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.job_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: jobs tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.jobs USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: locale_settings platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.locale_settings FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: locale_settings tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.locale_settings USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: organisations tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.organisations USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: projects tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.projects USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: provenance_entries tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.provenance_entries USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: record_links tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.record_links USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: restore_test_records tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.restore_test_records USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: role tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.role USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: role_assignment tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.role_assignment USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: role_permission tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.role_permission USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: security_audit_events tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.security_audit_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: sites tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.sites USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_auth_policy tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_auth_policy USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_entitlement_override tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_entitlement_override USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_feature_flags tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_feature_flags USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_membership tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_membership USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_subscription tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_subscription USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenant_usage tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenant_usage USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: tenants real_customer_check; Type: POLICY; Schema: public
CREATE POLICY real_customer_check ON public.tenants FOR SELECT TO aip_owner USING (is_real_customer);

-- Name: tenants tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.tenants USING ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: term_alias platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.term_alias FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: term_alias tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.term_alias USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: term_key platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.term_key FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: term_key tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.term_key USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: term_override platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.term_override FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: term_override tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.term_override USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: term_pack platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.term_pack FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: term_pack tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.term_pack USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: term_pack_version platform_read; Type: POLICY; Schema: public
CREATE POLICY platform_read ON public.term_pack_version FOR SELECT USING ((tenant_id = '00000000-0000-0000-0000-000000000000'::uuid));

-- Name: term_pack_version tenant_write; Type: POLICY; Schema: public
CREATE POLICY tenant_write ON public.term_pack_version USING (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name)))) WITH CHECK (((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) AND ((tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid) OR (CURRENT_USER = 'aip_owner'::name))));

-- Name: upload_sessions tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.upload_sessions USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: user_session session_lookup; Type: POLICY; Schema: public
CREATE POLICY session_lookup ON public.user_session FOR SELECT TO aip_owner USING (true);

-- Name: user_session tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.user_session USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: workflow_definition_audit tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.workflow_definition_audit USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: workflow_definitions tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.workflow_definitions USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: workflow_instances tenant_isolation; Type: POLICY; Schema: public
CREATE POLICY tenant_isolation ON public.workflow_instances USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));

-- Name: access_reviews; Type: ROW SECURITY; Schema: public
ALTER TABLE public.access_reviews ENABLE ROW LEVEL SECURITY;

-- Name: access_settings; Type: ROW SECURITY; Schema: public
ALTER TABLE public.access_settings ENABLE ROW LEVEL SECURITY;

-- Name: app_user; Type: ROW SECURITY; Schema: public
ALTER TABLE public.app_user ENABLE ROW LEVEL SECURITY;

-- Name: audit_chain_checkpoints; Type: ROW SECURITY; Schema: public
ALTER TABLE public.audit_chain_checkpoints ENABLE ROW LEVEL SECURITY;

-- Name: audit_chain_heads; Type: ROW SECURITY; Schema: public
ALTER TABLE public.audit_chain_heads ENABLE ROW LEVEL SECURITY;

-- Name: audit_log; Type: ROW SECURITY; Schema: public
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- Name: auth_event; Type: ROW SECURITY; Schema: public
ALTER TABLE public.auth_event ENABLE ROW LEVEL SECURITY;

-- Name: breach_incidents; Type: ROW SECURITY; Schema: public
ALTER TABLE public.breach_incidents ENABLE ROW LEVEL SECURITY;

-- Name: control_records; Type: ROW SECURITY; Schema: public
ALTER TABLE public.control_records ENABLE ROW LEVEL SECURITY;

-- Name: data_map_entries; Type: ROW SECURITY; Schema: public
ALTER TABLE public.data_map_entries ENABLE ROW LEVEL SECURITY;

-- Name: domain_events; Type: ROW SECURITY; Schema: public
ALTER TABLE public.domain_events ENABLE ROW LEVEL SECURITY;

-- Name: evidence_items; Type: ROW SECURITY; Schema: public
ALTER TABLE public.evidence_items ENABLE ROW LEVEL SECURITY;

-- Name: glossary_entry; Type: ROW SECURITY; Schema: public
ALTER TABLE public.glossary_entry ENABLE ROW LEVEL SECURITY;

-- Name: job_events; Type: ROW SECURITY; Schema: public
ALTER TABLE public.job_events ENABLE ROW LEVEL SECURITY;

-- Name: jobs; Type: ROW SECURITY; Schema: public
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Name: locale_settings; Type: ROW SECURITY; Schema: public
ALTER TABLE public.locale_settings ENABLE ROW LEVEL SECURITY;

-- Name: organisations; Type: ROW SECURITY; Schema: public
ALTER TABLE public.organisations ENABLE ROW LEVEL SECURITY;

-- Name: projects; Type: ROW SECURITY; Schema: public
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

-- Name: provenance_entries; Type: ROW SECURITY; Schema: public
ALTER TABLE public.provenance_entries ENABLE ROW LEVEL SECURITY;

-- Name: record_links; Type: ROW SECURITY; Schema: public
ALTER TABLE public.record_links ENABLE ROW LEVEL SECURITY;

-- Name: restore_test_records; Type: ROW SECURITY; Schema: public
ALTER TABLE public.restore_test_records ENABLE ROW LEVEL SECURITY;

-- Name: role; Type: ROW SECURITY; Schema: public
ALTER TABLE public.role ENABLE ROW LEVEL SECURITY;

-- Name: role_assignment; Type: ROW SECURITY; Schema: public
ALTER TABLE public.role_assignment ENABLE ROW LEVEL SECURITY;

-- Name: role_permission; Type: ROW SECURITY; Schema: public
ALTER TABLE public.role_permission ENABLE ROW LEVEL SECURITY;

-- Name: security_audit_events; Type: ROW SECURITY; Schema: public
ALTER TABLE public.security_audit_events ENABLE ROW LEVEL SECURITY;

-- Name: sites; Type: ROW SECURITY; Schema: public
ALTER TABLE public.sites ENABLE ROW LEVEL SECURITY;

-- Name: tenant_auth_policy; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_auth_policy ENABLE ROW LEVEL SECURITY;

-- Name: tenant_entitlement_override; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_entitlement_override ENABLE ROW LEVEL SECURITY;

-- Name: tenant_feature_flags; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_feature_flags ENABLE ROW LEVEL SECURITY;

-- Name: tenant_membership; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_membership ENABLE ROW LEVEL SECURITY;

-- Name: tenant_subscription; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_subscription ENABLE ROW LEVEL SECURITY;

-- Name: tenant_usage; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenant_usage ENABLE ROW LEVEL SECURITY;

-- Name: tenants; Type: ROW SECURITY; Schema: public
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

-- Name: term_alias; Type: ROW SECURITY; Schema: public
ALTER TABLE public.term_alias ENABLE ROW LEVEL SECURITY;

-- Name: term_key; Type: ROW SECURITY; Schema: public
ALTER TABLE public.term_key ENABLE ROW LEVEL SECURITY;

-- Name: term_override; Type: ROW SECURITY; Schema: public
ALTER TABLE public.term_override ENABLE ROW LEVEL SECURITY;

-- Name: term_pack; Type: ROW SECURITY; Schema: public
ALTER TABLE public.term_pack ENABLE ROW LEVEL SECURITY;

-- Name: term_pack_version; Type: ROW SECURITY; Schema: public
ALTER TABLE public.term_pack_version ENABLE ROW LEVEL SECURITY;

-- Name: upload_sessions; Type: ROW SECURITY; Schema: public
ALTER TABLE public.upload_sessions ENABLE ROW LEVEL SECURITY;

-- Name: user_session; Type: ROW SECURITY; Schema: public
ALTER TABLE public.user_session ENABLE ROW LEVEL SECURITY;

-- Name: workflow_definition_audit; Type: ROW SECURITY; Schema: public
ALTER TABLE public.workflow_definition_audit ENABLE ROW LEVEL SECURITY;

-- Name: workflow_definitions; Type: ROW SECURITY; Schema: public
ALTER TABLE public.workflow_definitions ENABLE ROW LEVEL SECURITY;

-- Name: workflow_instances; Type: ROW SECURITY; Schema: public
ALTER TABLE public.workflow_instances ENABLE ROW LEVEL SECURITY;

-- Name: procrastinate_events_id_seq; Type: SEQUENCE; Schema: public
CREATE SEQUENCE public.procrastinate_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.procrastinate_events_id_seq OWNER TO aip_owner;

-- Name: procrastinate_jobs_id_seq; Type: SEQUENCE; Schema: public
CREATE SEQUENCE public.procrastinate_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.procrastinate_jobs_id_seq OWNER TO aip_owner;

-- Name: procrastinate_periodic_defers_id_seq; Type: SEQUENCE; Schema: public
CREATE SEQUENCE public.procrastinate_periodic_defers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.procrastinate_periodic_defers_id_seq OWNER TO aip_owner;

-- Name: procrastinate_workers_id_seq; Type: SEQUENCE; Schema: public
ALTER TABLE public.procrastinate_workers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.procrastinate_workers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

-- Name: procrastinate_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public
ALTER SEQUENCE public.procrastinate_events_id_seq OWNED BY public.procrastinate_events.id;

-- Name: procrastinate_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public
ALTER SEQUENCE public.procrastinate_jobs_id_seq OWNED BY public.procrastinate_jobs.id;

-- Name: procrastinate_periodic_defers_id_seq; Type: SEQUENCE OWNED BY; Schema: public
ALTER SEQUENCE public.procrastinate_periodic_defers_id_seq OWNED BY public.procrastinate_periodic_defers.id;

-- Name: access_reviews; Type: TABLE; Schema: public
CREATE TABLE public.access_reviews (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    quarter text NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    snapshot jsonb NOT NULL,
    decisions jsonb DEFAULT '{}'::jsonb NOT NULL,
    signed_off_by uuid,
    signed_off_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_access_reviews_decisions CHECK ((jsonb_typeof(decisions) = 'object'::text)),
    CONSTRAINT ck_access_reviews_quarter CHECK ((quarter ~ '^[0-9]{4}-Q[1-4]$'::text)),
    CONSTRAINT ck_access_reviews_signed_off CHECK (((status = 'signed_off'::text) = ((signed_off_by IS NOT NULL) AND (signed_off_at IS NOT NULL)))),
    CONSTRAINT ck_access_reviews_snapshot CHECK ((jsonb_typeof(snapshot) = 'object'::text)),
    CONSTRAINT ck_access_reviews_status CHECK ((status = ANY (ARRAY['open'::text, 'in_review'::text, 'signed_off'::text])))
);

ALTER TABLE ONLY public.access_reviews FORCE ROW LEVEL SECURITY;

ALTER TABLE public.access_reviews OWNER TO aip_owner;

-- Name: access_settings; Type: TABLE; Schema: public
CREATE TABLE public.access_settings (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    access_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_access_settings_access_version CHECK ((access_version >= 1))
);

ALTER TABLE ONLY public.access_settings FORCE ROW LEVEL SECURITY;

ALTER TABLE public.access_settings OWNER TO aip_owner;

-- Name: app_user; Type: TABLE; Schema: public
CREATE TABLE public.app_user (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    organisation_id uuid,
    user_class text NOT NULL,
    email public.citext NOT NULL,
    display_name text NOT NULL,
    idp_alias text,
    keycloak_user_id uuid,
    external_id text,
    sso_managed boolean DEFAULT false NOT NULL,
    status text NOT NULL,
    deactivated_at timestamp with time zone,
    last_login_at timestamp with time zone,
    sync_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_app_user_deactivated_at CHECK (((status = 'deactivated'::text) = (deactivated_at IS NOT NULL))),
    CONSTRAINT ck_app_user_display_name CHECK (((btrim(display_name) <> ''::text) AND (length(display_name) <= 200))),
    CONSTRAINT ck_app_user_email CHECK ((email OPERATOR(public.~) '^[^@[:space:]]+@[^@[:space:]]+$'::public.citext)),
    CONSTRAINT ck_app_user_external_id CHECK ((external_id <> ''::text)),
    CONSTRAINT ck_app_user_idp_alias CHECK ((idp_alias <> ''::text)),
    CONSTRAINT ck_app_user_status CHECK ((status = ANY (ARRAY['invited'::text, 'active'::text, 'deactivated'::text]))),
    CONSTRAINT ck_app_user_sync_version CHECK ((sync_version >= 1)),
    CONSTRAINT ck_app_user_user_class CHECK ((user_class = ANY (ARRAY['staff'::text, 'field'::text, 'portal'::text])))
);

ALTER TABLE ONLY public.app_user FORCE ROW LEVEL SECURITY;

ALTER TABLE public.app_user OWNER TO aip_owner;

-- Name: audit_chain_checkpoints; Type: TABLE; Schema: public
CREATE TABLE public.audit_chain_checkpoints (
    tenant_id uuid NOT NULL,
    stream text NOT NULL,
    segment text NOT NULL,
    last_seq bigint NOT NULL,
    last_hash bytea NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_chain_checkpoints_last_hash CHECK ((octet_length(last_hash) = 32)),
    CONSTRAINT ck_audit_chain_checkpoints_last_seq CHECK ((last_seq > 0)),
    CONSTRAINT ck_audit_chain_checkpoints_segment CHECK ((segment ~ '^\d{4}-\d{2}$'::text)),
    CONSTRAINT ck_audit_chain_checkpoints_stream CHECK ((stream = ANY (ARRAY['audit'::text, 'security'::text])))
);

ALTER TABLE ONLY public.audit_chain_checkpoints FORCE ROW LEVEL SECURITY;

ALTER TABLE public.audit_chain_checkpoints OWNER TO aip_owner;

-- Name: audit_chain_heads; Type: TABLE; Schema: public
CREATE TABLE public.audit_chain_heads (
    tenant_id uuid NOT NULL,
    stream text NOT NULL,
    last_seq bigint DEFAULT 0 NOT NULL,
    last_hash bytea NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_chain_heads_last_hash CHECK ((octet_length(last_hash) = 32)),
    CONSTRAINT ck_audit_chain_heads_last_seq CHECK ((last_seq >= 0)),
    CONSTRAINT ck_audit_chain_heads_stream CHECK ((stream = ANY (ARRAY['audit'::text, 'security'::text])))
);

ALTER TABLE ONLY public.audit_chain_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE public.audit_chain_heads OWNER TO aip_owner;

-- Name: audit_log; Type: TABLE; Schema: public
CREATE TABLE public.audit_log (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    stream text NOT NULL,
    seq bigint NOT NULL,
    project_id uuid,
    asset_id uuid,
    asset_path public.ltree,
    actor_id uuid,
    on_behalf_of_id uuid,
    auth_strength text,
    source_module text,
    record_table text,
    record_id uuid,
    event_type text NOT NULL,
    summary_key text,
    payload jsonb,
    reason_for_change text,
    flags text[] DEFAULT '{}'::text[] NOT NULL,
    source_ip inet,
    device text,
    source_event_id uuid,
    supersedes_id uuid,
    prev_hash bytea NOT NULL,
    hash bytea NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_log_event_type CHECK ((event_type <> ''::text)),
    CONSTRAINT ck_audit_log_hash CHECK ((octet_length(hash) = 32)),
    CONSTRAINT ck_audit_log_prev_hash CHECK ((octet_length(prev_hash) = 32)),
    CONSTRAINT ck_audit_log_seq CHECK ((seq > 0)),
    CONSTRAINT ck_audit_log_stream CHECK ((stream = 'audit'::text))
);

ALTER TABLE ONLY public.audit_log FORCE ROW LEVEL SECURITY;

ALTER TABLE public.audit_log OWNER TO aip_owner;

-- Name: auth_event; Type: TABLE; Schema: public
CREATE TABLE public.auth_event (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    event_type text NOT NULL,
    ip inet,
    user_agent text,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_auth_event_detail CHECK ((jsonb_typeof(detail) = 'object'::text)),
    CONSTRAINT ck_auth_event_event_type CHECK ((event_type ~ '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$'::text)),
    CONSTRAINT ck_auth_event_user_agent CHECK ((length(user_agent) <= 512))
);

ALTER TABLE ONLY public.auth_event FORCE ROW LEVEL SECURITY;

ALTER TABLE public.auth_event OWNER TO aip_owner;

-- Name: breach_incidents; Type: TABLE; Schema: public
CREATE TABLE public.breach_incidents (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    description text NOT NULL,
    data_categories jsonb DEFAULT '[]'::jsonb NOT NULL,
    individuals_affected integer,
    serious_harm_likely boolean,
    assessment_due_at timestamp with time zone NOT NULL,
    oaic_notified_at timestamp with time zone,
    individuals_notified_at timestamp with time zone,
    status text DEFAULT 'open'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_breach_incidents_data_categories CHECK ((jsonb_typeof(data_categories) = 'array'::text)),
    CONSTRAINT ck_breach_incidents_description CHECK ((description <> ''::text)),
    CONSTRAINT ck_breach_incidents_individuals_affected CHECK ((individuals_affected >= 0)),
    CONSTRAINT ck_breach_incidents_status CHECK ((status = ANY (ARRAY['open'::text, 'assessing'::text, 'notified'::text, 'closed'::text])))
);

ALTER TABLE ONLY public.breach_incidents FORCE ROW LEVEL SECURITY;

ALTER TABLE public.breach_incidents OWNER TO aip_owner;

-- Name: control_records; Type: TABLE; Schema: public
CREATE TABLE public.control_records (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    control_key text NOT NULL,
    title text NOT NULL,
    framework_mappings jsonb DEFAULT '{}'::jsonb NOT NULL,
    owner_user_id uuid,
    status text DEFAULT 'specified'::text NOT NULL,
    evidence_source text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_control_records_control_key CHECK ((control_key <> ''::text)),
    CONSTRAINT ck_control_records_framework_mappings CHECK ((jsonb_typeof(framework_mappings) = 'object'::text)),
    CONSTRAINT ck_control_records_status CHECK ((status = ANY (ARRAY['specified'::text, 'implemented'::text, 'proven'::text]))),
    CONSTRAINT ck_control_records_title CHECK ((title <> ''::text))
);

ALTER TABLE ONLY public.control_records FORCE ROW LEVEL SECURITY;

ALTER TABLE public.control_records OWNER TO aip_owner;

-- Name: data_map_entries; Type: TABLE; Schema: public
CREATE TABLE public.data_map_entries (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    data_category text NOT NULL,
    classification text NOT NULL,
    system_location text NOT NULL,
    region text NOT NULL,
    purpose text NOT NULL,
    retention_rule text NOT NULL,
    sub_processor text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_data_map_entries_classification CHECK ((classification = ANY (ARRAY['public'::text, 'internal'::text, 'sensitive'::text, 'health'::text]))),
    CONSTRAINT ck_data_map_entries_data_category CHECK ((data_category <> ''::text))
);

ALTER TABLE ONLY public.data_map_entries FORCE ROW LEVEL SECURITY;

ALTER TABLE public.data_map_entries OWNER TO aip_owner;

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

-- Name: domain_events; Type: TABLE; Schema: public
CREATE TABLE public.domain_events (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid,
    asset_id uuid,
    event_name text NOT NULL,
    event_version integer NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb NOT NULL,
    actor_id uuid,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    dead_lettered_at timestamp with time zone,
    last_error text,
    next_attempt_at timestamp with time zone,
    discarded_at timestamp with time zone,
    discarded_by uuid,
    discard_reason text,
    CONSTRAINT ck_domain_events_aggregate_type CHECK ((aggregate_type <> ''::text)),
    CONSTRAINT ck_domain_events_attempts CHECK ((attempts >= 0)),
    CONSTRAINT ck_domain_events_discard_reason CHECK (((char_length(discard_reason) <= 1000) AND ((discarded_at IS NULL) OR (btrim(COALESCE(discard_reason, ''::text)) <> ''::text)))),
    CONSTRAINT ck_domain_events_event_name CHECK ((event_name <> ''::text)),
    CONSTRAINT ck_domain_events_event_version CHECK ((event_version >= 1)),
    CONSTRAINT ck_domain_events_last_error CHECK ((char_length(last_error) <= 4000))
);

ALTER TABLE ONLY public.domain_events FORCE ROW LEVEL SECURITY;

ALTER TABLE public.domain_events OWNER TO aip_owner;

-- Name: evidence_items; Type: TABLE; Schema: public
CREATE TABLE public.evidence_items (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    control_id uuid NOT NULL,
    evidence_type text NOT NULL,
    document_id uuid,
    storage_key text,
    content_hash text,
    collected_at timestamp with time zone NOT NULL,
    period_start date,
    period_end date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_evidence_items_content_hash CHECK ((content_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_evidence_items_evidence_type CHECK ((evidence_type = ANY (ARRAY['ci_artefact'::text, 'screenshot'::text, 'report'::text, 'sign_off'::text]))),
    CONSTRAINT ck_evidence_items_period CHECK ((period_end >= period_start))
)
PARTITION BY RANGE (created_at);

ALTER TABLE ONLY public.evidence_items FORCE ROW LEVEL SECURITY;

ALTER TABLE public.evidence_items OWNER TO aip_owner;

-- Name: evidence_items_default; Type: TABLE; Schema: public
CREATE TABLE public.evidence_items_default (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    control_id uuid NOT NULL,
    evidence_type text NOT NULL,
    document_id uuid,
    storage_key text,
    content_hash text,
    collected_at timestamp with time zone NOT NULL,
    period_start date,
    period_end date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_evidence_items_content_hash CHECK ((content_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_evidence_items_evidence_type CHECK ((evidence_type = ANY (ARRAY['ci_artefact'::text, 'screenshot'::text, 'report'::text, 'sign_off'::text]))),
    CONSTRAINT ck_evidence_items_period CHECK ((period_end >= period_start))
);

ALTER TABLE public.evidence_items_default OWNER TO aip_owner;

-- Name: glossary_entry; Type: TABLE; Schema: public
CREATE TABLE public.glossary_entry (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    term text NOT NULL,
    abbreviation text,
    definition text NOT NULL,
    neutral_concept_code text,
    locale text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_glossary_entry_term CHECK ((term <> ''::text))
);

ALTER TABLE ONLY public.glossary_entry FORCE ROW LEVEL SECURITY;

ALTER TABLE public.glossary_entry OWNER TO aip_owner;

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

-- Name: locale_settings; Type: TABLE; Schema: public
CREATE TABLE public.locale_settings (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid,
    locale text DEFAULT 'en-AU'::text NOT NULL,
    date_format text,
    number_format text,
    unit_system text DEFAULT 'metric'::text NOT NULL,
    unit_overrides jsonb DEFAULT '{}'::jsonb NOT NULL,
    timezone text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_locale_settings_unit_overrides CHECK ((jsonb_typeof(unit_overrides) = 'object'::text)),
    CONSTRAINT ck_locale_settings_unit_system CHECK ((unit_system = ANY (ARRAY['metric'::text, 'imperial'::text])))
);

ALTER TABLE ONLY public.locale_settings FORCE ROW LEVEL SECURITY;

ALTER TABLE public.locale_settings OWNER TO aip_owner;

-- Name: login_directory; Type: TABLE; Schema: public
CREATE TABLE public.login_directory (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind text NOT NULL,
    key public.citext NOT NULL,
    tenant_id uuid NOT NULL,
    idp_alias text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_login_directory_email_no_idp CHECK (((kind <> 'email'::text) OR (idp_alias IS NULL))),
    CONSTRAINT ck_login_directory_kind CHECK ((kind = ANY (ARRAY['email_domain'::text, 'tenant_slug'::text, 'email'::text])))
);

ALTER TABLE public.login_directory OWNER TO aip_owner;

-- Name: organisations; Type: TABLE; Schema: public
CREATE TABLE public.organisations (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    org_type text NOT NULL,
    registration_number text,
    status text DEFAULT 'active'::text NOT NULL,
    sync_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_organisations_name CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT ck_organisations_org_type CHECK ((org_type = ANY (ARRAY['owner'::text, 'client'::text, 'subcontractor'::text]))),
    CONSTRAINT ck_organisations_status CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text]))),
    CONSTRAINT ck_organisations_sync_version CHECK ((sync_version >= 1))
);

ALTER TABLE ONLY public.organisations FORCE ROW LEVEL SECURITY;

ALTER TABLE public.organisations OWNER TO aip_owner;

-- Name: partition_settings; Type: TABLE; Schema: public
CREATE TABLE public.partition_settings (
    table_name text NOT NULL,
    partition_interval text DEFAULT 'month'::text NOT NULL,
    months_ahead integer DEFAULT 3 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_partition_settings_interval CHECK ((partition_interval = 'month'::text)),
    CONSTRAINT ck_partition_settings_months_ahead CHECK (((months_ahead >= 0) AND (months_ahead <= 24)))
);

ALTER TABLE public.partition_settings OWNER TO aip_owner;

-- Name: permission; Type: TABLE; Schema: public
CREATE TABLE public.permission (
    code text NOT NULL,
    module_id text NOT NULL,
    description text NOT NULL,
    is_privileged boolean DEFAULT false NOT NULL,
    deprecated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_permission_code CHECK ((code ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$'::text)),
    CONSTRAINT ck_permission_description CHECK (((btrim(description) <> ''::text) AND (length(description) <= 500))),
    CONSTRAINT ck_permission_module_id CHECK ((module_id ~ '^[a-z][a-z0-9_]*$'::text))
);

ALTER TABLE public.permission OWNER TO aip_owner;

-- Name: platform_event_status; Type: TABLE; Schema: public
CREATE TABLE public.platform_event_status (
    event_name text NOT NULL,
    event_version integer NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    deprecated_at timestamp with time zone,
    deprecated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_platform_event_status_deprecated CHECK (((status = 'deprecated'::text) = (deprecated_at IS NOT NULL))),
    CONSTRAINT ck_platform_event_status_event_name CHECK ((event_name <> ''::text)),
    CONSTRAINT ck_platform_event_status_event_version CHECK ((event_version >= 1)),
    CONSTRAINT ck_platform_event_status_status CHECK ((status = ANY (ARRAY['active'::text, 'deprecated'::text])))
);

ALTER TABLE public.platform_event_status OWNER TO aip_owner;

-- Name: procrastinate_events; Type: TABLE; Schema: public
CREATE TABLE public.procrastinate_events (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    type public.procrastinate_job_event_type,
    at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.procrastinate_events OWNER TO aip_owner;

-- Name: procrastinate_jobs; Type: TABLE; Schema: public
CREATE TABLE public.procrastinate_jobs (
    id bigint NOT NULL,
    queue_name character varying(128) NOT NULL,
    task_name character varying(128) NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    lock text,
    queueing_lock text,
    args jsonb DEFAULT '{}'::jsonb NOT NULL,
    status public.procrastinate_job_status DEFAULT 'todo'::public.procrastinate_job_status NOT NULL,
    scheduled_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    abort_requested boolean DEFAULT false NOT NULL,
    worker_id bigint,
    CONSTRAINT check_not_todo_abort_requested CHECK ((NOT ((status = 'todo'::public.procrastinate_job_status) AND (abort_requested = true))))
);

ALTER TABLE public.procrastinate_jobs OWNER TO aip_owner;

-- Name: procrastinate_periodic_defers; Type: TABLE; Schema: public
CREATE TABLE public.procrastinate_periodic_defers (
    id bigint NOT NULL,
    task_name character varying(128) NOT NULL,
    defer_timestamp bigint,
    job_id bigint,
    periodic_id character varying(128) DEFAULT ''::character varying NOT NULL
);

ALTER TABLE public.procrastinate_periodic_defers OWNER TO aip_owner;

-- Name: procrastinate_workers; Type: TABLE; Schema: public
CREATE TABLE public.procrastinate_workers (
    id bigint NOT NULL,
    last_heartbeat timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.procrastinate_workers OWNER TO aip_owner;

-- Name: projects; Type: TABLE; Schema: public
CREATE TABLE public.projects (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    client_company_id uuid,
    site_id uuid,
    classification_id uuid,
    template_id uuid,
    region text,
    timezone text,
    currency character(3),
    status text DEFAULT 'draft'::text NOT NULL,
    closed_at timestamp with time zone,
    sync_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_projects_code CHECK ((code <> ''::text)),
    CONSTRAINT ck_projects_name CHECK ((name <> ''::text)),
    CONSTRAINT ck_projects_status CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text, 'closing'::text, 'archived'::text]))),
    CONSTRAINT ck_projects_sync_version CHECK ((sync_version >= 1))
);

ALTER TABLE ONLY public.projects FORCE ROW LEVEL SECURITY;

ALTER TABLE public.projects OWNER TO aip_owner;

-- Name: provenance_entries; Type: TABLE; Schema: public
CREATE TABLE public.provenance_entries (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    feature text NOT NULL,
    reference_source text NOT NULL,
    own_spec_path text NOT NULL,
    author text NOT NULL,
    legal_review_ref text,
    recorded_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_provenance_entries_author CHECK ((author <> ''::text)),
    CONSTRAINT ck_provenance_entries_feature CHECK ((feature <> ''::text))
)
PARTITION BY RANGE (created_at);

ALTER TABLE ONLY public.provenance_entries FORCE ROW LEVEL SECURITY;

ALTER TABLE public.provenance_entries OWNER TO aip_owner;

-- Name: provenance_entries_default; Type: TABLE; Schema: public
CREATE TABLE public.provenance_entries_default (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    feature text NOT NULL,
    reference_source text NOT NULL,
    own_spec_path text NOT NULL,
    author text NOT NULL,
    legal_review_ref text,
    recorded_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_provenance_entries_author CHECK ((author <> ''::text)),
    CONSTRAINT ck_provenance_entries_feature CHECK ((feature <> ''::text))
);

ALTER TABLE public.provenance_entries_default OWNER TO aip_owner;

-- Name: record_links; Type: TABLE; Schema: public
CREATE TABLE public.record_links (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    from_type text NOT NULL,
    from_id uuid NOT NULL,
    to_type text NOT NULL,
    to_id uuid NOT NULL,
    asset_id uuid,
    link_kind text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_record_links_from_type CHECK ((from_type ~ '^[a-z][a-z0-9_]{0,62}$'::text)),
    CONSTRAINT ck_record_links_link_kind CHECK ((link_kind ~ '^[a-z][a-z0-9_]{0,62}$'::text)),
    CONSTRAINT ck_record_links_not_self CHECK (((from_type <> to_type) OR (from_id <> to_id))),
    CONSTRAINT ck_record_links_to_type CHECK ((to_type ~ '^[a-z][a-z0-9_]{0,62}$'::text))
);

ALTER TABLE ONLY public.record_links FORCE ROW LEVEL SECURITY;

ALTER TABLE public.record_links OWNER TO aip_owner;

-- Name: restore_test_records; Type: TABLE; Schema: public
CREATE TABLE public.restore_test_records (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    environment text NOT NULL,
    backup_taken_at timestamp with time zone NOT NULL,
    restore_started_at timestamp with time zone NOT NULL,
    restore_completed_at timestamp with time zone,
    rpo_achieved_seconds integer,
    rto_achieved_seconds integer,
    result text NOT NULL,
    evidence_item_id uuid,
    performed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_restore_test_records_completed CHECK ((restore_completed_at >= restore_started_at)),
    CONSTRAINT ck_restore_test_records_environment CHECK ((environment <> ''::text)),
    CONSTRAINT ck_restore_test_records_result CHECK ((result = ANY (ARRAY['pass'::text, 'fail'::text]))),
    CONSTRAINT ck_restore_test_records_rpo CHECK ((rpo_achieved_seconds >= 0)),
    CONSTRAINT ck_restore_test_records_rto CHECK ((rto_achieved_seconds >= 0))
)
PARTITION BY RANGE (created_at);

ALTER TABLE ONLY public.restore_test_records FORCE ROW LEVEL SECURITY;

ALTER TABLE public.restore_test_records OWNER TO aip_owner;

-- Name: restore_test_records_default; Type: TABLE; Schema: public
CREATE TABLE public.restore_test_records_default (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    environment text NOT NULL,
    backup_taken_at timestamp with time zone NOT NULL,
    restore_started_at timestamp with time zone NOT NULL,
    restore_completed_at timestamp with time zone,
    rpo_achieved_seconds integer,
    rto_achieved_seconds integer,
    result text NOT NULL,
    evidence_item_id uuid,
    performed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_restore_test_records_completed CHECK ((restore_completed_at >= restore_started_at)),
    CONSTRAINT ck_restore_test_records_environment CHECK ((environment <> ''::text)),
    CONSTRAINT ck_restore_test_records_result CHECK ((result = ANY (ARRAY['pass'::text, 'fail'::text]))),
    CONSTRAINT ck_restore_test_records_rpo CHECK ((rpo_achieved_seconds >= 0)),
    CONSTRAINT ck_restore_test_records_rto CHECK ((rto_achieved_seconds >= 0))
);

ALTER TABLE public.restore_test_records_default OWNER TO aip_owner;

-- Name: role; Type: TABLE; Schema: public
CREATE TABLE public.role (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    code text NOT NULL,
    name_term_key text,
    name text,
    is_system boolean DEFAULT false NOT NULL,
    customised_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_role_code CHECK ((code ~ '^[a-z][a-z0-9_]{1,62}$'::text)),
    CONSTRAINT ck_role_customised_system CHECK (((customised_at IS NULL) OR is_system)),
    CONSTRAINT ck_role_named CHECK (((name_term_key IS NOT NULL) OR (name <> ''::text)))
);

ALTER TABLE ONLY public.role FORCE ROW LEVEL SECURITY;

ALTER TABLE public.role OWNER TO aip_owner;

-- Name: role_assignment; Type: TABLE; Schema: public
CREATE TABLE public.role_assignment (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    scope_type text NOT NULL,
    project_id uuid,
    team_id uuid,
    asset_path public.ltree,
    source text DEFAULT 'manual'::text NOT NULL,
    valid_from timestamp with time zone DEFAULT now() NOT NULL,
    valid_to timestamp with time zone,
    approved_by uuid,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_role_assignment_scope CHECK ((((scope_type = 'tenant'::text) AND (project_id IS NULL) AND (team_id IS NULL) AND (asset_path IS NULL)) OR ((scope_type = 'project'::text) AND (project_id IS NOT NULL) AND (team_id IS NULL) AND (asset_path IS NULL)) OR ((scope_type = 'team'::text) AND (team_id IS NOT NULL) AND (asset_path IS NULL)) OR ((scope_type = 'asset_subtree'::text) AND (asset_path IS NOT NULL) AND (team_id IS NULL)))),
    CONSTRAINT ck_role_assignment_scope_type CHECK ((scope_type = ANY (ARRAY['tenant'::text, 'project'::text, 'team'::text, 'asset_subtree'::text]))),
    CONSTRAINT ck_role_assignment_source CHECK ((source = ANY (ARRAY['manual'::text, 'scim'::text, 'delegation'::text]))),
    CONSTRAINT ck_role_assignment_valid CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))
);

ALTER TABLE ONLY public.role_assignment FORCE ROW LEVEL SECURITY;

ALTER TABLE public.role_assignment OWNER TO aip_owner;

-- Name: role_permission; Type: TABLE; Schema: public
CREATE TABLE public.role_permission (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    role_id uuid NOT NULL,
    permission_code text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_role_permission_not_operator_only CHECK ((permission_code !~~ 'platform.%'::text))
);

ALTER TABLE ONLY public.role_permission FORCE ROW LEVEL SECURITY;

ALTER TABLE public.role_permission OWNER TO aip_owner;

-- Name: security_audit_events; Type: TABLE; Schema: public
CREATE TABLE public.security_audit_events (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    seq bigint NOT NULL,
    actor_id uuid,
    event_type text NOT NULL,
    target_ref text,
    auth_strength text,
    source_ip inet,
    device text,
    detail jsonb,
    source_event_id uuid,
    prev_hash bytea NOT NULL,
    hash bytea NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_audit_events_event_type CHECK ((event_type <> ''::text)),
    CONSTRAINT ck_security_audit_events_hash CHECK ((octet_length(hash) = 32)),
    CONSTRAINT ck_security_audit_events_prev_hash CHECK ((octet_length(prev_hash) = 32)),
    CONSTRAINT ck_security_audit_events_seq CHECK ((seq > 0))
);

ALTER TABLE ONLY public.security_audit_events FORCE ROW LEVEL SECURITY;

ALTER TABLE public.security_audit_events OWNER TO aip_owner;

-- Name: sites; Type: TABLE; Schema: public
CREATE TABLE public.sites (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    lat numeric(9,6),
    lng numeric(9,6),
    timezone text,
    is_system boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_sites_code CHECK ((code <> ''::text)),
    CONSTRAINT ck_sites_lat CHECK (((lat >= ('-90'::integer)::numeric) AND (lat <= (90)::numeric))),
    CONSTRAINT ck_sites_lng CHECK (((lng >= ('-180'::integer)::numeric) AND (lng <= (180)::numeric))),
    CONSTRAINT ck_sites_name CHECK ((name <> ''::text))
);

ALTER TABLE ONLY public.sites FORCE ROW LEVEL SECURITY;

ALTER TABLE public.sites OWNER TO aip_owner;

-- Name: tenant_auth_policy; Type: TABLE; Schema: public
CREATE TABLE public.tenant_auth_policy (
    tenant_id uuid NOT NULL,
    session_policy jsonb DEFAULT '{"field": {"idleMin": 5, "absoluteH": 12}, "staff": {"idleMin": 30, "absoluteH": 12}, "portal": {"idleMin": 15, "absoluteH": 8}}'::jsonb NOT NULL,
    sso_enforced boolean DEFAULT false NOT NULL,
    step_up_max_age_min integer DEFAULT 10 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_auth_policy_session_policy CHECK ((jsonb_typeof(session_policy) = 'object'::text)),
    CONSTRAINT ck_tenant_auth_policy_step_up_max_age_min CHECK (((step_up_max_age_min >= 1) AND (step_up_max_age_min <= 1440)))
);

ALTER TABLE ONLY public.tenant_auth_policy FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_auth_policy OWNER TO aip_owner;

-- Name: tenant_entitlement_override; Type: TABLE; Schema: public
CREATE TABLE public.tenant_entitlement_override (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    key text NOT NULL,
    value jsonb,
    reason text NOT NULL,
    expires_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_entitlement_override_key CHECK ((key ~ '^(feature|limit)\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'::text)),
    CONSTRAINT ck_tenant_entitlement_override_reason CHECK ((btrim(reason) <> ''::text))
);

ALTER TABLE ONLY public.tenant_entitlement_override FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_entitlement_override OWNER TO aip_owner;

-- Name: tenant_feature_flags; Type: TABLE; Schema: public
CREATE TABLE public.tenant_feature_flags (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    flag text NOT NULL,
    enabled boolean NOT NULL,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_feature_flags_flag CHECK ((flag ~ '^[a-z][a-z0-9_]{0,62}$'::text))
);

ALTER TABLE ONLY public.tenant_feature_flags FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_feature_flags OWNER TO aip_owner;

-- Name: tenant_membership; Type: TABLE; Schema: public
CREATE TABLE public.tenant_membership (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    organisation_id uuid,
    membership_type text NOT NULL,
    valid_from date DEFAULT CURRENT_DATE NOT NULL,
    valid_to date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_membership_membership_type CHECK ((membership_type = ANY (ARRAY['member'::text, 'client'::text, 'subcontractor'::text, 'guest'::text]))),
    CONSTRAINT ck_tenant_membership_valid_to CHECK (((valid_to IS NULL) OR (valid_to >= valid_from)))
);

ALTER TABLE ONLY public.tenant_membership FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_membership OWNER TO aip_owner;

-- Name: tenant_subscription; Type: TABLE; Schema: public
CREATE TABLE public.tenant_subscription (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    plan_code text NOT NULL,
    plan_version integer NOT NULL,
    term text NOT NULL,
    starts_on date NOT NULL,
    ends_on date,
    renewal_date date,
    seat_limits jsonb DEFAULT '{}'::jsonb NOT NULL,
    storage_gb integer,
    add_ons text[] DEFAULT '{}'::text[] NOT NULL,
    contract_ref text,
    status text NOT NULL,
    entitlement_version bigint DEFAULT 1 NOT NULL,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_subscription_contract_ref CHECK (((term <> ALL (ARRAY['annual'::text, 'multi_year'::text])) OR (COALESCE(btrim(contract_ref), ''::text) <> ''::text))),
    CONSTRAINT ck_tenant_subscription_dates CHECK (((ends_on IS NULL) OR (ends_on >= starts_on))),
    CONSTRAINT ck_tenant_subscription_entitlement_version CHECK ((entitlement_version >= 1)),
    CONSTRAINT ck_tenant_subscription_plan_code CHECK ((plan_code <> ''::text)),
    CONSTRAINT ck_tenant_subscription_plan_version CHECK ((plan_version >= 1)),
    CONSTRAINT ck_tenant_subscription_seat_limits CHECK ((jsonb_typeof(seat_limits) = 'object'::text)),
    CONSTRAINT ck_tenant_subscription_status CHECK ((status = ANY (ARRAY['active'::text, 'expired'::text, 'suspended'::text]))),
    CONSTRAINT ck_tenant_subscription_storage_gb CHECK ((storage_gb >= 0)),
    CONSTRAINT ck_tenant_subscription_term CHECK ((term = ANY (ARRAY['annual'::text, 'multi_year'::text, 'trial'::text, 'sandbox'::text])))
);

ALTER TABLE ONLY public.tenant_subscription FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_subscription OWNER TO aip_owner;

-- Name: tenant_usage; Type: TABLE; Schema: public
CREATE TABLE public.tenant_usage (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    period date NOT NULL,
    active_users jsonb DEFAULT '{}'::jsonb NOT NULL,
    storage_bytes bigint DEFAULT 0 NOT NULL,
    jobs_count bigint DEFAULT 0 NOT NULL,
    ai_spend_cents bigint DEFAULT 0 NOT NULL,
    db_bytes_est bigint,
    db_estimate_method text,
    db_estimated_at timestamp with time zone,
    over_limit jsonb DEFAULT '{}'::jsonb NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_tenant_usage_active_users CHECK ((jsonb_typeof(active_users) = 'object'::text)),
    CONSTRAINT ck_tenant_usage_counts CHECK (((storage_bytes >= 0) AND (jobs_count >= 0) AND (ai_spend_cents >= 0) AND ((db_bytes_est IS NULL) OR (db_bytes_est >= 0)))),
    CONSTRAINT ck_tenant_usage_over_limit CHECK ((jsonb_typeof(over_limit) = 'object'::text)),
    CONSTRAINT ck_tenant_usage_period CHECK ((EXTRACT(day FROM period) = (1)::numeric))
);

ALTER TABLE ONLY public.tenant_usage FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenant_usage OWNER TO aip_owner;

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
    is_real_customer boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_tenants_deployment_shape CHECK ((deployment_shape = ANY (ARRAY['pooled'::text, 'siloed'::text]))),
    CONSTRAINT ck_tenants_id CHECK ((id <> '00000000-0000-0000-0000-000000000000'::uuid)),
    CONSTRAINT ck_tenants_kms_key_ref CHECK ((kms_key_ref <> ''::text)),
    CONSTRAINT ck_tenants_name CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT ck_tenants_slug CHECK ((slug ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'::text)),
    CONSTRAINT ck_tenants_status CHECK ((status = ANY (ARRAY['provisioning'::text, 'active'::text, 'suspended'::text, 'offboarding'::text, 'offboarded'::text])))
);

ALTER TABLE ONLY public.tenants FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tenants OWNER TO aip_owner;

-- Name: term_alias; Type: TABLE; Schema: public
CREATE TABLE public.term_alias (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    alias text NOT NULL,
    target_type text NOT NULL,
    target_code text NOT NULL,
    locale text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_term_alias_alias CHECK (((alias <> ''::text) AND (alias = lower(alias)))),
    CONSTRAINT ck_term_alias_target_type CHECK ((target_type = ANY (ARRAY['entity_type'::text, 'field'::text, 'status'::text])))
);

ALTER TABLE ONLY public.term_alias FORCE ROW LEVEL SECURITY;

ALTER TABLE public.term_alias OWNER TO aip_owner;

-- Name: term_key; Type: TABLE; Schema: public
CREATE TABLE public.term_key (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    key text NOT NULL,
    module_id text NOT NULL,
    default_locale text DEFAULT 'en-AU'::text NOT NULL,
    default_text text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_term_key_default_text CHECK ((default_text <> ''::text)),
    CONSTRAINT ck_term_key_key CHECK ((key ~ '^[a-z][a-z0-9_]*(\.[A-Za-z0-9_-]+)+$'::text)),
    CONSTRAINT ck_term_key_module_id CHECK ((module_id ~ '^[a-z][a-z0-9_]*$'::text))
);

ALTER TABLE ONLY public.term_key FORCE ROW LEVEL SECURITY;

ALTER TABLE public.term_key OWNER TO aip_owner;

-- Name: term_override; Type: TABLE; Schema: public
CREATE TABLE public.term_override (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    level text NOT NULL,
    client_org_id uuid,
    project_id uuid,
    key text NOT NULL,
    locale text NOT NULL,
    text text NOT NULL,
    sync_version integer DEFAULT 1 NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_term_override_level CHECK ((((level = 'tenant'::text) AND (client_org_id IS NULL) AND (project_id IS NULL)) OR ((level = 'client'::text) AND (client_org_id IS NOT NULL) AND (project_id IS NULL)) OR ((level = 'project'::text) AND (project_id IS NOT NULL) AND (client_org_id IS NULL)))),
    CONSTRAINT ck_term_override_sync_version CHECK ((sync_version >= 1)),
    CONSTRAINT ck_term_override_text CHECK ((text <> ''::text))
);

ALTER TABLE ONLY public.term_override FORCE ROW LEVEL SECURITY;

ALTER TABLE public.term_override OWNER TO aip_owner;

-- Name: term_pack; Type: TABLE; Schema: public
CREATE TABLE public.term_pack (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    active_version_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_term_pack_code CHECK ((code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text)),
    CONSTRAINT ck_term_pack_name CHECK ((name <> ''::text))
);

ALTER TABLE ONLY public.term_pack FORCE ROW LEVEL SECURITY;

ALTER TABLE public.term_pack OWNER TO aip_owner;

-- Name: term_pack_version; Type: TABLE; Schema: public
CREATE TABLE public.term_pack_version (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    pack_id uuid NOT NULL,
    version integer NOT NULL,
    contents jsonb NOT NULL,
    contents_sha256 text NOT NULL,
    change_summary jsonb,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_term_pack_version_contents CHECK ((jsonb_typeof(contents) = 'object'::text)),
    CONSTRAINT ck_term_pack_version_sha256 CHECK ((contents_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_term_pack_version_version CHECK ((version >= 1))
);

ALTER TABLE ONLY public.term_pack_version FORCE ROW LEVEL SECURITY;

ALTER TABLE public.term_pack_version OWNER TO aip_owner;

-- Name: upload_sessions; Type: TABLE; Schema: public
CREATE TABLE public.upload_sessions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    declared_filename text NOT NULL,
    declared_mime text NOT NULL,
    declared_size_bytes numeric NOT NULL,
    mode text NOT NULL,
    s3_upload_id text,
    quarantine_key text NOT NULL,
    chunk_size integer,
    parts_received jsonb,
    client_file_hash text,
    status text NOT NULL,
    reject_reason text,
    priority integer DEFAULT 0 NOT NULL,
    client_request_id uuid,
    expires_at timestamp with time zone NOT NULL,
    file_id uuid,
    sync_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_upload_sessions_declared_size CHECK ((declared_size_bytes > (0)::numeric)),
    CONSTRAINT ck_upload_sessions_mode CHECK ((mode = ANY (ARRAY['single'::text, 'multipart'::text]))),
    CONSTRAINT ck_upload_sessions_priority CHECK ((priority >= 0)),
    CONSTRAINT ck_upload_sessions_status CHECK ((status = ANY (ARRAY['requested'::text, 'uploading'::text, 'uploaded'::text, 'scanning'::text, 'validating'::text, 'released'::text, 'rejected'::text, 'expired'::text, 'aborted'::text]))),
    CONSTRAINT ck_upload_sessions_sync_version CHECK ((sync_version >= 1))
);

ALTER TABLE ONLY public.upload_sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.upload_sessions OWNER TO aip_owner;

-- Name: user_session; Type: TABLE; Schema: public
CREATE TABLE public.user_session (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    sid_hash bytea NOT NULL,
    audience text NOT NULL,
    device_id uuid,
    aal smallint NOT NULL,
    amr text[] NOT NULL,
    authenticated_at timestamp with time zone NOT NULL,
    kc_sid text,
    ip inet,
    user_agent text,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    idle_seconds integer NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    revoke_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_user_session_aal CHECK ((aal = ANY (ARRAY[1, 2]))),
    CONSTRAINT ck_user_session_audience CHECK ((audience = ANY (ARRAY['app'::text, 'portal'::text, 'device'::text]))),
    CONSTRAINT ck_user_session_expiry CHECK ((idle_expires_at <= absolute_expires_at)),
    CONSTRAINT ck_user_session_idle_seconds CHECK ((idle_seconds > 0)),
    CONSTRAINT ck_user_session_revoked CHECK (((revoked_at IS NULL) = (revoke_reason IS NULL))),
    CONSTRAINT ck_user_session_sid_hash CHECK ((octet_length(sid_hash) = 32)),
    CONSTRAINT ck_user_session_user_agent CHECK ((char_length(user_agent) <= 512))
);

ALTER TABLE ONLY public.user_session FORCE ROW LEVEL SECURITY;

ALTER TABLE public.user_session OWNER TO aip_owner;

-- Name: workflow_definition_audit; Type: TABLE; Schema: public
CREATE TABLE public.workflow_definition_audit (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    definition_id uuid NOT NULL,
    actor_id uuid,
    change jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_workflow_definition_audit_change CHECK ((jsonb_typeof(change) = 'object'::text))
)
PARTITION BY RANGE (created_at);

ALTER TABLE ONLY public.workflow_definition_audit FORCE ROW LEVEL SECURITY;

ALTER TABLE public.workflow_definition_audit OWNER TO aip_owner;

-- Name: workflow_definition_audit_default; Type: TABLE; Schema: public
CREATE TABLE public.workflow_definition_audit_default (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    definition_id uuid NOT NULL,
    actor_id uuid,
    change jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_workflow_definition_audit_change CHECK ((jsonb_typeof(change) = 'object'::text))
);

ALTER TABLE public.workflow_definition_audit_default OWNER TO aip_owner;

-- Name: workflow_definitions; Type: TABLE; Schema: public
CREATE TABLE public.workflow_definitions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    record_type text NOT NULL,
    project_id uuid,
    key text NOT NULL,
    version integer NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    states jsonb NOT NULL,
    transitions jsonb NOT NULL,
    initial_state text NOT NULL,
    is_preset boolean DEFAULT false NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_workflow_definitions_key CHECK ((key ~ '^[a-z][a-z0-9_]{0,62}$'::text)),
    CONSTRAINT ck_workflow_definitions_record_type CHECK ((record_type ~ '^[a-z][a-z0-9_]{0,62}$'::text)),
    CONSTRAINT ck_workflow_definitions_states CHECK ((jsonb_typeof(states) = 'array'::text)),
    CONSTRAINT ck_workflow_definitions_status CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text, 'retired'::text]))),
    CONSTRAINT ck_workflow_definitions_transitions CHECK ((jsonb_typeof(transitions) = 'array'::text)),
    CONSTRAINT ck_workflow_definitions_version CHECK ((version >= 1))
);

ALTER TABLE ONLY public.workflow_definitions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.workflow_definitions OWNER TO aip_owner;

-- Name: workflow_instances; Type: TABLE; Schema: public
CREATE TABLE public.workflow_instances (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid,
    definition_id uuid NOT NULL,
    record_type text NOT NULL,
    record_id uuid NOT NULL,
    asset_id uuid,
    current_state text NOT NULL,
    record_value numeric(18,2),
    currency character(3),
    visibility_scope text,
    created_by uuid,
    client_generated_id uuid,
    sync_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_workflow_instances_current_state CHECK ((current_state ~ '^[a-z][a-z0-9_]{0,62}$'::text)),
    CONSTRAINT ck_workflow_instances_record_type CHECK ((record_type ~ '^[a-z][a-z0-9_]{0,62}$'::text))
);

ALTER TABLE ONLY public.workflow_instances FORCE ROW LEVEL SECURITY;

ALTER TABLE public.workflow_instances OWNER TO aip_owner;

-- Name: evidence_items_default; Type: TABLE ATTACH; Schema: public
ALTER TABLE ONLY public.evidence_items ATTACH PARTITION public.evidence_items_default DEFAULT;

-- Name: provenance_entries_default; Type: TABLE ATTACH; Schema: public
ALTER TABLE ONLY public.provenance_entries ATTACH PARTITION public.provenance_entries_default DEFAULT;

-- Name: restore_test_records_default; Type: TABLE ATTACH; Schema: public
ALTER TABLE ONLY public.restore_test_records ATTACH PARTITION public.restore_test_records_default DEFAULT;

-- Name: workflow_definition_audit_default; Type: TABLE ATTACH; Schema: public
ALTER TABLE ONLY public.workflow_definition_audit ATTACH PARTITION public.workflow_definition_audit_default DEFAULT;

-- Name: access_settings trg_access_settings_version_guard; Type: TRIGGER; Schema: public
CREATE TRIGGER trg_access_settings_version_guard BEFORE UPDATE ON public.access_settings FOR EACH ROW EXECUTE FUNCTION public.access_settings_version_guard();

-- Name: audit_log audit_log_append_only; Type: TRIGGER; Schema: public
CREATE TRIGGER audit_log_append_only BEFORE DELETE OR UPDATE ON public.audit_log FOR EACH ROW EXECUTE FUNCTION public.audit_log_forbid_mutation();

-- Name: domain_events domain_events_write_once; Type: TRIGGER; Schema: public
CREATE TRIGGER domain_events_write_once BEFORE UPDATE ON public.domain_events FOR EACH ROW EXECUTE FUNCTION public.domain_events_write_once();

-- Name: procrastinate_jobs procrastinate_jobs_notify_queue_job_aborted_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_jobs_notify_queue_job_aborted_v1 AFTER UPDATE OF abort_requested ON public.procrastinate_jobs FOR EACH ROW WHEN (((old.abort_requested = false) AND (new.abort_requested = true) AND (new.status = 'doing'::public.procrastinate_job_status))) EXECUTE FUNCTION public.procrastinate_notify_queue_abort_job_v1();

-- Name: procrastinate_jobs procrastinate_jobs_notify_queue_job_inserted_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_jobs_notify_queue_job_inserted_v1 AFTER INSERT ON public.procrastinate_jobs FOR EACH ROW WHEN ((new.status = 'todo'::public.procrastinate_job_status)) EXECUTE FUNCTION public.procrastinate_notify_queue_job_inserted_v1();

-- Name: procrastinate_jobs procrastinate_trigger_abort_requested_events_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_trigger_abort_requested_events_v1 AFTER UPDATE OF abort_requested ON public.procrastinate_jobs FOR EACH ROW WHEN ((new.abort_requested = true)) EXECUTE FUNCTION public.procrastinate_trigger_abort_requested_events_procedure_v1();

-- Name: procrastinate_jobs procrastinate_trigger_delete_jobs_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_trigger_delete_jobs_v1 BEFORE DELETE ON public.procrastinate_jobs FOR EACH ROW EXECUTE FUNCTION public.procrastinate_unlink_periodic_defers_v1();

-- Name: procrastinate_jobs procrastinate_trigger_scheduled_events_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_trigger_scheduled_events_v1 AFTER INSERT OR UPDATE ON public.procrastinate_jobs FOR EACH ROW WHEN (((new.scheduled_at IS NOT NULL) AND (new.status = 'todo'::public.procrastinate_job_status))) EXECUTE FUNCTION public.procrastinate_trigger_function_scheduled_events_v1();

-- Name: procrastinate_jobs procrastinate_trigger_status_events_insert_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_trigger_status_events_insert_v1 AFTER INSERT ON public.procrastinate_jobs FOR EACH ROW WHEN ((new.status = 'todo'::public.procrastinate_job_status)) EXECUTE FUNCTION public.procrastinate_trigger_function_status_events_insert_v1();

-- Name: procrastinate_jobs procrastinate_trigger_status_events_update_v1; Type: TRIGGER; Schema: public
CREATE TRIGGER procrastinate_trigger_status_events_update_v1 AFTER UPDATE OF status ON public.procrastinate_jobs FOR EACH ROW EXECUTE FUNCTION public.procrastinate_trigger_function_status_events_update_v1();

-- Name: security_audit_events security_audit_events_append_only; Type: TRIGGER; Schema: public
CREATE TRIGGER security_audit_events_append_only BEFORE DELETE OR UPDATE ON public.security_audit_events FOR EACH ROW EXECUTE FUNCTION public.security_audit_events_forbid_mutation();

-- Name: procrastinate_job_event_type; Type: TYPE; Schema: public
CREATE TYPE public.procrastinate_job_event_type AS ENUM (
    'deferred',
    'started',
    'deferred_for_retry',
    'failed',
    'succeeded',
    'cancelled',
    'abort_requested',
    'aborted',
    'scheduled',
    'retried'
);

ALTER TYPE public.procrastinate_job_event_type OWNER TO aip_owner;

-- Name: procrastinate_job_status; Type: TYPE; Schema: public
CREATE TYPE public.procrastinate_job_status AS ENUM (
    'todo',
    'doing',
    'succeeded',
    'failed',
    'cancelled',
    'aborting',
    'aborted'
);

ALTER TYPE public.procrastinate_job_status OWNER TO aip_owner;

-- Name: procrastinate_job_to_defer_v1; Type: TYPE; Schema: public
CREATE TYPE public.procrastinate_job_to_defer_v1 AS (
	queue_name character varying,
	task_name character varying,
	priority integer,
	lock text,
	queueing_lock text,
	args jsonb,
	scheduled_at timestamp with time zone
);

ALTER TYPE public.procrastinate_job_to_defer_v1 OWNER TO aip_owner;

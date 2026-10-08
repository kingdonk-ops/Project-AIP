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

-- Name: COLUMN procrastinate_jobs.id; Type: ACL; Schema: public
GRANT SELECT(id) ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: FUNCTION identity_resolve_login(p_kind text, p_key public.citext); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) FROM PUBLIC;
GRANT ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) TO aip_app;

-- Name: SEQUENCE procrastinate_events_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_events_id_seq TO aip_jobs;
GRANT USAGE ON SEQUENCE public.procrastinate_events_id_seq TO aip_app;

-- Name: SEQUENCE procrastinate_jobs_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_jobs_id_seq TO aip_jobs;
GRANT USAGE ON SEQUENCE public.procrastinate_jobs_id_seq TO aip_app;

-- Name: SEQUENCE procrastinate_periodic_defers_id_seq; Type: ACL; Schema: public
GRANT SELECT,USAGE ON SEQUENCE public.procrastinate_periodic_defers_id_seq TO aip_jobs;

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

-- Name: TABLE procrastinate_events; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_events TO aip_jobs;
GRANT INSERT ON TABLE public.procrastinate_events TO aip_app;

-- Name: TABLE procrastinate_jobs; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_jobs TO aip_jobs;
GRANT INSERT ON TABLE public.procrastinate_jobs TO aip_app;

-- Name: TABLE procrastinate_periodic_defers; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_periodic_defers TO aip_jobs;

-- Name: TABLE procrastinate_workers; Type: ACL; Schema: public
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.procrastinate_workers TO aip_jobs;

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

-- Name: tenants pk_tenants; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT pk_tenants PRIMARY KEY (id);

-- Name: tenants uq_tenants_slug; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT uq_tenants_slug UNIQUE (slug);

-- Name: procrastinate_events id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_events ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_events_id_seq'::regclass);

-- Name: procrastinate_jobs id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_jobs ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_jobs_id_seq'::regclass);

-- Name: procrastinate_periodic_defers id; Type: DEFAULT; Schema: public
ALTER TABLE ONLY public.procrastinate_periodic_defers ALTER COLUMN id SET DEFAULT nextval('public.procrastinate_periodic_defers_id_seq'::regclass);

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

-- Name: idx_procrastinate_jobs_worker_not_null; Type: INDEX; Schema: public
CREATE INDEX idx_procrastinate_jobs_worker_not_null ON public.procrastinate_jobs USING btree (worker_id) WHERE ((worker_id IS NOT NULL) AND (status = 'doing'::public.procrastinate_job_status));

-- Name: idx_procrastinate_workers_last_heartbeat; Type: INDEX; Schema: public
CREATE INDEX idx_procrastinate_workers_last_heartbeat ON public.procrastinate_workers USING btree (last_heartbeat);

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

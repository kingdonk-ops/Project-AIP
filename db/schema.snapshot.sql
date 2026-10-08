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

-- Name: FUNCTION identity_resolve_login(p_kind text, p_key public.citext); Type: ACL; Schema: public
REVOKE ALL ON FUNCTION public.identity_resolve_login(p_kind text, p_key public.citext) FROM PUBLIC;

-- Name: login_directory login_directory_pkey; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT login_directory_pkey PRIMARY KEY (id);

-- Name: login_directory uq_login_directory_kind_key; Type: CONSTRAINT; Schema: public
ALTER TABLE ONLY public.login_directory
    ADD CONSTRAINT uq_login_directory_kind_key UNIQUE (kind, key);

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

-- Name: ix_login_directory_tenant_id; Type: INDEX; Schema: public
CREATE INDEX ix_login_directory_tenant_id ON public.login_directory USING btree (tenant_id);

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

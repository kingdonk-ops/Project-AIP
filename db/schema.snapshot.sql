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

# Search, retrieval & saved views — Tech stack advisor


- **note**: Postgres FTS plus pgvector is sufficient at this scale and keeps permission filtering inside the SQL query. Avoid OpenSearch until measured need, since it adds tenant-isolation work.

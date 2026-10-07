# Search, retrieval & saved views — Security advisor


- **note**: Apply permission filters at query time, including pgvector embeddings, because vectors can leak restricted content. Scope indexes per tenant, and delete embeddings on record deletion, offboarding or crypto-shredding. Do not index masked health fields.

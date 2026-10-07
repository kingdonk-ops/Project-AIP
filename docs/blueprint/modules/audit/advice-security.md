# Audit trail, activity & timeline — Security advisor


- **note**: Hash chaining only helps if the app cannot rewrite the chain, so use separate DB roles and external anchoring. Give audit read access its own permission apart from tenant admin. Log reads of sensitive records and exports, and ensure purge jobs honour legal hold.

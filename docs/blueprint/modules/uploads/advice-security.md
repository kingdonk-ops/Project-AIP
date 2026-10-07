# Upload & file processing pipeline — Security advisor


- **note**: Highest-exposure surface because of CAD, IFC and PDF parsing. Sandbox converters with no network, non-root, resource limits and short-lived credentials, and fail closed on scan errors. Re-validate type server-side after chunked reassembly, and keep scanner signatures current.

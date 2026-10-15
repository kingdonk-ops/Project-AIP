"""Upload & file processing pipeline (``uploads``).

UPLOADS-01 is the only safe way a file enters the platform: a user-bound upload session whose
server-issued presigned POST drops the bytes straight into a tenant-prefixed quarantine key, so the
app is never in the byte path. Scanning and release follow in UPLOADS-02.
"""

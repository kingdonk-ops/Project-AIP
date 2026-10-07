# E-signatures & tamper-evident records — Tech stack advisor


- **note**: pyHanko with KMS-backed keys gives PAdES seals; node-signpdf is weaker, which is another reason to stay on Python. Use S3 Object Lock in compliance mode for retained records and anchor the audit hash chain there.

# Terminology dictionary & localisation — Tech stack advisor


- **note**: i18next with ICU and per-tenant override tables fits well, and the same dictionary must feed PDF templates and emails server-side (Python i18n or ICU via a shared JSON pack). Beware the RFI naming clash with the hold-point inspection kind.

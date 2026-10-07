# Offline field app & sync — Security advisor


- **note**: Local data on tablets is exposed if devices are lost. Encrypt IndexedDB where feasible, bind devices, support remote revoke and wipe, and limit sync scope. Re-check authorisation on every push, and treat client-supplied timestamps and IDs as untrusted.

# Cost items & schedule of rates (thin) — Architecture & code structure


- **change isolation**: Nothing is built. Remove the module from the registry, scope doc and dependency lists; dependants must not import it. If pricing is revisited later, it can return as a new module behind the same cost-code field. The per-contract rate question is dropped with it.
- **config not code**:
  - Cost code lists, if needed, load as a reference pack through ref_packs rather than a module
- **reuses shared**:
  - None: module removed per owner comment. Dependants (change, procurement, scope_work) use a plain cost_code/WBS/CTR text field on their own records, as already carried by the Scope Portal.

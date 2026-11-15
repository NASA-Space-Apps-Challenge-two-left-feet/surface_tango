# Status: quake ground truth (#24)

- Completed the source review and documented candidate municipal damage reports and neighborhood boundaries for Armenia, Pereira and Manizales in `reports/ground_truth.md`.
- Armenia boundary audit and conservative name crosswalk are documented separately. Supporting raw GIS snapshots, CSVs and map remain in ignored local cache; no geometry was silently repaired and no damage labels were assigned.
- Acceptance gaps remain: complete neighborhood assessment coverage, official boundary adoption/vintage/terms, stable identities, topology review and ambiguous locations. This is a research handoff, not accepted scientific ground truth.
- The official power/headline decision (#25), configuration freeze (#26) and real scorecard (#32) remain with their respective tasks. The latest upstream data gate (#23) is available.
- Validation: publication checks use `make check`, `make test`, explicit hooks on new files and `make ci`. Only research documents and the optional diagnostic helper are included.

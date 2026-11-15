# Status: quake scoring (#18)

- Implemented the pure scoring library and known-answer tests: percentile ranking, precision@k, Wilson intervals, whole-barrio paired bootstrap, built-up excess, informative gate and directional claim rule.
- Stable original unit identity resolves tied rankings consistently across repeated bootstrap draws. Test fixtures and API boundaries are documented in `validation/ALLOWLIST.md`.
- Publication scope: issue #18 only. Real-data scorecard assembly (#32) remains blocked by accepted labels, frozen pre-registration and pipeline inputs. No co-event data were opened.
- Validation: publication checks use `make check`, `make test`, explicit hooks on new files and `make ci`. Pure-logic fixtures use no source granules.

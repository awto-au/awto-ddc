# Colour controls #371 review archive

- Requested archive: 28 November 2026.
- Scope: preserve the proposed patch, review and validation evidence. This archive does not apply or merge firmware changes, close #371, flash a monitor or change live settings.
- Source issues: [RGB writes #371](https://github.com/awto-au/awto-ddc/issues/371), [preset calibration #278](https://github.com/awto-au/awto-ddc/issues/278).
- Proposed behaviour: editing RGB selects User, starts with the active gains, changes only the requested channel, and persists User mode plus gains. Explicit User selection recalls its saved or pending triple.
- Validation: 1,452 simulator assertions passed; focused GUI, DDC/menu and link checks passed. Runtime ISR validation remains blocked by a simulator bank-loading error. The complete result and other limitations are in [VALIDATION.md](VALIDATION.md).
- Calibration: the current recovered presets have distinct coefficients; Kelvin accuracy and sRGB compliance remain unmeasured. No gain values were invented or changed.
- Newer decision: [Dan approved automatic User selection on 28 November](https://github.com/awto-au/awto-ddc/issues/371#issuecomment-7231831452); that comment still says implementation is pending. The original reports predate this decision. Preset naming/calibration and approval before implementation merge or monitor operations remain separate.
- Before implementation: check newer awto-ddc changes, recover/rebase the patch, run the normal development toolchain and full gates, then obtain approval before merging or physical-monitor operations.

## Preserved material

- [Review and MCCS comparison](REVIEW.md).
- [Validation record and reproduction commands](VALIDATION.md).
- [Complete original bundle](awto-ddc-colour-controls-371-review.zip): git format patch, test logs, checksums and the local validation wrapper. No flashable image is included.
- Original implementation base: `3326a1d6f78e7c676947bf7d82f35eb6d9f7166e` in `awto-au/awto-ddc`.
- Original local review commit: `351d945`, branch `review/371-rgb-user`. It was not published as a remote branch or PR during the original work. Recover it from `0001-colour-controls.patch` inside the bundle.
- Original bundle: 35,988 bytes; SHA-256 `f95002d470264a99491f93cadc338e1e5de33590fe52627fe6906c2b34f0fee9`.

The archived reports record the state and tests from the original review; they are not a statement that the current upstream issue or code is unchanged.

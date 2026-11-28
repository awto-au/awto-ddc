# DRAM log consistency review (#391)

This branch publishes a review package. The implementation is contained in the patch and has not been applied to this branch's source files.

- Base: ce8e1625f5c168f67f0f28145395f2bee448f5f0
- Local implementation commit: aeec401e10fd23eb8f92713479d80e50f722cc62
- Apply: git am reviews/dram-log-391/0001-dram-log-consistency.patch in a checkout of the base.
- Validation: 65 focused tests pass, including production C function harness and offscreen GUI consistency tests. Full pinned SDCC target build and bank/XDATA validation remain pending.
- Port-busy defenses merged for #392 are preserved in the base.
- No live monitor operations or flashing were performed or authorized.

The SDK header is included only as a small contextual diff within the patch. Its full contents are not uploaded by this review-package commit. Automatic approval review blocked the full-source publication even after the user's explicit approval; this package avoids that full-header upload.

See design-and-validation.md for the alternatives, exact diagnostic behavior, simulation limits and release gates. The 2,276-versus-5,142 regression fixture reproduces the counts synthetically, not the unrecorded hardware bus interleaving.

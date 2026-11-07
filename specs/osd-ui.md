# Spec: osd-ui  (step 5, #65): our OSD menus, including the factory menu
Status: TO WRITE (spec writer: Sonnet). Template: `SPEC_TEMPLATE.md`. Interface below it: `awto/include/osd.h` (engine, step 4).

## Sources (spec side)
- Functional facts from the vendor image, tag `vendor-ui`: menu tree, items, value ranges and steps, defaults, key behaviour
  (menu/left/right/exit, repeat, timeouts), what each item changes. Method: `fw_sim_vendor.py` + `osd_render.py`
  (osd_model hooks) on the vendor image, walking every page with key actions -> `tmp/osd/vendor/<page>.png` + JSON state.
- Factory menu (kept, Dan 2026-11-07): same method on its pages; items and ranges as facts.
- NOT carried over: vendor code, fonts, icons, graphics, layouts as pixels. The clean tree redraws all assets (our font,
  our icons) and implements from the spec text.

## Spec content to produce
- Menu tree table: page, item, type (list / range / action), range, step, default, effect (as a call into our interfaces).
- Key table per state; timeouts with tags.
- Layout in our grid units (rows/cols), not vendor pixels.

## Oracle
- Side-by-side render: `osd_render.py` on the vendor image and on ours for the same key script; per page the PNGs go next
  to each other (`tmp/osd/sbs/<page>.png`) and the JSON states are diffed on menu facts (page, selected item, value).
  Pass = same facts per step; pixels may differ (our assets).
- Our-image renders: `osd_render.py` PNG diff against the last accepted render of ours.

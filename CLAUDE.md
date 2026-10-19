# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working rules for every change

- **Update the footer on every change.** The page footer in `index.html` (`.page-footer`, near the end of the markup) reads `Kasimir Reich · v<version> · <DD/MM/YYYY>`. Set the date to today's date and bump the version in the same edit. Version scheme: `MAJOR.MINOR.PATCH` — patch for fixes and tweaks, minor for new features, major for breaking changes to the workflow or output layout. Current: v1.19.4.
- **Commit after each edit.** When a change is finished, commit it straight away (small, focused commits; message explains the why). Don't let edits pile up uncommitted.

## What this is

A single-file, client-side ELISA analysis tool. The entire application is `index.html` — markup, CSS, and JS in one file with no framework, no build step, and no backend. It takes BMG Omega plate-reader CSV exports plus a metadata spreadsheet, fits standard/sample curves, and produces a styled `.xlsx` workbook (downloaded in-browser) plus on-page SVG charts.

Two runtime dependencies, inlined in `<script>` tags at the top of `index.html` (minified; no network needed, so the file works offline and can be downloaded and opened on its own — there is no service worker, manifest or `vendor/` folder):
- `xlsx-js-style` — read/write XLSX with cell styling.
- `jszip` — used to post-process the written XLSX (see conditional formatting below).

## Running / developing

There is no build, lint, or test suite. To preview, serve the directory statically (config in `.claude/launch.json`):

```
npx serve -p 7823 .
```

Then open `http://localhost:7823`. Opening `index.html` directly via `file://` also works. All logic runs in the browser; "processing" is triggered by the Process button (`runProcessing`), which reads the loaded files from in-memory state and writes a workbook via `downloadBlob`.

Deployment: GitHub Pages serves `index.html` from the repo root (that's why the app file is named `index.html`). Default work branch is `main`.

## The central data-layout invariant

Almost every function depends on one fixed grid convention — understand this before editing the pipeline. After `mergePlates`, the in-memory `grid` is `29 rows × (numPlates × 14) cols`. For plate `p`, `offset = p * 14`, and within a plate:

- Columns `offset+1 … offset+12` hold the 12 well-columns (col 0 is the row label A–H, col 13 is padding).
- Row `7` → sample names (written from metadata before output).
- Rows `9–16` → the **450 nm** block ("Raw Data (450 1)").
- Rows `21–28` → the **570 nm** block ("Raw Data (570 2)"). A given well's 570 read is exactly **12 rows below** its 450 read.

These row/col numbers are hard-coded in `getSeries`, `subtractBackground`, and `buildCondfmtRanges` (the latter uses Excel 1-indexed rows, i.e. 450 nm = rows 10–17, 570 nm = rows 22–29). Changing the layout means updating all of them in lockstep.

## Page layout

Four collapsible sections (`.sec`): **1 Upload** (CSV + metadata), **2 Processing** (analysis options, Process, log), **3 Reviewing** (`#chartsSection`), **4 Download** (filename + button). `setSection`/`toggleSection`/`setBadge` drive them; `updateSections()` keeps the Review/Download badges and the download button in sync with `review`. `runProcessing` collapses Upload when it starts and Processing when it finishes successfully, then opens Reviewing; Download opens once every plate is accepted. `newAnalysis` resets all four.

## Progress bar

Processing shows a progress bar with percentage and an ETA (pace so far). Fitting is written as generators (`ec50Gen`, `plateEntryGen`) that yield after every series: `buildDataSheet` drains them synchronously (`drain`), while `runProcessing` first fills the per-plate cache through `warmCache`, awaiting a tick per series (`makeProgress().yieldMaybe()` repaints every ~30 ms). `computeSuggestions` ticks per series too. Bands: 5–70 % fitting, 70–97 % outlier screening. A cancelled run (New analysis) throws `CANCELLED` from a tick.

## Parallel fitting (Web Workers)

`createFitPool` builds a pool of module-less workers from a Blob whose source is assembled at run time from the fitting functions via `Function.prototype.toString` (`fitWorkerSource`) — no extra files, works offline. **Any function a worker needs must be listed in `fitWorkerSource`'s `fns` array**, and must not touch the DOM or other globals (`OUTLIER` is serialised in). A job is `{type:'plate', p, excl, screen}`: it runs `plateEntryGen` for one plate and, with `screen`, the outlier screening on the fresh fits, posting a tick per series. `fitAndScreenParallel` drives the first run (progress 5–97 %); `warmCacheParallel`/`reanalyzeAsync` refit many plates after bulk exclusions. If workers are missing or fail, the main-thread path (`warmCache` + `computeSuggestions`) runs instead, so keep that path working. Workers are throttled inside the hidden preview pane, so benchmark with Node `worker_threads` or a visible browser tab. Measured: 8 Example plates, 1 → 7 workers 9.4 s → 2.6 s.

## Processing pipeline (in `runProcessing`)

0. **Reader import** (at file load, `loadCSVFiles` → `normalizePlateText`): BMG files pass through; BioTek Gen5, Tecan (CSV/XLSX) and SpectraMax/SoftMax Pro exports are found structurally (header row `1…12` + 8 rows of 12 values; tab/`;`/`,` delimiters, decimal comma, optional row letters) and rewritten as the canonical 29-line BMG layout, wavelengths taken from the text above each block (first read = signal slot, second = reference slot, swapped if the first is the longer wavelength). The formats were written from vendor documentation and synthetic exports, not real instrument files — validate against real exports before relying on a vendor.
1. `parseCsvText` (first 29 lines only) → `mergePlates` → the `grid` above.
2. Optional `subtractBackground(grid, numPlates)` — when the "Subtract 570 nm background" toggle is on (default on), replaces each 450 nm well with `450 − 570` in place, relabels the block header to "Data (450 − 570)", and leaves the 570 block intact. Runs *before* everything downstream, so corrected values flow into all fits and the output sheet automatically.
3. `parseMetadata(metaBytes)` → sample names, per-cell fill colors (copied into the output names row), and dilution series.
4. `buildDataSheet` → per plate: `getSeries` slices each column's 8-point dilution series, then `calculateEC50s` and `calculateConcentrations` fit a 4PL curve and interpolate. Returns the worksheet, a conditional-formatting spec, fitted params, and chart geometry.
5. `buildProtocolSheet` (run parameters, fit bounds, fitted standard and sample curve parameters).
6. **Review step, then download.** Process no longer downloads. It stores state in `review` (grid, meta, `excl` Set, `suggested` Set, `accepted` Set, per-plate fit `cache`) and renders interactive SVG charts (`renderReview`). Clicking a point toggles its exclusion (`toggleExclusion` → `reanalyze`, which refits only the touched plate via the cache). Exclusion keys are `"plate|col(1-12)|doseIndex(0-7)"` (`exKey`); `getSeries(grid, p, excl)` blanks excluded wells so they drop out of every fit, while the output sheet keeps the raw value, struck through, and adds an "Excluded Points" sheet. Suggested outliers come from `suggestOutliers` (leave-one-out refit of the two largest residuals; thresholds in `OUTLIER`) and are only suggestions until excluded. Download (`downloadResults`: `XLSX.write` → `injectConditionalFormatting` → `downloadBlob`) is enabled once every plate is accepted; any change to a plate un-accepts it.
   - **Batch-first review** (`TRIAGE` block, `plateFlags`): each plate gets flags — unresolved suggested outliers, failed fits, ED50/slope at a fit bound, poor R² (thresholds in `FLAG`, judged only for curves with OD range ≥ 0.3), bad standard. The default view is "All plates" (first tab; "Needs review" is the second) (not accepted and flagged or already edited); flagged plates graph only their flagged samples until "Show all" (`focusActive`/`isHidden`; the focus set is sticky per plate via `focusSamples`, so fixing a sample by exclusion never changes which curves are shown). A tile strip gives every plate's state; `review.view/cur/limit/focusOff` hold the view state. Keyboard: J/K/←/→ step, A accept & advance, X exclude suggested here, C clear here, F toggle view (`keydown` handler). Bulk changes (`setAllExclusions`, session restore) refit through the worker pool (`reanalyzeAsync`); single-point toggles still refit their plate synchronously.
   - **Missing / borrowed standard**: `standardMissing` flags a plate whose standard wells are absent or flat (OD span < `FLAG.STD_MIN_RANGE`) as "probably not pipetted". Its banner offers a dropdown of plates with a good standard; `review.stdFrom` (plate → source plate, saved in the session) makes `buildDataSheet` fit that plate against the source's fitted parameters (`plateEntryGen`'s `stdOverride`, part of the cache signature). Sources are fitted first, borrowers second; changing the source plate's points re-fits and un-accepts its borrowers. The borrowed plate's own standard points are dropped, the Protocol and Results sheets name the source.
   - **Saturation hunch** (`applyHookCorrection`, `HOOK` block; option "Correct saturation hunch", default on, `meta.hookFix`): when the concentrated dilutions are flat and below a peak just before the series falls, `plateEntryGen` fits the sample on a copy where the earlier points are raised to the peak. Interpolation, the chart points (`q.y`) and the output keep the real readings; corrected points carry `q.fy` (value the fit saw), which screening/R² use, are drawn with a dashed ring, and appear in italic blue on Processed Data plus a Protocol-sheet section. A near-ceiling shortcut (`HOOK.CEILING_OD`, peak among the first `EARLY_N` readings, earlier readings ≥ `PLATEAU_FRAC` of it and ≥ `CEIL_MIN_RISE` lower) corrects even a single low first dilution with no statistics; the stricter rule (≥2 points before and after the peak, rise vs. noise) handles peaks further down the series. Excluding the peak point undoes it. Thresholds are heuristic — tune on real data.
   - Standard fit uses wells with OD ≤ 2; sample interpolation uses the least-diluted reading with OD ≤ 1.5 (`stdFitPoints`, `sampleChoicePoint`), each with its own true dilution index.

## Things that are easy to get wrong

- **Conditional formatting is injected as raw XML, not via the library.** `xlsx-js-style` can't emit color-scale rules, so `injectConditionalFormatting` opens the written workbook with JSZip, splices `<conditionalFormatting>` elements into `xl/worksheets/sheet1.xml` (anchored before the first of `<ignoredErrors>/<pageMargins>/…` per the OOXML element order), and re-zips. It **must** re-emit with `type:'uint8array'` — a plain `Array` passed to `new Blob()` gets stringified and corrupts the file.
- **Curve fitting is hand-rolled.** `model4PL` + `levenbergMarquardt` (analytic Jacobian, one SSE per step, exits on a stalled fit; with `solveGaussian`) + `fitBest4PL` (multi-start over IC50 seeds, keeps best SSE). Fit bounds/initial guesses come from an optional **`Settings` sheet** in the metadata workbook (rows Bottom/Top/IC50/Hill × Lower/Initial/Upper; read by `parseFitSettings`, written by `createTemplate`). A missing sheet, row or unusable number falls back to the matching `DEFAULT_FIT` value. The same sheet can hold an optional **Universal Standard Curve** block (header row starting "Universal Standard", then Bottom/Top/IC50/Hill in column B; `parseUniversalStd`): with all four filled, every plate's concentrations are interpolated against that one curve (`calculateConcentrations(..., universalStd)`) instead of a per-plate fit; Hill is forced negative, standard-point outlier suggestions are skipped. There is no settings UI. Hill is entered positive (samples fall); `stdFitConfig` mirrors it negative for the rising standard curve. With background subtraction on, corrected baselines approach 0 while the default Bottom bound is ~0.03 — relevant if low-end interpolation looks off.
- **`parseCsvText` uses `Number()`, not `parseFloat()`** — deliberately, so labels like `"1. Raw Data (450 1)"` stay strings instead of becoming `1`.
- **Reading vs writing styles differ in `xlsx-js-style`.** When reading the metadata Names sheet, fill info is on `cell.s` directly (`s.patternType`, `s.fgColor`); when writing, it's nested under `s.fill`. `parseMetadata` handles both forms.
- **Metadata format is positional.** `Dilutions` sheet reads fixed cells `B2/B3` (standard start/dilution) and `B6/B7` (sample start/dilution). `Settings` sheet (optional) holds the 4PL bounds. `Names` sheet has one row per plate; header row is detected by `A1 === 'Plate'`. `createTemplate` generates a matching blank workbook (one Names row per loaded CSV, 6 if none).

## Example data

The `Example/` run (8 plates, metadata, output workbook) was removed from the repo; bring your own BMG CSVs plus a metadata workbook (use "Create a template file") to exercise the pipeline end-to-end.

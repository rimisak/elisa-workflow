# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file, client-side ELISA analysis tool. The entire application is `index.html` — markup, CSS, and JS in one file with no framework, no build step, and no backend. It takes BMG Omega plate-reader CSV exports plus a metadata spreadsheet, fits standard/sample curves, and produces a styled `.xlsx` workbook (downloaded in-browser) plus on-page SVG charts.

Two runtime dependencies, both loaded from CDN (so a network connection is required even when running locally):
- `xlsx-js-style` — read/write XLSX with cell styling.
- `jszip` — used to post-process the written XLSX (see conditional formatting below).

## Running / developing

There is no build, lint, or test suite. To preview, serve the directory statically (config in `.claude/launch.json`):

```
npx serve -p 7823 .
```

Then open `http://localhost:7823`. Opening `index.html` directly via `file://` also works but the CDN `<script>` tags still need network access. All logic runs in the browser; "processing" is triggered by the Process button (`runProcessing`), which reads the loaded files from in-memory state and writes a workbook via `downloadBlob`.

Deployment: GitHub Pages serves `index.html` from the repo root (that's why the app file is named `index.html`). Default work branch is `main`.

## The central data-layout invariant

Almost every function depends on one fixed grid convention — understand this before editing the pipeline. After `mergePlates`, the in-memory `grid` is `29 rows × (numPlates × 14) cols`. For plate `p`, `offset = p * 14`, and within a plate:

- Columns `offset+1 … offset+12` hold the 12 well-columns (col 0 is the row label A–H, col 13 is padding).
- Row `7` → sample names (written from metadata before output).
- Rows `9–16` → the **450 nm** block ("Raw Data (450 1)").
- Rows `21–28` → the **570 nm** block ("Raw Data (570 2)"). A given well's 570 read is exactly **12 rows below** its 450 read.

These row/col numbers are hard-coded in `getSeries`, `subtractBackground`, and `buildCondfmtRanges` (the latter uses Excel 1-indexed rows, i.e. 450 nm = rows 10–17, 570 nm = rows 22–29). Changing the layout means updating all of them in lockstep.

## Processing pipeline (in `runProcessing`)

1. `parseCsvText` (first 29 lines only) → `mergePlates` → the `grid` above.
2. Optional `subtractBackground(grid, numPlates)` — when the "Subtract 570 nm background" toggle is on (default on), replaces each 450 nm well with `450 − 570` in place, relabels the block header to "Data (450 − 570)", and leaves the 570 block intact. Runs *before* everything downstream, so corrected values flow into all fits and the output sheet automatically.
3. `parseMetadata(metaBytes)` → sample names, per-cell fill colors (copied into the output names row), and dilution series.
4. `buildDataSheet` → per plate: `getSeries` slices each column's 8-point dilution series, then `calculateEC50s` and `calculateConcentrations` fit a 4PL curve and interpolate. Returns the worksheet, a conditional-formatting spec, fitted params, and chart geometry.
5. `buildProtocolSheet` + `buildSOPSheet` (the SOP is static lab-protocol text).
6. `XLSX.write` → `injectConditionalFormatting` → `downloadBlob`; `renderCharts` draws on-page SVGs.

### Optional "Edge-effect ED50" stage (toggle, default off)

Ported from `elisa_ed50.py`. When `#corrEd50Chk` is on, `buildDataSheet` also runs `buildCorrectedAnalysis` and `writeCorrectedRows`, and `runProcessing` appends two sheets: **"ED50 Corrected"** (one row per sample: censored ED50, 4PL cross-check, plateau OD, flags, back-calculated conc.) and **"QC Edge Effect"** (per-row blank ODs, edge excess, corrected standard-curve params). It also writes labelled rows **37–41** onto the Processed Data sheet (directly into the `ws` object after `aoaToSheet`, extending `!ref` — *not* via `fullData`, whose `styledData` map would re-wrap the cells). Rows 31/35 are left untouched.

What it does differently from the main pipeline: background is subtracted **per row** using in-plate blank columns (columns named `blank`; two → distinct edge/interior profiles, one → both fall back to it, none → that plate is skipped, not corrupted), the descending limb is fitted with **Bottom fixed at 0** and **Top fixed to the observed plateau**, ED50 is the interpolated half-plateau crossing (not a 4PL midpoint), and a curve whose plateau is below `CORR.MIN_PLATEAU_OD` is censored (`n.d.`). Thresholds live in the `CORR` block. Column roles come from the `grid[7]` names, so this is robust to the app's name-driven layout unlike the Python's fixed `COL_*` indices. If "Subtract 570 nm background" is also on, this stage runs on the 570-subtracted values (a warning is logged).

## Things that are easy to get wrong

- **Conditional formatting is injected as raw XML, not via the library.** `xlsx-js-style` can't emit color-scale rules, so `injectConditionalFormatting` opens the written workbook with JSZip, splices `<conditionalFormatting>` elements into `xl/worksheets/sheet1.xml` (anchored before the first of `<ignoredErrors>/<pageMargins>/…` per the OOXML element order), and re-zips. It **must** re-emit with `type:'uint8array'` — a plain `Array` passed to `new Blob()` gets stringified and corrupts the file.
- **Curve fitting is hand-rolled.** `model4PL` + `levenbergMarquardt` (with `solveGaussian`) + `fitBest4PL` (multi-start over IC50 seeds, keeps best SSE). Fit bounds/initial guesses live in `DEFAULT_FIT` and are user-editable via the gear icon (`fitConfig`). With background subtraction on, corrected baselines approach 0 while the default Bottom bound is ~0.03 — relevant if low-end interpolation looks off.
- **`parseCsvText` uses `Number()`, not `parseFloat()`** — deliberately, so labels like `"1. Raw Data (450 1)"` stay strings instead of becoming `1`.
- **Reading vs writing styles differ in `xlsx-js-style`.** When reading the metadata Names sheet, fill info is on `cell.s` directly (`s.patternType`, `s.fgColor`); when writing, it's nested under `s.fill`. `parseMetadata` handles both forms.
- **Metadata format is positional.** `Dilutions` sheet reads fixed cells `B2/B3` (standard start/dilution) and `B6/B7` (sample start/dilution). `Names` sheet has one row per plate; header row is detected by `A1 === 'Plate'`. `createTemplate` generates a matching blank workbook.

## Example data

`Example/` holds a real 8-plate run: `1–8.CSV`, `MetaData_*.xlsx`, and the regenerated output `260611_*.xlsx` (produced with background subtraction on — its 450 block shows corrected values and the "Data (450 − 570)" header). Use these to exercise the pipeline end-to-end.

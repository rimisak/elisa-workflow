# ELISA Workflow App

A macOS app for processing BMG Omega plate reader CSV files into a formatted Excel workbook with EC50 estimates and interpolated antibody concentrations.

---

## Requirements

### System
| Requirement | Minimum version |
|-------------|----------------|
| macOS | 13 Ventura or later |
| Xcode | 15 or later (to build from source) |
| Python | 3.9 or later |

### Python packages
The app calls a bundled Python script at runtime. The following packages must be available in whichever `python3` is on your `PATH` (or in a standard location — see [Python discovery](#python-discovery) below):

```
pip3 install openpyxl scipy numpy
```

| Package | Purpose |
|---------|---------|
| `openpyxl` | Reading and writing `.xlsx` files |
| `scipy` | 4-parameter logistic curve fitting (`curve_fit`) |
| `numpy` | Numerical operations |

---

## Building & running

1. Open `ELISAWorkflowApp/ELISAWorkflowApp.xcodeproj` in Xcode.
2. Select the **ELISAWorkflowApp** scheme and your Mac as the run destination.
3. Press **⌘R** to build and run.

> No third-party Swift packages or CocoaPods are used — the project has no additional Swift dependencies beyond the standard Apple frameworks.

---

## Python discovery

The app searches for a `python3` executable at startup in this order:

1. `/opt/homebrew/bin/python3`
2. `/usr/local/bin/python3`
3. `~/anaconda3/bin/python3`
4. `~/miniconda3/bin/python3`
5. `~/opt/anaconda3/bin/python3`
6. `~/.pyenv/shims/python3`
7. `/usr/bin/python3`
8. `which python3` (via a login shell, as a fallback)

The first interpreter that has `openpyxl`, `scipy`, and `numpy` importable is used. If none is found, the app shows an alert with installation instructions.

---

## Usage

1. **Drop CSV files** — drag one or more BMG Omega plate reader `.CSV` files onto the drop zone, or click the zone to browse.
2. **Load MetaData.xlsx** — drag an existing `MetaData.xlsx` onto the metadata field, click to browse for one, or use **Create MetaData.xlsx…** to generate a blank template.
3. **Choose an output folder** and enter a filename (without extension).
4. *(Optional)* Open **⚙ Curve Fit Settings** in the toolbar to adjust 4PL bounds and initial guesses.
5. Click **Process** — the output `.xlsx` opens automatically when processing succeeds.

---

## Example data

The `Example/` folder contains:

- `Example Input/` — 16 sample CSV files and a completed `MetaData.xlsx`
- `Example Output/` — the expected output workbook
- `SOPELISA.pdf` — the full ELISA SOP appended to every output file

Use these to verify your setup before running real experiments.

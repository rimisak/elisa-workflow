#!/usr/bin/env python3
"""
ELISA Workflow Processing Script
Processes BMG Omega plate reader CSV files into a formatted Excel workbook
with EC50 estimates and interpolated concentrations.

Usage:
    python3 elisa_workflow.py \
        --input-files /path/01.CSV /path/02.CSV ... \
        --metadata /path/to/MetaData.xlsx \
        --output-dir /path/to/output \
        --output-name my_experiment
"""

import argparse
import os
import sys
from pathlib import Path
from copy import copy

import openpyxl
import openpyxl as xl
from openpyxl.formatting.rule import ColorScaleRule
import numpy as np
from scipy.optimize import curve_fit

# Mutable curve-fit config — overridden by CLI args in main().
# Order for all lists: [bottom, top, ic50, hill]
_FIT_CONFIG = {
    "lower": [0.029, 0.5,  0.0,  -1.0],
    "upper": [0.031, 5.0,  1e6,   1.0],
    "p0":    [0.03,  3.0,  50.0,  1.0],
}


def ElisaMerge(filepath1, filepath2, newfilepath):
    with open(filepath1, errors='replace') as f:
        lines1 = f.readlines()
    with open(filepath2, errors='replace') as f:
        lines2 = f.readlines()

    lines = []
    spacer = [
        ",,,,,,,,,,,,",
        ",,,,,,,,,,,,",
        "",
        ",,,,,,,,,,,",
        ",,,,,,,,,,,,,,",
        "",
        ",,,,,,,,,,,,,,",
        "",
        ",",
    ]
    for i in range(0, 29):
        if i in range(9, 17) or i in range(21, 29):
            lines.append(lines1[i][:-1] + ",," + lines2[i])
        elif i == 20:
            lines.append(lines1[i][:-1] + "," + lines2[i])
        elif i in range(17, 20):
            lines.append(lines1[i][:-1] + ",,,,,,,,,,,,,," + lines2[i])
        else:
            lines.append(lines1[i][:-1] + spacer[i] + lines2[i])

    with open(newfilepath, "w") as f:
        f.writelines(lines)


def MergeSpecificFiles(file_paths, output_dir, output_name):
    """Merge an explicit list of CSV files into an Excel workbook.

    Replaces MergeAllInFolder: instead of globbing a directory, accepts
    a specific list of file paths (sorted alphabetically by filename to
    match the original behavior).
    """
    sorted_files = sorted(file_paths, key=lambda p: Path(p).name)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    combinepath = str(output_dir / f"{output_name}.csv")
    combinedpathXLSX = str(output_dir / f"{output_name}.xlsx")

    # ElisaMerge only processes the first 29 lines of each CSV (range(0,29)).
    # A raw plate-reader file can be 60+ lines (it appends a well-by-well
    # section after row 29 that would bloat max_column and confuse the pipeline).
    # Truncate to 29 lines here so single-file runs behave identically to merged ones.
    with open(sorted_files[0], errors='replace') as f:
        lines1 = f.readlines()[:29]
    with open(combinepath, "w") as f:
        f.writelines(lines1)

    for filepath in sorted_files[1:]:
        ElisaMerge(combinepath, str(filepath), combinepath)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Processed Data"

    with open(combinepath) as f:
        reader = f.readlines()
        for row in reader:
            row = row.split(",")
            for i in range(len(row)):
                try:
                    row[i] = float(row[i])
                except Exception:
                    row[i] = row[i]
            ws.append(row)

    wb.save(combinedpathXLSX)
    os.remove(combinepath)

    print(f"File saved to: {combinedpathXLSX}")
    print("Done with merging!")
    print("")
    return combinedpathXLSX


def ColorTheTables(path):
    wb = xl.load_workbook(path)
    ws = wb.active

    color_scale_rule_450 = ColorScaleRule(
        start_type='percentile', start_value=1, start_color='63BE7B',
        mid_type='percentile', mid_value=50, mid_color='FFEB84',
        end_type='percentile', end_value=99, end_color='F8696B'
    )
    for i in range(0, int(ws.max_column / 14)):
        start = ws.cell(row=10, column=2 + 14 * i).coordinate
        end = ws.cell(row=17, column=13 + 14 * i).coordinate
        ws.conditional_formatting.add(start + ":" + end, color_scale_rule_450)

    color_scale_rule_570 = ColorScaleRule(
        start_type='percentile', start_value=1, start_color='638ABE',
        mid_type='percentile', mid_value=50, mid_color='FFFFFF',
        end_type='percentile', end_value=99, end_color='F8696B'
    )
    for i in range(0, int(ws.max_column / 14)):
        start = ws.cell(row=22, column=2 + 14 * i).coordinate
        end = ws.cell(row=29, column=13 + 14 * i).coordinate
        ws.conditional_formatting.add(start + ":" + end, color_scale_rule_570)

    wb.save(path)
    print("Done with coloring!")
    print("")


def RenameTheColumns(path, Npath):
    wb = xl.load_workbook(path)
    ws = wb.active
    Nwb = xl.load_workbook(Npath)
    names = Nwb["Names"]

    # New template format (created by the app) has a dedicated header row:
    #   A1 = "Plate",  B1 = "blank"
    # Old MetaData.xlsx files have the plate identifier in A1 (e.g. "Names Plate 1")
    # and real sample names in B1 — fall back to row-1 start for backward compatibility.
    has_header = (
        names.cell(row=1, column=1).value == "Plate" and
        names.cell(row=1, column=2).value == "blank"
    )
    start_row  = 2 if has_header else 1
    num_plates = names.max_row - (1 if has_header else 0)

    for i in range(num_plates):
        row = start_row + i
        for j in range(1, 13):
            value = names.cell(row=row, column=j + 1).value
            fill  = names.cell(row=row, column=j + 1).fill
            ws.cell(row=8, column=i * 14 + j + 1).value = value
            ws.cell(row=8, column=i * 14 + j + 1).fill  = copy(fill)

    wb.save(path)
    print("Done with adding the sample names!")
    print("")


def GetDilInfo(mergerpath, Mpath):
    wb = xl.load_workbook(mergerpath)
    Nwb = xl.load_workbook(Mpath)
    dilutions = Nwb["Dilutions"]
    standard_start = dilutions["B2"].value
    standard_dil = dilutions["B3"].value
    sample_start = dilutions["B6"].value
    sample_dil = dilutions["B7"].value

    seriesST = [standard_start / (standard_dil ** i) for i in range(8)]
    seriesSA = [sample_start * (sample_dil ** i) for i in range(8)]

    return [seriesST, seriesSA]


def GetSeries(tablenumber, ws):
    start = tablenumber * 14
    results = dict()
    for col in range(start + 2, start + 14):
        name = str(ws.cell(row=8, column=col).value)
        if name == "blank":
            name = "blank" + str(col)
        results[name] = list()
        for el in list(ws.columns)[col - 1][9:17]:
            results[name].append(el.value)
    return results


def sigFit(xdata, ydata):
    def four_pl(x, bottom, top, ic50, hill):
        return bottom + (top - bottom) / (1 + (x / ic50) ** hill)

    # Drop paired (dilution, OD) entries where the OD is missing or non-finite.
    # Empty wells can produce None; non-numeric CSV cells produce strings.
    def _finite(y):
        try:
            return np.isfinite(float(y))
        except (TypeError, ValueError):
            return False

    pairs = [(x, y) for x, y in zip(xdata, ydata) if y is not None and _finite(y)]
    if not pairs:
        raise ValueError("No finite OD values available for curve fitting")
    xdata_f, ydata_f = zip(*pairs)

    p0     = list(_FIT_CONFIG["p0"])
    bounds = (list(_FIT_CONFIG["lower"]), list(_FIT_CONFIG["upper"]))
    params, cov = curve_fit(four_pl, xdata_f, ydata_f, p0=p0, bounds=bounds, maxfev=10000)
    return params


def calculateEC50s(datafrom450, dilutions):
    results = datafrom450
    dil = dilutions

    ic50s = []
    ic50s.append("Est. ED50")
    for el in results:
        if el == "standard":
            ic50s.append("/")
        elif el.startswith("blank"):
            ic50s.append("/")
        else:
            try:
                ic50 = round(sigFit(dil[1], results[el])[2])
                if ic50 < 10:
                    ic50 = 10
                ic50s.append(ic50)
            except Exception as e:
                print(f"Warning: could not fit EC50 for '{el}': {e}", flush=True)
                ic50s.append("/")
    ic50s.append("")
    return ic50s


def addEC50(mergerpath, dil):
    wb = xl.load_workbook(mergerpath)
    ws = wb.active
    totalEC50 = []
    for i in range(int(ws.max_column / 14)):
        results = GetSeries(i, ws)
        tableEC50 = calculateEC50s(results, dil)
        for el in tableEC50:
            totalEC50.append(el)

    ws.append([])
    ws.append(totalEC50)
    color_scale_rule = ColorScaleRule(
        start_type='percentile', start_value=1, start_color='63BE7B',
        mid_type='percentile', mid_value=50, mid_color='FFEB84',
        end_type='percentile', end_value=99, end_color='F8696B'
    )
    for i in range(0, int(ws.max_column / 14)):
        start = ws.cell(row=ws.max_row, column=3 + 14 * i).coordinate
        end = ws.cell(row=ws.max_row, column=12 + 14 * i).coordinate
        ws.conditional_formatting.add(start + ":" + end, color_scale_rule)
    wb.save(mergerpath)
    print("Done with estimating EC50s!")
    print("")


def inverse_4pl(y, top, bottom, hill, ic50):
    y = np.asarray(y)
    eps = 1e-12
    y = np.clip(y, bottom + eps, top - eps)
    return ic50 * ((top - y) / (y - bottom)) ** (1.0 / hill)


def addCon(mergerpath, dil):
    wb = xl.load_workbook(mergerpath)
    ws = wb.active

    conRow = []
    choValRow = []
    choDilRow = []
    fitted_params = []   # actual 4PL fit results per plate standard curve

    for i in range(int(ws.max_column / 14)):
        results = GetSeries(i, ws)

        # Strip None values (empty wells) before any max() comparisons
        results["standard"] = [v for v in results["standard"] if v is not None]

        STindex = 0
        while max(results["standard"]) > 2:
            results["standard"].remove(max(results["standard"]))
            STindex = STindex + 1

        params = sigFit(dil[0][STindex:], results["standard"])
        bottom, top, ic50, hill = params
        fitted_params.append({
            "plate":   i + 1,
            "bottom":  bottom,
            "top":     top,
            "ic50":    ic50,
            "hill":    hill,
            "n_points": len(results["standard"]),  # concentration points used
        })
        totalCon = []
        chosenVal = []
        chosenDil = []
        for el in results:
            if el.startswith("blank"):
                totalCon.append("/")
                chosenVal.append("/")
                chosenDil.append("/")
            elif el == "standard":
                first = results[el][0]
                con = inverse_4pl(first, top, bottom, hill, ic50) * 5 ** STindex / 1000
                totalCon.append(con)
                chosenVal.append(first)
                chosenDil.append(str(dil[0][STindex]) + " (Con)")
            else:
                indexDil = 0
                # Strip None values (empty wells) before outlier removal
                results[el] = [v for v in results[el] if v is not None]
                if not results[el]:
                    results[el] = [1.49]
                while max(results[el]) > 1.5:
                    results[el].remove(max(results[el]))
                    indexDil = indexDil + 1
                    if results[el] == []:
                        results[el] = [1.49]
                        indexDil = indexDil - 1
                con = inverse_4pl(max(results[el]), top, bottom, hill, ic50) * dil[1][indexDil]
                con = round(con / 1000, 2)
                totalCon.append(con)
                chosenVal.append(max(results[el]))
                chosenDil.append(dil[1][indexDil])

        conRow.append("Interp. Con.")
        for el in totalCon:
            conRow.append(el)
        conRow.append("")

        choValRow.append("Chos. Val.")
        for el in chosenVal:
            choValRow.append(el)
        choValRow.append("")

        choDilRow.append("Chos. Dil.")
        for el in chosenDil:
            choDilRow.append(el)
        choDilRow.append("")

    ws.append([])
    ws.append(choValRow)
    ws.append(choDilRow)
    ws.append(conRow)

    color_scale_rule = ColorScaleRule(
        start_type='percentile', start_value=1, start_color='63BE7B',
        mid_type='percentile', mid_value=50, mid_color='FFEB84',
        end_type='percentile', end_value=99, end_color='F8696B'
    )
    for i in range(0, int(ws.max_column / 14)):
        start = ws.cell(row=ws.max_row, column=3 + 14 * i).coordinate
        end = ws.cell(row=ws.max_row, column=12 + 14 * i).coordinate
        ws.conditional_formatting.add(start + ":" + end, color_scale_rule)

    wb.save(mergerpath)
    print("Done with estimating concentrations based on interpolated standard curve!")
    print("")
    return fitted_params


def addSOPSheet(mergerpath):
    """Append a 'SOP' sheet containing the full ELISA protocol text."""
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = xl.load_workbook(mergerpath)
    ws = wb.create_sheet("SOP")

    # ── Styles ────────────────────────────────────────────────────────────────
    TITLE_FONT   = Font(bold=True,  size=16, name="Calibri")
    META_FONT    = Font(italic=True, size=11, name="Calibri")
    SECTION_FONT = Font(bold=True,  size=12, name="Calibri")
    SUB_FONT     = Font(bold=True,  size=11, name="Calibri")
    BODY_FONT    = Font(size=10,             name="Calibri")
    STEP_FONT    = Font(size=10,             name="Calibri")
    BREAK_FONT   = Font(italic=True, size=9, color="808080", name="Calibri")

    SECTION_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    SUB_FILL     = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")

    WRAP = Alignment(wrap_text=True, vertical="top")
    TOP  = Alignment(vertical="top")

    ws.column_dimensions["A"].width = 7    # step numbers / sub-labels
    ws.column_dimensions["B"].width = 105  # content

    row = [1]   # mutable so inner helpers can update it

    def cell(col, value, font, fill=None, align=None, height=None):
        c = ws.cell(row=row[0], column=col, value=value)
        c.font  = font
        if fill:  c.fill      = fill
        if align: c.alignment = align
        if height: ws.row_dimensions[row[0]].height = height

    def next_row(h=None):
        if h: ws.row_dimensions[row[0]].height = h
        row[0] += 1

    def blank(h=6):
        next_row(h)

    def title(text):
        cell(2, text, TITLE_FONT, align=TOP, height=26); next_row()

    def meta(text):
        cell(2, text, META_FONT, align=TOP, height=14); next_row()

    def body(text, h=None):
        lines = max(1, len(text) // 100 + text.count("\n"))
        cell(2, text, BODY_FONT, align=WRAP, height=h or max(15, lines * 14)); next_row()

    def section(num, heading):
        blank(5)
        cell(1, str(num), SECTION_FONT, fill=SECTION_FILL, align=TOP)
        cell(2, heading.upper(), SECTION_FONT, fill=SECTION_FILL, align=TOP, height=18)
        next_row()

    def subsection(num, heading):
        blank(4)
        cell(1, num, SUB_FONT, fill=SUB_FILL, align=TOP)
        cell(2, heading, SUB_FONT, fill=SUB_FILL, align=TOP, height=16)
        next_row()

    def step(num, text, h=None):
        lines = max(1, len(text) // 100)
        cell(1, f"{num}.", STEP_FONT, align=TOP)
        cell(2, text, BODY_FONT, align=WRAP, height=h or max(15, lines * 14)); next_row()

    def substep(letter, text, h=None):
        lines = max(1, len(text) // 100)
        cell(1, f"  ({letter})", STEP_FONT, align=TOP)
        cell(2, text, BODY_FONT, align=WRAP, height=h or max(15, lines * 14)); next_row()

    def breakpoint_(label):
        blank(3)
        cell(2, f"{'· '*18}  {label}  {'· '*18}", BREAK_FONT, align=TOP, height=11)
        next_row(); blank(3)

    # ── Content ───────────────────────────────────────────────────────────────
    title("SOP ELISA")
    meta("Kasimir Reich  |  03-20-2026")
    blank()
    body("Goal: An enzyme-linked immunosorbent assay (ELISA) is described, which can be used to "
         "determine the quantity of antibodies or other proteins. Attached is an Excel file for "
         "calculations.", h=30)
    body("Estimated Time: Coating usually takes < 30 minutes the evening before, then around a "
         "day including waiting times.", h=22)

    # 1. Preparation
    section(1, "Preparation")

    subsection("1.1", "Planning of the Plates")
    step(1, "Determine the number and type of samples. Decide which proteins or antibodies to test for.")
    step(2, "Plan the plates. Around 15 plates can be run on a single day, but start with a lower "
            "number if still gaining experience. On each plate, the first column should be a negative "
            "control with water (blank). The last should be the positive control of known concentration "
            "(standard). Each column is the dilution series for a single sample.", h=56)
    step(3, "Plan the starting dilution and the dilution coefficient for both samples and standard. "
            "For example: Start with 1:50 for samples and then dilute 1:3. Start with 1000 ng/mL for "
            "the standard and do a 1:5 dilution.", h=42)
    step(4, "Do the calculations using the Excel spreadsheet.")
    step(5, "Check that the washing machine is available for the day of your ELISA.")
    breakpoint_("Flexible Break Point")

    subsection("1.2", "Coating")
    step(1, "Prepare a 2 µg/mL coating solution of the protein you want to coat with (e.g. TM4 core "
            "gp140 protein or the anti-idiotype antibody anti-3BNC117 human IgG1k). The total volume "
            "can be calculated using the spreadsheet.", h=42)
    step(2, "Prepare a wet chamber: Take the plastic box from the 4°C room. Put wet paper towels "
            "around the edges.", h=28)
    step(3, "Take a flat bottom ELISA 96-well plate.")
    step(4, "Fill 25 µL of the coating solution into each well.")
    step(5, "Put the plate into the wet chamber box and put the box into the 4°C room.")
    step(6, "Repeat for all plates.")
    step(7, "Let the plates incubate overnight.")
    step(8, "Check whether blocking solution (5% milk) is prepared. It can be found in the door of "
            "the Mr. Shiny fridge.", h=28)
    step(9, "If not, prepare new 5% milk: Take a fresh bottle of 1X PBS (Attention: not 10X!). Go "
            "to the weighing room and add 25 g of milk powder. Mix well by inverting and put into the "
            "fridge door.", h=42)
    breakpoint_("Overnight Break Point")

    # 2. Performing the ELISA
    section(2, "Performing the ELISA")
    body("Work one plate at a time to avoid the drying out of plates. If plates dry out, the margins "
         "will have a higher signal in the measurements (edge effect). Always keep the plates covered "
         "by another (empty) plate. Keep in the wet chamber as much as possible.", h=42)

    subsection("2.1", "Blocking")
    step(1, "Take the plates from the 4°C room.")
    step(2, "Throw out the coating solution and blot dry.")
    step(3, "Add 170 µL of the 5% milk to each well using the automatic multichannel pipette.")
    step(4, "Incubate for 2 h in the wet chamber at room temperature.")
    step(5, "Prepare for later steps:")
    substep("a", "Take all samples from the freezer and let them unthaw.")
    substep("b", "Get the secondary antibody (Harry's ELISA box in the Mr. Shiny fridge) and the "
                 "standard (freezer below Harry's bench) and keep them on ice.", h=28)
    substep("c", "Take the TMB solutions for the enzymatic reaction out of the 4°C room and let "
                 "them warm up to room temperature.", h=28)
    breakpoint_("Coffee Break Point")

    subsection("2.2", "Preparation of Dilution Series and Sample Loading")
    body("Once the samples are ready, start making the dilution series.")
    step(1, "Take a V-shaped 96 ELISA well plate and begin by preparing with PBS (e.g. 120 µL into "
            "each well of the first row and 90 µL into the others).", h=28)
    step(2, "Leave the blank and add the serum (e.g. 2.4 µL for 1:50) starting dilution for each "
            "sample into the first row.", h=28)
    step(3, 'Use the "Pipette and Mix" mode of the automatic multichannel pipette to mix and '
            "transfer (e.g. 30 µL for 1:4).", h=28)
    step(4, "Prepare the standard once for all the plates using 8 FACS tubes (e.g. start at "
            "1000 ng/mL in 625 µL and then transfer 125 µL to 500 µL to a 1:5 dilution).", h=28)
    step(5, "Once the blocking time is passed, wash plates using the plate washer George Washington.")
    substep("a", "Before opening any bottle be sure to depressurize!")
    substep("b", "Check that the PBS and water bottles are full and the trash empty.")
    substep("c", "Prime the machine using the yellow bottle (PBS). Sometimes there is a problem with "
                 "the pressure. This can often be circumvented by having the bottle fully filled and "
                 "checking the cap. Depressurize before opening.", h=42)
    substep("d", "Load the plates into the front tower and cover both towers with empty plates to "
                 "prevent the plates from drying out.", h=28)
    substep("e", "Select the program halfwell 6x PBS and click run.")
    substep("f", "After the plates are washed, prime with water (green).")
    step(6, "Load 25 µL of the samples:")
    substep("a", "Throw out the washing PBS and blot dry.")
    substep("b", "Using a normal multichannel transfer 25 µL of the dilution series: Reuse the tips. "
                 "Start with the highest dilution, transfer without blowing out, blow out over the "
                 "original dilution and then move on to the next highest dilution.", h=42)
    substep("c", "To keep things simple, use a second pipette to transfer the standard and reuse "
                 "these tips.", h=28)
    step(7, "Incubate for 1.5 h in the wet chamber at room temperature.")
    breakpoint_("Lunch Break Point")

    subsection("2.3", "Adding the Secondary Antibody")
    step(1, "After incubation, wash the plates using the program halfwell 6x PBS. Prime with PBS "
            "before and with water after.", h=28)
    step(2, "Meanwhile, prepare a 1:5000 dilution of the secondary antibody (e.g. anti-mouse "
            "IgG-HRP, antibody is Jackson Cat. 115-035-071 (0.8 mg/mL Harry April 2025)). Calculate "
            "the needed volume using the table. (25 µL × 96 wells × plate number + a little extra)", h=42)
    step(3, "Throw away the washing PBS and blot dry.")
    step(4, "Add 25 µL of the secondary antibody solution.")
    step(5, "Incubate for 1 h in the wet chamber at room temperature.")
    breakpoint_("Coffee Break Point")

    subsection("2.4", "Performing the Enzymatic Reaction")
    step(1, "After incubation, wash the plates using the program halfwell 6x PBS. Prime with PBS "
            "before and with water after. If you're likely to be the last person using the machine "
            "that day, start the shut down sequence — this cleans and depressurizes the machine.", h=42)
    step(2, "Meanwhile, prepare a 1:1 mix of the TMB substrate and the H₂O₂. In total, it's double "
            "the volume of the secondary antibody stain.", h=28)
    step(3, "Throw away the washing PBS and blot dry.")
    step(4, "Add 50 µL of the solution to each well.")
    step(5, "Develop the reaction for around 12 min until the highest concentration of standard is "
            "maxed out.", h=28)
    step(6, "Stop the reaction using 50 µL of 1 M H₂SO₄. Attention: Do not let any H₂SO₄ come "
            "on your clothes or skin!", h=28)
    step(7, "Read immediately afterwards using the plate reader.")

    subsection("2.5", "Reading the Results")
    step(1, "Use the plate reader machine. Open the Omega software and use the experiment Harry 450 "
            "and 570. 450 nm is the wavelength of the reaction. 570 nm is for measuring potential "
            "contamination or dirt.", h=42)
    step(2, "Name the plates with date, experiment name, and number.")
    step(3, "Use the software to open the plate holder and insert the plate.")
    step(4, "Start an experiment.")
    step(5, "Wait... (Great time to talk to someone or do some flashcards.)")
    step(6, "Repeat for all plates.")

    subsection("2.6", "Transfer of Data")
    step(1, "Open the Omega Analysis Software.")
    step(2, 'Click on open, select all the files and right-click them to select "Export as multiple '
            'ASCII files".')
    step(3, 'Save the data to the folder "tempshare/*yourname*".')
    breakpoint_("Flexible Break Point")

    # 3. Analysis
    section(3, "Analysis")

    subsection("3.1", "Cleaning of the Data")
    step(1, "Copy the files from tempshare to your computer.")
    step(2, "Merge the separate files manually or using Python.")
    step(3, "Color the individual tables according to Harry's color scheme (Red = larger) manually "
            "or using Python.", h=28)
    step(4, "Add the sample names using Python or manually.")

    subsection("3.2", "Determination of EC₅₀ or Concentration")
    step(1, "The EC₅₀ is the concentration at which half the maximum reaction occurs. It is the "
            "turning point of a sigmoidal function fitted to the data. This has the advantage of "
            "being independent of the starting concentration (as long as the data points allow for "
            "the fitting of a curve).", h=56)
    step(2, "It can be calculated using a Prism sheet or using Python.")
    step(3, "Based on the standard, an absolute concentration can also be calculated. This is done "
            "by fitting a function to the standard with the known concentration as x values and then "
            "using the inverse function to calculate the concentrations in the samples. Use Prism or "
            "Python.", h=42)

    wb.save(mergerpath)
    print("Done with adding SOP sheet!")
    print("")


def addProtocolSheet(mergerpath, Mpath, fit_config=None, fitted_params=None):
    """Append a 'Protocol Parameters' sheet summarising dilution settings and
    the actual 4PL parameters fitted to each plate's standard curve."""
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    if fit_config is None:
        fit_config = _FIT_CONFIG

    Nwb = xl.load_workbook(Mpath)
    dilutions = Nwb["Dilutions"]
    standard_start = dilutions["B2"].value
    standard_dil   = dilutions["B3"].value
    sample_start   = dilutions["B6"].value
    sample_dil     = dilutions["B7"].value

    wb = xl.load_workbook(mergerpath)
    ws = wb.create_sheet("Protocol Parameters")

    title_font  = Font(bold=True, size=14)
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    label_fill  = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")

    ws["A1"] = "ELISA Run Parameters"
    ws["A1"].font = title_font

    # Standard curve section
    ws["A3"] = "Standard Curve"
    ws["A3"].font = header_font
    for col in range(1, 3):
        ws.cell(row=3, column=col).fill = header_fill

    ws["A4"] = "Starting Concentration (ng/mL)"
    ws["B4"] = standard_start
    ws["A4"].fill = label_fill

    ws["A5"] = "Dilution Factor"
    ws["B5"] = standard_dil
    ws["A5"].fill = label_fill

    seriesST = [standard_start / (standard_dil ** i) for i in range(8)]
    ws["A6"] = "Dilution Series"
    ws["A6"].fill = label_fill
    for i, val in enumerate(seriesST):
        ws.cell(row=6, column=2 + i).value = round(val, 4)

    # Sample section
    ws["A8"] = "Samples"
    ws["A8"].font = header_font
    for col in range(1, 3):
        ws.cell(row=8, column=col).fill = header_fill

    ws["A9"] = "Starting Dilution Factor"
    ws["B9"] = sample_start
    ws["A9"].fill = label_fill

    ws["A10"] = "Dilution Factor"
    ws["B10"] = sample_dil
    ws["A10"].fill = label_fill

    seriesSA = [sample_start * (sample_dil ** i) for i in range(8)]
    ws["A11"] = "Dilution Series"
    ws["A11"].fill = label_fill
    for i, val in enumerate(seriesSA):
        ws.cell(row=11, column=2 + i).value = round(val, 2)

    # Fitted standard curve parameters section
    ws["A13"] = "Fitted Standard Curve Parameters (4PL)"
    ws["A13"].font = header_font
    for col in range(1, 7):
        ws.cell(row=13, column=col).fill = header_fill

    col_headers = ["Plate", "Bottom", "Top", "IC50 (ng/mL)", "Hill", "Conc. Points Used"]
    for col, text in enumerate(col_headers, start=1):
        cell = ws.cell(row=14, column=col, value=text)
        cell.font = Font(bold=True)

    for i, fp in enumerate(fitted_params or []):
        row = 15 + i
        ws.cell(row=row, column=1, value=f"Plate {fp['plate']}").fill = label_fill
        ws.cell(row=row, column=2, value=round(float(fp["bottom"]), 4))
        ws.cell(row=row, column=3, value=round(float(fp["top"]),    4))
        ws.cell(row=row, column=4, value=round(float(fp["ic50"]),   4))
        ws.cell(row=row, column=5, value=round(float(fp["hill"]),   4))
        ws.cell(row=row, column=6, value=fp.get("n_points", ""))

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 20

    wb.save(mergerpath)
    print("Done with adding protocol parameters sheet!")
    print("")


def create_metadata_template(num_plates, output_path):
    """Generate a MetaData.xlsx template with the correct sheet structure.

    Names sheet layout:
      Row 1  — header: "Plate" | "blank" | "sample 1" … "sample 10" | "standard"
      Rows 2+  — one row per plate:
                   col A  = "plate X - dXX assayXX"  (informational; not read by pipeline)
                   cols B–M = pre-filled default labels ("blank", "sample 1", … "standard")

    The pipeline reads columns B–M (2–13) of each data row; column A and row 1
    are skipped automatically by RenameTheColumns.

    Dilutions sheet: B2 = standard start conc, B3 = standard dil factor,
                     B6 = sample start dil, B7 = sample dil factor.
    """
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # ── Names sheet ──────────────────────────────────────────────────────────
    ws_names = wb.active
    ws_names.title = "Names"

    # The 12 default sample labels (blank + 10 samples + standard)
    sample_labels = ["blank"] + [f"sample {i}" for i in range(1, 11)] + ["standard"]

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    plate_fill  = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")

    # Row 1 — header
    hdr_plate = ws_names.cell(row=1, column=1)
    hdr_plate.value = "Plate"
    hdr_plate.font  = header_font
    hdr_plate.fill  = header_fill
    for col_idx, label in enumerate(sample_labels):
        cell = ws_names.cell(row=1, column=col_idx + 2)
        cell.value = label
        cell.font  = header_font
        cell.fill  = header_fill

    # Rows 2 … num_plates+1 — one row per plate
    for plate_idx in range(num_plates):
        row = plate_idx + 2
        # Column A: descriptive plate-name placeholder (not read by the pipeline)
        plate_name_cell = ws_names.cell(row=row, column=1)
        plate_name_cell.value = f"plate {plate_idx + 1} - dXX assayXX"
        plate_name_cell.fill  = plate_fill
        # Columns B–M: pre-filled default sample labels (edit these as needed)
        for col_idx, label in enumerate(sample_labels):
            ws_names.cell(row=row, column=col_idx + 2).value = label

    # Column widths and frozen header
    ws_names.column_dimensions["A"].width = 28
    for col_n in range(2, 14):   # B through M
        ws_names.column_dimensions[get_column_letter(col_n)].width = 12
    ws_names.freeze_panes = "B2"

    # ── Dilutions sheet ───────────────────────────────────────────────────────
    ws_dil = wb.create_sheet("Dilutions")
    ws_dil["A2"] = "Standard Starting Concentration (ng/mL)"
    ws_dil["B2"] = 1000
    ws_dil["A3"] = "Standard Dilution Factor"
    ws_dil["B3"] = 5
    ws_dil["A6"] = "Sample Starting Dilution Factor"
    ws_dil["B6"] = 50
    ws_dil["A7"] = "Sample Dilution Factor"
    ws_dil["B7"] = 3

    for cell_ref in ["A2", "A3", "A6", "A7"]:
        ws_dil[cell_ref].font = Font(bold=True)
    ws_dil.column_dimensions["A"].width = 42
    ws_dil.column_dimensions["B"].width = 12

    wb.save(output_path)
    print(f"Template saved to: {output_path}")


def generate_metadata_xlsx(json_path):
    """Build a temporary MetaData.xlsx from a JSON config written by the SwiftUI app.

    JSON shape:
        {
          "plates": [{"names": [...12...], "colors": [...12 hex or ""...]}, ...],
          "standardConcentration": 1000,
          "standardDilutionFactor": 5,
          "sampleStartDilution": 50,
          "sampleDilutionFactor": 3
        }

    Returns the path to the generated .xlsx (caller is responsible for deleting it).
    """
    import json
    import tempfile
    from openpyxl.styles import PatternFill

    with open(json_path) as f:
        config = json.load(f)

    wb = openpyxl.Workbook()

    # Build a lookup from setup UUID string -> hex color
    setup_color = {
        s["id"]: s.get("color", "")
        for s in config.get("experimentalSetups", [])
    }

    # Names sheet
    ws_names = wb.active
    ws_names.title = "Names"
    for plate_idx, plate in enumerate(config["plates"]):
        row = plate_idx + 1
        names  = plate.get("names",  [])
        setups = plate.get("setups", [])
        for col_idx in range(12):
            cell = ws_names.cell(row=row, column=col_idx + 2)
            cell.value = names[col_idx] if col_idx < len(names) else ""
            setup_id  = setups[col_idx] if col_idx < len(setups) else ""
            hex_color = setup_color.get(setup_id, "")
            if hex_color:
                cell.fill = PatternFill(
                    start_color=hex_color, end_color=hex_color, fill_type="solid"
                )

    # Dilutions sheet
    ws_dil = wb.create_sheet("Dilutions")
    ws_dil["B2"] = config.get("standardConcentration",  1000)
    ws_dil["B3"] = config.get("standardDilutionFactor", 5)
    ws_dil["B6"] = config.get("sampleStartDilution",    50)
    ws_dil["B7"] = config.get("sampleDilutionFactor",   3)

    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp_path = tmp.name
    tmp.close()
    wb.save(tmp_path)
    return tmp_path


def main():
    parser = argparse.ArgumentParser(
        description="Process BMG Omega plate reader CSV files into a formatted Excel workbook."
    )

    # Template creation mode
    parser.add_argument(
        "--create-template", action="store_true",
        help="Create a blank MetaData.xlsx template instead of processing"
    )
    parser.add_argument(
        "--num-plates", type=int, default=1,
        help="Number of plate rows in the template (used with --create-template)"
    )
    parser.add_argument(
        "--template-output",
        help="Output path for the template file (used with --create-template)"
    )

    # Processing mode
    parser.add_argument(
        "--input-files", nargs="+",
        help="Paths to the CSV files from the plate reader (sorted alphabetically by filename)"
    )
    parser.add_argument(
        "--metadata",
        help="Path to MetaData.xlsx (contains Names and Dilutions sheets)"
    )
    parser.add_argument(
        "--output-dir",
        help="Directory where the output Excel file will be saved"
    )
    parser.add_argument(
        "--output-name",
        help="Base name for the output file (without extension)"
    )

    # Curve fit bounds (order: bottom top ic50 hill)
    parser.add_argument(
        "--fit-lower-bounds", type=float, nargs=4,
        default=[0.029, 0.5, 0.0, -1.0],
        metavar=("BOTTOM", "TOP", "IC50", "HILL"),
        help="Lower bounds for 4PL fit parameters"
    )
    parser.add_argument(
        "--fit-upper-bounds", type=float, nargs=4,
        default=[0.031, 5.0, 1e6, 1.0],
        metavar=("BOTTOM", "TOP", "IC50", "HILL"),
        help="Upper bounds for 4PL fit parameters"
    )
    parser.add_argument(
        "--fit-p0", type=float, nargs=4,
        default=[0.03, 3.0, 50.0, 1.0],
        metavar=("BOTTOM", "TOP", "IC50", "HILL"),
        help="Initial guesses for 4PL fit parameters"
    )

    args = parser.parse_args()

    if args.create_template:
        if not args.template_output:
            parser.error("--template-output is required with --create-template")
        create_metadata_template(args.num_plates, args.template_output)
        return

    # Regular processing
    if not args.input_files:
        parser.error("--input-files is required")
    if not args.metadata:
        parser.error("--metadata is required")
    if not args.output_dir:
        parser.error("--output-dir is required")
    if not args.output_name:
        parser.error("--output-name is required")

    _FIT_CONFIG["lower"] = args.fit_lower_bounds
    _FIT_CONFIG["upper"] = args.fit_upper_bounds
    _FIT_CONFIG["p0"]    = args.fit_p0

    print(f"Processing {len(args.input_files)} CSV file(s)...")
    print("")

    mergerpath = MergeSpecificFiles(args.input_files, args.output_dir, args.output_name)
    ColorTheTables(mergerpath)
    RenameTheColumns(mergerpath, args.metadata)
    dil = GetDilInfo(mergerpath, args.metadata)
    addEC50(mergerpath, dil)
    fitted_params = addCon(mergerpath, dil)
    addProtocolSheet(mergerpath, args.metadata, _FIT_CONFIG, fitted_params)
    addSOPSheet(mergerpath)
    print(f"Complete! Output: {mergerpath}")


if __name__ == "__main__":
    main()

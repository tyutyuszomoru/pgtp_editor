"""
pgtp_ui_tool.py
Interactive toolchain for PostgreSQL PHP Generator .pgtp UI string management.

Actions
-------
  extract   → parse a .pgtp file, write all UI strings to .csv
  translate → call Anthropic Claude API to fill in translations in a .csv
  apply     → write translations from a .csv back into a .pgtp file

CSV format
----------
Delimiter  : semicolon  ;
Quoting    : QUOTE_ALL  (every field in double quotes)
Encoding   : UTF-8 with BOM  (utf-8-sig — Excel opens without wizard)
Columns    : Type ; English text ; Context / Field name ; Translation

  Note: Excel will still split on ; inside &amp; — that is Excel's problem,
  not ours. The Python reader handles it correctly.

Apply behaviour
---------------
Every entry is applied exactly as written — no conflict detection, no skipping.
  - "Column header" uses the fieldName from Context as a secondary anchor,
    so the same English text can have different translations per column.
  - All other types use simple  attr="english" → attr="translation"  replacement.

Dependencies
------------
  pip install anthropic    (only required for the translate action)
"""

import os
import re
import csv
import html
import shutil
from pathlib import Path
from collections import defaultdict

# ── Working directory: same folder as this script ─────────────────────────────
WORK_DIR = Path(__file__).resolve().parent

# CSV dialect: semicolon delimiter, all fields quoted, UTF-8 with BOM
CSV_KWARGS = dict(delimiter=";", quoting=csv.QUOTE_ALL)
CSV_HEADER = ["Type", "English text", "Context / Field name", "Translation"]

# ── XML attribute map ──────────────────────────────────────────────────────────
TYPE_TO_ATTR = {
    "Column header":                "caption",
    "Menu / Page title":            "caption",
    "Detail tab title":             "caption",
    "Dropdown value":               "caption",
    "Short caption":                "shortCaption",
    "Column header hint (tooltip)": "headerHint",
    "Insert form caption":          "insertFormCaption",
    "Menu group name":              "groupName",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  UI helpers
# ═══════════════════════════════════════════════════════════════════════════════

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def choose_from_list(items, prompt, allow_cancel=True):
    """Print numbered list, return 0-based index or -1 for cancel."""
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    if allow_cancel:
        print("  0. Cancel / back to menu")
    while True:
        raw = input(f"\n{prompt}: ").strip()
        if allow_cancel and raw == "0":
            return -1
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return idx
        print(f"  → Enter a number between 1 and {len(items)}"
              + (" or 0 to cancel" if allow_cancel else ""))


def ask_filename(prompt, extension):
    """Ask for a filename stem, return Path with extension appended."""
    while True:
        name = input(f"{prompt}: ").strip()
        if not name:
            print("  → Name cannot be empty")
            continue
        if name.lower().endswith(extension.lower()):
            name = name[: -len(extension)]
        return WORK_DIR / (name + extension)


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV I/O helpers
# ═══════════════════════════════════════════════════════════════════════════════

def read_csv(path):
    """Read a semicolon-delimited CSV, return (header_row, list_of_rows)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, **CSV_KWARGS)
        header_row = next(reader)
        rows = list(reader)
    return header_row, rows


def write_csv(path, rows):
    """Write rows (including header as first row) to a semicolon CSV with BOM."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, **CSV_KWARGS)
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTRACT
# ═══════════════════════════════════════════════════════════════════════════════

def action_extract():
    header("EXTRACT — Scan .pgtp → write .csv")

    pgtp_files = sorted(WORK_DIR.glob("*.pgtp"))
    if not pgtp_files:
        print("  No .pgtp files found in", WORK_DIR)
        input("\nPress Enter to continue...")
        return

    idx = choose_from_list([f.name for f in pgtp_files], "Choose file")
    if idx < 0:
        return

    source = pgtp_files[idx]
    output = ask_filename("Output filename (without .csv)", ".csv")

    print(f"\nReading {source.name}...")
    content = source.read_text(encoding="utf-8", errors="replace")
    print(f"  {len(content):,} characters")

    rows = []  # list of (type, english, context)

    def add(type_label, text, context=""):
        text = text.strip()
        if text:
            rows.append((type_label, text, context))

    # Menu group names
    for m in re.finditer(r'\bgroupName="([^"]+)"', content):
        add("Menu group name", m.group(1))

    # Page captions — groupName before caption
    for m in re.finditer(
            r'<Page[^>]+?groupName="([^"]*)"[^>]+?caption="([^"]*)"', content):
        add("Menu / Page title", m.group(2), f"group: {m.group(1)}")

    # Page captions — caption before groupName
    for m in re.finditer(
            r'<Page[^>]+?caption="([^"]*)"[^>]+?groupName="([^"]*)"', content):
        add("Menu / Page title", m.group(1), f"group: {m.group(2)}")

    # Detail tab captions
    for m in re.finditer(r'<Detail\s+caption="([^"]*)"', content):
        add("Detail tab title", m.group(1))

    # Column headers (fieldName gives the anchor used in apply)
    for m in re.finditer(
            r'<ColumnPresentation\s+fieldName="([^"]*)"\s+caption="([^"]*)"', content):
        add("Column header", m.group(2), f"field: {m.group(1)}")

    # Insert-form captions
    for m in re.finditer(r'\binsertFormCaption="([^"]+)"', content):
        add("Insert form caption", m.group(1))

    # Column tooltips
    for m in re.finditer(r'\bheaderHint="([^"]+)"', content):
        add("Column header hint (tooltip)", m.group(1))

    # Short captions
    for m in re.finditer(r'\bshortCaption="([^"]+)"', content):
        add("Short caption", m.group(1))

    # Dropdown values
    for m in re.finditer(r'<Value\s+name="([^"]*)"\s+caption="([^"]*)"', content):
        add("Dropdown value", m.group(2), f"value key: {m.group(1)}")

    # Deduplicate on (type, english, context) — same english in different contexts kept
    seen, unique = set(), []
    for r in rows:
        key = (r[0], r[1], r[2])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Summary
    from collections import Counter
    counts = Counter(r[0] for r in unique)
    print(f"\nExtracted {len(unique)} unique entries:")
    for t, c in sorted(counts.items()):
        print(f"  {t}: {c}")

    # Write: header + data rows (Translation column empty)
    data = [CSV_HEADER] + [list(r) + [""] for r in unique]
    write_csv(output, data)
    print(f"\n✓  Written → {output.name}")
    input("\nPress Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
#  TRANSLATE
# ═══════════════════════════════════════════════════════════════════════════════

def action_translate():
    header("TRANSLATE — Fill translations via Claude API")

    csv_files = sorted(WORK_DIR.glob("*.csv"))
    if not csv_files:
        print("  No .csv files found in", WORK_DIR)
        input("\nPress Enter to continue...")
        return

    idx = choose_from_list([f.name for f in csv_files], "Choose CSV file")
    if idx < 0:
        return
    input_path = csv_files[idx]

    lang = input("Target language (e.g. French, Italian, Arabic): ").strip()
    if not lang:
        print("  → Language cannot be empty")
        input("\nPress Enter to continue...")
        return

    output_path = ask_filename("Output filename (without .csv)", ".csv")

    # Load CSV — col indices: 0=Type, 1=English, 2=Context, 3=Translation
    hdr, rows = read_csv(input_path)
    if len(hdr) < 3:
        print(f"  ERROR: expected at least 3 columns, found {hdr}")
        input("\nPress Enter to continue...")
        return

    # Ensure translation column exists
    if len(hdr) < 4:
        hdr.append("Translation")
        rows = [r + [""] for r in rows]

    trans_col = len(hdr) - 1  # last column = translation

    # Only rows without a translation (or translation == english)
    to_translate_idx = [
        i for i, r in enumerate(rows)
        if len(r) > trans_col and (not r[trans_col] or r[trans_col] == r[1])
    ]
    print(f"\n  Total entries      : {len(rows)}")
    print(f"  Need translation   : {len(to_translate_idx)}")

    if not to_translate_idx:
        print("  All entries already translated — nothing to do.")
        input("\nPress Enter to continue...")
        return

    # API setup
    try:
        import anthropic
    except ImportError:
        print("\nERROR: anthropic not installed.  Run:  pip install anthropic")
        input("\nPress Enter to continue...")
        return

    import json, time

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        api_key = input("ANTHROPIC_API_KEY not set. Paste your key: ").strip()
        if not api_key:
            print("  → No key provided.")
            input("\nPress Enter to continue...")
            return

    model  = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    SYSTEM_PROMPT = f"""You are a professional technical translator specialising in
industrial maintenance management systems (CMMS / EAM software).
Translate UI labels, column headers, menu items, and tooltips from English to {lang}.

Hard rules — never break these:
- Keep technical acronyms unchanged: WBS, HSE, SAP, CMMS, PSV, PTW, RPN, DMZ, CSV, SECE, OCE, DFM
- Keep single-letter codes unchanged: D, S, E, A, C, M, I, R
- Keep placeholder tokens unchanged: %tag%  %humanreadableid%  :fieldname
- Keep XML/HTML entities unchanged: &amp;  &lt;  &gt;  &quot;
- Keep HTML tags unchanged: <b>  </b>  <h1>  </h1>  <br>
- Keep special Unicode characters unchanged (e.g. ߷)
- Keep database identifiers unchanged (snake_case names, IDs like r_jcop)
- If a string is already in {lang}, return it as-is
- Keep translations short — these are UI labels, not prose
"""

    def translate_batch(batch_indices):
        items = {}
        for local_i, global_i in enumerate(batch_indices):
            r = rows[global_i]
            entry = {"text": r[1], "type": r[0]}
            if len(r) > 2 and r[2]:
                entry["context"] = r[2]
            items[str(local_i)] = entry

        user_msg = (
            f"Translate each 'text' value to {lang}.\n"
            "Return a JSON object mapping each numeric key to its translated string.\n"
            "No explanation, no markdown fences — raw JSON only.\n\n"
            + json.dumps(items, ensure_ascii=False, indent=2)
        )
        resp = client.messages.create(
            model=model, max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}]
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

    BATCH_SIZE = 60
    MAX_RETRIES = 3
    RETRY_DELAY = 3
    total = len(to_translate_idx)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print()

    for batch_num, start in enumerate(range(0, total, BATCH_SIZE), 1):
        batch = to_translate_idx[start: start + BATCH_SIZE]
        end_row = to_translate_idx[min(start + BATCH_SIZE, total) - 1] + 1
        print(f"  Batch {batch_num}/{n_batches}  ({len(batch)} strings) ... ",
              end="", flush=True)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = translate_batch(batch)
                for local_i, global_i in enumerate(batch):
                    rows[global_i][trans_col] = result.get(str(local_i), rows[global_i][1])
                print("✓")
                break
            except json.JSONDecodeError:
                if attempt < MAX_RETRIES:
                    print(f"JSON error, retry {attempt}/{MAX_RETRIES} ... ", end="", flush=True)
                    time.sleep(RETRY_DELAY)
                else:
                    print("FAILED (bad JSON) — keeping originals")
            except anthropic.RateLimitError:
                wait = RETRY_DELAY * attempt
                print(f"rate limit, waiting {wait}s ... ", end="", flush=True)
                time.sleep(wait)
                if attempt == MAX_RETRIES:
                    print("FAILED — keeping originals")
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"error ({e}), retry {attempt}/{MAX_RETRIES} ... ", end="", flush=True)
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"FAILED ({e}) — keeping originals")

    changed = sum(1 for r in rows if len(r) > trans_col and r[trans_col] and r[trans_col] != r[1])
    write_csv(output_path, [hdr] + rows)
    print(f"\n{changed}/{len(rows)} strings translated  →  {output_path.name}")
    input("\nPress Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
#  APPLY
# ═══════════════════════════════════════════════════════════════════════════════

def xml_safe(text):
    """Unescape any existing HTML entities then re-escape — prevents double-encoding."""
    return html.escape(html.unescape(text), quote=True)


def replace_attr(text, attr_name, english, translated):
    """Replace  attr="english"  with  attr="translated"  globally. Returns (text, count)."""
    pattern = re.compile(
        r'(' + re.escape(attr_name) + r'=")' + re.escape(english) + r'(")'
    )
    count = len(pattern.findall(text))
    if count == 0:
        return text, 0
    safe = xml_safe(translated)
    return pattern.sub(lambda m: m.group(1) + safe + m.group(2), text), count


def action_apply():
    header("APPLY — Write translations into .pgtp")

    pgtp_files = sorted(WORK_DIR.glob("*.pgtp"))
    if not pgtp_files:
        print("  No .pgtp files found in", WORK_DIR)
        input("\nPress Enter to continue...")
        return

    print("Target .pgtp file:")
    pgtp_idx = choose_from_list([f.name for f in pgtp_files], "Choose file")
    if pgtp_idx < 0:
        return
    source = pgtp_files[pgtp_idx]

    csv_files = sorted(WORK_DIR.glob("*.csv"))
    if not csv_files:
        print("  No .csv files found in", WORK_DIR)
        input("\nPress Enter to continue...")
        return

    print("\nTranslation CSV:")
    csv_idx = choose_from_list([f.name for f in csv_files], "Choose CSV")
    if csv_idx < 0:
        return
    csv_path = csv_files[csv_idx]

    out_name = input(f"\nOutput filename (Enter = overwrite {source.name}): ").strip()
    if out_name:
        if not out_name.lower().endswith(".pgtp"):
            out_name += ".pgtp"
        output = WORK_DIR / out_name
    else:
        output = source

    # Load CSV
    hdr, rows = read_csv(csv_path)
    if len(hdr) < 4:
        print("  ERROR: CSV must have at least 4 columns (Type; English; Context; Translation)")
        input("\nPress Enter to continue...")
        return

    trans_col = len(hdr) - 1  # last column = translation

    content  = source.read_text(encoding="utf-8", errors="replace")
    original = content

    # Backup — always
    backup = source.with_suffix(source.suffix + ".bak")
    shutil.copy2(source, backup)
    print(f"\nBackup → {backup.name}")

    dry = input("Dry run? (y/N): ").strip().lower() == "y"

    print("\nApplying...")
    cp_count    = 0
    attr_totals = defaultdict(int)

    for row in rows:
        if len(row) <= trans_col:
            continue
        typ    = row[0].strip()
        eng    = row[1]
        ctx    = row[2] if len(row) > 2 else ""
        transl = row[trans_col]

        # Skip untranslated / unchanged
        if not transl or transl == eng:
            continue

        attr = TYPE_TO_ATTR.get(typ)
        if not attr:
            continue

        safe = xml_safe(transl)

        # Column headers → fieldName-anchored replacement
        if typ == "Column header" and ctx.startswith("field: "):
            field     = ctx[len("field: "):]
            eng_esc   = re.escape(eng)
            field_esc = re.escape(field)

            # Both attribute orderings
            pat_a = re.compile(
                r'(<ColumnPresentation\b[^>]*?\bfieldName="' + field_esc +
                r'"[^>]*?\bcaption=")' + eng_esc + r'(")', re.DOTALL
            )
            pat_b = re.compile(
                r'(<ColumnPresentation\b[^>]*?\bcaption=")' + eng_esc +
                r'("[^>]*?\bfieldName="' + field_esc + r'")', re.DOTALL
            )

            n_a = len(pat_a.findall(content))
            n_b = len(pat_b.findall(content))
            if not dry:
                content = pat_a.sub(lambda m, t=safe: m.group(1) + t + m.group(2), content)
                content = pat_b.sub(lambda m, t=safe: m.group(1) + t + m.group(2), content)
            cp_count += n_a + n_b
            continue

        # All other types → simple global replacement
        if dry:
            pat   = re.compile(r'(?:' + re.escape(attr) + r'=")' + re.escape(eng) + r'(?=")')
            count = len(pat.findall(content))
        else:
            content, count = replace_attr(content, attr, eng, transl)
        attr_totals[attr] += count

    # Report
    print(f"  Column header (anchored) : {cp_count}")
    for a, n in sorted(attr_totals.items()):
        print(f"  {a} : {n}")
    grand = cp_count + sum(attr_totals.values())
    print(f"  Total : {grand}")

    if dry:
        print("\n[DRY RUN] Nothing written.")
    else:
        output.write_text(content, encoding="utf-8", errors="replace")
        orig_tags = len(re.findall(r'<[^?!][^>]*>', original))
        new_tags  = len(re.findall(r'<[^?!][^>]*>', content))
        if orig_tags != new_tags:
            print(f"\n⚠  WARNING: tag count changed! original={orig_tags}, output={new_tags}")
        else:
            print(f"✓  XML tag count unchanged ({orig_tags} tags)")
        print(f"✓  Written → {output.name}")

    input("\nPress Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

MENU_OPTIONS = [
    "Extract   — scan a .pgtp file → write .csv",
    "Translate — fill translations via Claude API",
    "Apply     — write .csv translations back into .pgtp",
    "Exit",
]


def main():
    ACTIONS = [action_extract, action_translate, action_apply]
    while True:
        clear()
        header("pgtp_ui_tool  —  UI string manager")
        print(f"  Working folder: {WORK_DIR}\n")
        idx = choose_from_list(MENU_OPTIONS, "Choose action", allow_cancel=False)
        if idx == len(MENU_OPTIONS) - 1:
            print("\nBye.\n")
            break
        ACTIONS[idx]()


if __name__ == "__main__":
    main()

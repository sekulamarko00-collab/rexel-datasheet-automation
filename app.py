from pathlib import Path
import pandas as pd

from excel_parser import parse_excel
from rexel_downloader import RexelDownloader


EXCEL_FILE = "input/artikli.xlsx"
COLUMN = "A"

OUTPUT_DIR = "output"

# Ovde menjaš opseg
START_POSITION = "1.16.001"
END_POSITION = "1.16.090"

# True = brže, browser se ne vidi
# False = vidiš browser dok radi
HEADLESS = True


def build_summary(results):
    total = len(results)
    success = sum(1 for r in results if r.get("success") is True)
    failed = sum(1 for r in results if r.get("success") is False)
    cached = sum(1 for r in results if r.get("cached") is True)
    merged = sum(1 for r in results if r.get("merged") is True)

    datasheet_not_found = sum(
        1 for r in results
        if str(r.get("error", "")).lower() == "datasheet not found"
    )

    not_pdf = sum(
        1 for r in results
        if str(r.get("error", "")).lower() == "downloaded file is not pdf"
    )

    product_not_found = sum(
        1 for r in results
        if str(r.get("error", "")).lower() in [
            "product not found",
            "exact rexel art.no. not found",
            "würth product not found",
        ]
    )

    wurth_catalog_not_found = sum(
        1 for r in results
        if str(r.get("error", "")).lower() == "würth catalog pdf not found"
    )

    wurth_not_electrical = sum(
        1 for r in results
        if str(r.get("error", "")).lower() == "würth product is not electrical equipment"
    )

    http_errors = sum(
        1 for r in results
        if str(r.get("error", "")).lower().startswith("http")
    )

    known = (
        datasheet_not_found
        + not_pdf
        + product_not_found
        + wurth_catalog_not_found
        + wurth_not_electrical
        + http_errors
    )

    other_errors = failed - known

    return {
        "total_tasks": total,
        "successful": success,
        "failed": failed,
        "downloaded_new": success - cached,
        "cached_or_merged": cached,
        "merged": merged,
        "datasheet_not_found": datasheet_not_found,
        "downloaded_file_not_pdf": not_pdf,
        "product_not_found": product_not_found,
        "wurth_catalog_not_found": wurth_catalog_not_found,
        "wurth_not_electrical": wurth_not_electrical,
        "http_errors": http_errors,
        "other_errors": other_errors,
    }


def explain_error(error):
    error = str(error or "").lower()

    if error == "datasheet not found":
        return "Na Rexel strani nije pronađen Produktdatenblatt link. Skinuti ručno."

    if error == "downloaded file is not pdf":
        return "Link postoji, ali ne vraća pravi PDF nego npr. datasheet.php / HTML. Skinuti ručno."

    if error == "product not found":
        return "Rexel proizvod nije pronađen. Proveriti Rexel broj ručno."

    if error == "exact rexel art.no. not found":
        return "Nađena je lista rezultata, ali nijedan rezultat nema tačan Rexel Art.No. Skinuti/proveriti ručno."

    if error == "würth product not found":
        return "Würth proizvod nije pronađen. Proveriti W broj ručno."

    if error == "würth catalog pdf not found":
        return "Na Würth strani nije pronađena Katalogseite als PDF. Skinuti ručno."

    if error == "würth product is not electrical equipment":
        return "Würth proizvod ne izgleda kao elektro oprema, preskočeno."

    if error.startswith("http"):
        return "HTTP greška pri download-u. Pokušati ručno."

    if not error:
        return ""

    return "Nepoznata greška. Proveriti ručno."


def print_summary(summary):
    print("\n" + "=" * 80)
    print("REZIME DOWNLOAD-A")
    print("=" * 80)
    print(f"Ukupno zadataka:              {summary['total_tasks']}")
    print(f"Uspešno obrađeno:             {summary['successful']}")
    print(f"Novo skinuto:                 {summary['downloaded_new']}")
    print(f"Cache / spojeno:              {summary['cached_or_merged']}")
    print(f"Merged fajlova:               {summary['merged']}")
    print(f"Neuspešno:                    {summary['failed']}")
    print("-" * 80)
    print(f"Nema Rexel Produktdatenblatt: {summary['datasheet_not_found']}")
    print(f"Link nije pravi PDF:          {summary['downloaded_file_not_pdf']}")
    print(f"Proizvod nije nađen:          {summary['product_not_found']}")
    print(f"Würth nema katalog PDF:       {summary['wurth_catalog_not_found']}")
    print(f"Würth nije elektro oprema:    {summary['wurth_not_electrical']}")
    print(f"HTTP greške:                  {summary['http_errors']}")
    print(f"Ostale greške:                {summary['other_errors']}")
    print("=" * 80)


def print_failed_items(results):
    failed_items = [r for r in results if r.get("success") is False]

    if not failed_items:
        print("\nNema neuspešnih stavki. Sve je obrađeno.")
        return

    print("\n" + "=" * 80)
    print("NEUSPEŠNO / ZA RUČNO SKIDANJE")
    print("=" * 80)

    for item in failed_items:
        index = item.get("index", "")
        row = item.get("row", "")
        position = item.get("position", "")
        article_number = item.get("article_number", "")
        raw_value = item.get("raw_value", "")
        source = item.get("source", "")
        error = item.get("error", "")
        manual_note = item.get("manual_note", "")

        print(
            f"{index}. Red {row} | "
            f"Pozicija: {position} | "
            f"Artikal: {article_number} | "
            f"Raw: {raw_value} | "
            f"Izvor: {source} | "
            f"Greška: {error}"
        )

        if manual_note:
            print(f"   Napomena: {manual_note}")

    print("=" * 80)


def save_log(results, summary):
    log_dir = Path(OUTPUT_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / "download_log.xlsx"

    df_results = pd.DataFrame(results)

    if df_results.empty:
        df_results = pd.DataFrame(columns=[
            "index",
            "row",
            "position",
            "article_number",
            "raw_value",
            "source",
            "all_positions",
            "group_folder",
            "success",
            "cached",
            "merged",
            "file",
            "error",
            "manual_note"
        ])

    if "error" in df_results.columns:
        df_results["manual_note"] = df_results["error"].apply(explain_error)
    else:
        df_results["manual_note"] = ""

    if "success" in df_results.columns:
        df_failed = df_results[df_results["success"] == False].copy()
    else:
        df_failed = pd.DataFrame()

    if not df_failed.empty:
        wanted_failed_columns = [
            "index",
            "row",
            "position",
            "article_number",
            "raw_value",
            "source",
            "error",
            "manual_note",
            "group_folder",
            "file"
        ]

        existing_columns = [c for c in wanted_failed_columns if c in df_failed.columns]
        df_failed = df_failed[existing_columns]
    else:
        df_failed = pd.DataFrame(columns=[
            "index",
            "row",
            "position",
            "article_number",
            "raw_value",
            "source",
            "error",
            "manual_note",
            "group_folder",
            "file"
        ])

    df_summary = pd.DataFrame([
        {"Metric": "Ukupno zadataka", "Value": summary["total_tasks"]},
        {"Metric": "Uspešno obrađeno", "Value": summary["successful"]},
        {"Metric": "Novo skinuto", "Value": summary["downloaded_new"]},
        {"Metric": "Cache / spojeno", "Value": summary["cached_or_merged"]},
        {"Metric": "Merged fajlova", "Value": summary["merged"]},
        {"Metric": "Neuspešno", "Value": summary["failed"]},
        {"Metric": "Nema Rexel Produktdatenblatt", "Value": summary["datasheet_not_found"]},
        {"Metric": "Link nije pravi PDF", "Value": summary["downloaded_file_not_pdf"]},
        {"Metric": "Proizvod nije nađen", "Value": summary["product_not_found"]},
        {"Metric": "Würth nema katalog PDF", "Value": summary["wurth_catalog_not_found"]},
        {"Metric": "Würth nije elektro oprema", "Value": summary["wurth_not_electrical"]},
        {"Metric": "HTTP greške", "Value": summary["http_errors"]},
        {"Metric": "Ostale greške", "Value": summary["other_errors"]},
    ])

    with pd.ExcelWriter(log_path, engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="Summary", index=False)
        df_results.to_excel(writer, sheet_name="Details", index=False)
        df_failed.to_excel(writer, sheet_name="Failed", index=False)

    print(f"\nLog sačuvan: {log_path}")

    if not df_failed.empty:
        print(f"Neuspešnih za ručno skidanje: {len(df_failed)}")
        print("Pogledaj tab 'Failed' u download_log.xlsx")


def main():
    excel_path = Path(EXCEL_FILE)

    if not excel_path.exists():
        print(f"Excel fajl nije pronađen: {excel_path}")
        return

    tasks = parse_excel(
        file_path=excel_path,
        column=COLUMN,
        start_position=START_POSITION,
        end_position=END_POSITION
    )

    print("=" * 80)
    print(f"Excel: {EXCEL_FILE}")
    print(f"Kolona: {COLUMN}")
    print(f"Opseg pozicija: {START_POSITION} - {END_POSITION}")
    print(f"Pronađeno zadataka: {len(tasks)}")
    print("=" * 80)

    if not tasks:
        print("Nema zadataka za dati opseg.")
        return

    results = []

    downloader = RexelDownloader(
        output_root=OUTPUT_DIR,
        headless=HEADLESS
    )

    try:
        downloader.start()

        for index, task in enumerate(tasks, start=1):
            position = task["position"]
            article_number = task["article_number"]
            raw_value = task.get("raw_value", "")
            row = task["row"]

            print("\n" + "=" * 80)
            print(f"[{index}/{len(tasks)}] Red {row}")
            print(f"Pozicija: {position}")
            print(f"Artikal: {article_number}")
            if raw_value and raw_value != article_number:
                print(f"Raw Excel vrednost: {raw_value}")
            print("=" * 80)

            try:
                result = downloader.download_datasheet(
                    article_number=article_number,
                    position=position
                )

                result["row"] = row
                result["index"] = index
                result["raw_value"] = raw_value
                result["manual_note"] = explain_error(result.get("error", ""))

                results.append(result)

            except Exception as e:
                print(f"[ERROR] {position} / {article_number}: {e}")

                results.append({
                    "success": False,
                    "position": position,
                    "article_number": article_number,
                    "raw_value": raw_value,
                    "row": row,
                    "index": index,
                    "source": "",
                    "all_positions": position,
                    "group_folder": "",
                    "file": "",
                    "cached": False,
                    "merged": False,
                    "error": str(e),
                    "manual_note": explain_error(str(e))
                })

    finally:
        downloader.stop()

    summary = build_summary(results)
    print_summary(summary)
    print_failed_items(results)
    save_log(results, summary)

    print("\nZAVRŠENO.")


if __name__ == "__main__":
    main()
import sys
import json
import csv

from app.services.enrichment import enrich_company
from app.utils.logger import setup_logger

setup_logger()


def process_single(domain: str) -> dict:
    # run the full pipeline for one domain
    result = enrich_company(domain)

    # keep console output readable
    if "company" in result and "raw_summary" in result["company"]:
        result["company"].pop("raw_summary")

    return result


def process_csv(file_path: str) -> list[dict]:
    results = []

    # read domains from first column
    with open(file_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)

        for row in reader:
            if not row:
                continue

            domain = row[0].strip()
            if not domain:
                continue

            # small progress hint for batch runs
            print(f"Processing {domain}...")

            result = process_single(domain)
            results.append(result)

    return results


def main():
    # basic CLI input handling
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m app.main <domain>")
        print("  python -m app.main <file.csv>")
        return

    input_value = sys.argv[1].strip()

    # batch mode if a csv is passed in
    if input_value.endswith(".csv"):
        results = process_csv(input_value)
        print(json.dumps(results, indent=2))
        return

    # otherwise just process one domain
    result = process_single(input_value)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
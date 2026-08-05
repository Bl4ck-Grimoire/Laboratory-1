"""
main.py

Entry point for the retail analytics ETL pipeline. Runs the full flow
in order:

    1. Extract   -> raw sales sources (CSV, JSON, XML) + reference tables
    2. Profile   -> data quality summary on the combined raw transactions
    3. Clean     -> harmonization + rejection of invalid rows
    4. Integrate -> join with reference tables + derived columns
    5. Validate  -> final quality gate before loading
    6. Load      -> data/processed/integrated_sales.csv + SQLite database

Every stage logs a start/end message and a row count to logs/log_file.txt.
If the validation stage fails on a critical check, the pipeline stops
before loading and records the reason in the log.

Run from the project root with:
    python src/main.py
"""

import os
import sys
import json

sys.path.append(os.path.dirname(__file__))

from log import log_progress
from extract import (
    extract_all_sales,
    extract_products,
    extract_stores,
    extract_promotions,
    extract_monthly_targets,
)
from transform import (
    combine_sales,
    profile_sales,
    clean_sales,
    integrate_sales,
    validate_sales,
)
from load import create_database_connection, load_to_csv, load_to_db


# --------------------------------------------------------------------
# Project paths (relative to the project root, resolved from this file
# so the pipeline runs the same regardless of the current working
# directory).
# --------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_PATH = os.path.join(PROJECT_ROOT, 'data', 'raw')
PROCESSED_PATH = os.path.join(PROJECT_ROOT, 'data', 'processed')
OUTPUT_CSV = os.path.join(PROCESSED_PATH, 'integrated_sales.csv')
REJECTED_CSV = os.path.join(PROCESSED_PATH, 'rejected_sales.csv')
DB_PATH = os.path.join(PROJECT_ROOT, 'database')
DB_NAME = 'retail_analytics.db'
TABLE_NAME = 'sales_analytics'
LOG_FILE = os.path.join(PROJECT_ROOT, 'logs', 'log_file.txt')
PROFILE_JSON = os.path.join(PROCESSED_PATH, 'profiling_summary.json')


def main():
    log_progress("ETL Job Started", LOG_FILE)

    # ------------------------------------------------------------------
    # 1) EXTRACT
    # ------------------------------------------------------------------
    log_progress("Extract phase Started", LOG_FILE)

    sales_extracts = extract_all_sales(RAW_PATH)
    for name, df in sales_extracts.items():
        log_progress(f"Extracted {len(df)} rows from {name} source.", LOG_FILE)

    products_df = extract_products(os.path.join(RAW_PATH, 'products.csv'))
    stores_df = extract_stores(os.path.join(RAW_PATH, 'stores.csv'))
    promotions_df = extract_promotions(os.path.join(RAW_PATH, 'promotions.csv'))
    targets_df = extract_monthly_targets(os.path.join(RAW_PATH, 'monthly_targets.csv'))
    log_progress(
        f"Extracted reference tables: {len(products_df)} products, "
        f"{len(stores_df)} stores, {len(promotions_df)} promotions, "
        f"{len(targets_df)} monthly targets.",
        LOG_FILE
    )

    combined_df = combine_sales(sales_extracts['cali'], sales_extracts['bogota'], sales_extracts['medellin'])
    log_progress(f"Combined raw transactions: {len(combined_df)} rows.", LOG_FILE)
    log_progress("Extract phase Ended", LOG_FILE)

    # ------------------------------------------------------------------
    # 2) PROFILE
    # ------------------------------------------------------------------
    log_progress("Profiling phase Started", LOG_FILE)
    profile = profile_sales(combined_df)

    os.makedirs(PROCESSED_PATH, exist_ok=True)
    with open(PROFILE_JSON, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    log_progress(
        f"Profiling complete: {profile['row_count']} rows, "
        f"{profile['duplicate_sale_line_id_count']} duplicate sale_line_id, "
        f"{profile['invalid_quantity_zero_or_negative']} invalid quantities, "
        f"{profile['invalid_price_zero_or_negative']} invalid prices, "
        f"{profile['invalid_date_count']} invalid dates.",
        LOG_FILE
    )
    log_progress("Profiling phase Ended", LOG_FILE)

    # ------------------------------------------------------------------
    # 3) CLEAN
    # ------------------------------------------------------------------
    log_progress("Cleaning phase Started", LOG_FILE)
    clean_df, rejected_df, rejection_summary = clean_sales(combined_df)

    if len(rejected_df) > 0:
        load_to_csv(rejected_df, REJECTED_CSV)

    log_progress(
        f"Cleaning complete: {rejection_summary['total_kept']} rows kept, "
        f"{rejection_summary['total_rejected']} rows rejected "
        f"(invalid_date={rejection_summary['invalid_date']}, "
        f"invalid_quantity={rejection_summary['invalid_quantity']}, "
        f"invalid_unit_price={rejection_summary['invalid_unit_price']}, "
        f"duplicate_sale_line_id={rejection_summary['duplicate_sale_line_id']}).",
        LOG_FILE
    )
    log_progress("Cleaning phase Ended", LOG_FILE)

    if len(clean_df) == 0:
        log_progress("CRITICAL FAILURE: no valid rows remained after cleaning. Stopping pipeline.", LOG_FILE, level="ERROR")
        log_progress("ETL Job Failed", LOG_FILE, level="ERROR")
        return

    # ------------------------------------------------------------------
    # 4) TRANSFORM & INTEGRATE
    # ------------------------------------------------------------------
    log_progress("Transform phase Started", LOG_FILE)
    integrated_df = integrate_sales(clean_df, products_df, stores_df, promotions_df, targets_df)
    log_progress(f"Integration complete: {len(integrated_df)} rows with reference data joined.", LOG_FILE)
    log_progress("Transform phase Ended", LOG_FILE)

    # ------------------------------------------------------------------
    # 5) VALIDATE
    # ------------------------------------------------------------------
    log_progress("Validation phase Started", LOG_FILE)
    validation = validate_sales(integrated_df, products_df, stores_df)

    if not validation['passed']:
        log_progress(
            f"CRITICAL FAILURE: validation failed on: {validation['failed_checks']}. "
            f"Stopping pipeline before loading.",
            LOG_FILE, level="ERROR"
        )
        log_progress("ETL Job Failed", LOG_FILE, level="ERROR")
        return

    log_progress("Validation passed on all critical checks.", LOG_FILE)
    log_progress("Validation phase Ended", LOG_FILE)

    # ------------------------------------------------------------------
    # 6) LOAD
    # ------------------------------------------------------------------
    log_progress("Load phase Started", LOG_FILE)

    csv_ok = load_to_csv(integrated_df, OUTPUT_CSV)
    if csv_ok:
        log_progress(f"Data successfully written to {OUTPUT_CSV} ({len(integrated_df)} rows).", LOG_FILE)
    else:
        log_progress("CRITICAL FAILURE: could not write integrated_sales.csv.", LOG_FILE, level="ERROR")
        log_progress("ETL Job Failed", LOG_FILE, level="ERROR")
        return

    sql_connection = create_database_connection(DB_PATH, DB_NAME)
    if sql_connection is None:
        log_progress("CRITICAL FAILURE: could not connect to SQLite database.", LOG_FILE, level="ERROR")
        log_progress("ETL Job Failed", LOG_FILE, level="ERROR")
        return

    db_ok = load_to_db(integrated_df, sql_connection, TABLE_NAME)
    if db_ok:
        log_progress(
            f"Data successfully loaded into '{TABLE_NAME}' table in {DB_NAME} ({len(integrated_df)} rows).",
            LOG_FILE
        )
    else:
        log_progress("CRITICAL FAILURE: could not load data into SQLite database.", LOG_FILE, level="ERROR")
        log_progress("ETL Job Failed", LOG_FILE, level="ERROR")
        sql_connection.close()
        return

    sql_connection.close()
    log_progress("Load phase Ended", LOG_FILE)
    log_progress("ETL Job Completed Successfully", LOG_FILE)


if __name__ == "__main__":
    main()

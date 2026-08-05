"""
transform.py

Transform block for the retail analytics ETL pipeline. Split into four
stages, matching the workshop instructions:

    1. combine_sales(...)   -> stack the three raw extracts together
    2. profile_sales(...)   -> data quality profiling (read-only, no changes)
    3. clean_sales(...)     -> cleaning & harmonization rules
    4. integrate_sales(...) -> join with reference tables + derived columns
    5. validate_sales(...)  -> final quality gate before loading

Each function does one job, so the profiling numbers you see are always
about the data right before the cleaning step that responds to them.
"""

import pandas as pd
import numpy as np


# --------------------------------------------------------------------
# 1) Combine raw extracts
# --------------------------------------------------------------------

def combine_sales(cali_df, bogota_df, medellin_df):
    """
    Stack the three already-structurally-aligned extracts into a single
    DataFrame. No cleaning happens here -- this is still a purely
    structural step (same as concatenating extract_from_csv/xml/json in
    the reference pipeline).
    """
    combined = pd.concat([cali_df, bogota_df, medellin_df], ignore_index=True)
    return combined


# --------------------------------------------------------------------
# 2) Profiling
# --------------------------------------------------------------------

def profile_sales(df):
    """
    Build a compact profiling summary of the combined (but still raw)
    transaction data. This function only reads the data -- it never
    modifies df or drops rows.

    Returns
    -------
    dict : profiling summary, structured so it can be dropped straight
    into the README or printed to the log.
    """
    profile = {}

    profile['row_count'] = len(df)
    profile['columns_and_dtypes'] = {col: str(dtype) for col, dtype in df.dtypes.items()}
    profile['missing_values'] = df.isnull().sum().to_dict()

    # Duplicate sale_line_id
    profile['duplicate_sale_line_id_count'] = int(df['sale_line_id'].duplicated().sum())

    # Invalid quantities: not numeric, or numeric but <= 0
    qty_numeric = pd.to_numeric(df['quantity'], errors='coerce')
    profile['invalid_quantity_non_numeric'] = int(qty_numeric.isnull().sum() - df['quantity'].isnull().sum())
    profile['invalid_quantity_zero_or_negative'] = int((qty_numeric <= 0).sum())

    # Invalid prices: not numeric, or numeric but <= 0
    # (price sometimes arrives as "$220000" or a negative number, see raw sources)
    price_numeric = pd.to_numeric(
        df['unit_price'].astype(str).str.replace('$', '', regex=False).str.strip(),
        errors='coerce'
    )
    profile['invalid_price_non_numeric'] = int(price_numeric.isnull().sum() - df['unit_price'].isnull().sum())
    profile['invalid_price_zero_or_negative'] = int((price_numeric <= 0).sum())

    # Invalid dates: cannot be parsed under any of the 3 known formats
    profile['invalid_date_count'] = int(_count_unparseable_dates(df['sale_date']))

    # Distinct values for selected categorical fields (raw, before cleaning --
    # this is what justifies the casing/whitespace/missing-marker rules
    # applied in clean_sales)
    profile['distinct_store_id_raw'] = sorted(df['store_id'].dropna().unique().tolist())
    profile['distinct_payment_method_raw'] = sorted(df['payment_method'].dropna().unique().tolist())
    profile['distinct_product_id_raw'] = sorted(df['product_id'].dropna().unique().tolist())
    profile['distinct_promotion_code_raw'] = sorted(df['promotion_code'].dropna().unique().tolist())
    profile['distinct_source_system'] = sorted(df['source_system'].dropna().unique().tolist())

    return profile


def _count_unparseable_dates(date_series):
    """
    Try to parse each date string using the three known source formats
    (ISO from Cali, DD/MM/YYYY from Bogotá, MM-DD-YYYY from Medellín).
    A value is "unparseable" if none of the three formats work.
    """
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m-%d-%Y']
    unparseable = 0
    for value in date_series:
        if pd.isnull(value):
            unparseable += 1
            continue
        parsed_ok = False
        for fmt in formats:
            try:
                pd.to_datetime(value, format=fmt)
                parsed_ok = True
                break
            except (ValueError, TypeError):
                continue
        if not parsed_ok:
            unparseable += 1
    return unparseable


# --------------------------------------------------------------------
# 3) Cleaning & harmonization
# --------------------------------------------------------------------

def _parse_multi_format_date(value):
    """Parse a single date string trying the three known source formats."""
    if pd.isnull(value):
        return pd.NaT
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m-%d-%Y']
    for fmt in formats:
        try:
            return pd.to_datetime(value, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.NaT


def clean_sales(df):
    """
    Apply cleaning rules justified by profile_sales() findings:

    - Standardize column names (already common schema) and ID values
      (uppercase, trimmed) so joins with reference tables do not fail
      on casing/whitespace mismatches.
    - Trim whitespace and standardize casing on text fields
      (payment_method had entries like ' card ' mixed with 'Card').
    - Parse the three different date formats into a single date dtype.
    - Convert quantity and unit_price to numeric (unit_price sometimes
      arrives as "$220000").
    - Remove duplicated sale_line_id, keeping the first valid occurrence.
    - Reject rows with unparseable dates, quantity <= 0, or unit_price <= 0.
    - Represent missing promotion codes consistently (NaN -> "NONE").

    Returns
    -------
    (clean_df, rejected_df, rejection_summary)
    """
    working = df.copy()

    # --- Standardize IDs and text fields --------------------------------
    working['sale_line_id'] = working['sale_line_id'].astype(str).str.strip().str.upper()
    working['store_id'] = working['store_id'].astype(str).str.strip().str.upper()
    working['product_id'] = working['product_id'].astype(str).str.strip().str.upper()
    working['payment_method'] = (
        working['payment_method'].astype(str).str.strip().str.title()
    )
    working['payment_method'] = working['payment_method'].replace({'Nan': np.nan})

    # --- Promotion code: consistent missing representation --------------
    # Missing promotions show up in several disguises across sources:
    #   - an actual NaN (CSV/JSON empty field)
    #   - the literal string "None" (XML <promo_code /> empty element,
    #     read by ElementTree as None, then stringified by astype(str))
    #   - the literal string "N/A" (found in the Medellín XML extract)
    # All of these must collapse to the same "NONE" marker so promotion
    # joins and reporting treat "no promotion" consistently.
    working['promotion_code'] = working['promotion_code'].astype(str).str.strip().str.upper()
    working['promotion_code'] = working['promotion_code'].replace(
        {'NAN': 'NONE', 'NONE': 'NONE', 'N/A': 'NONE', 'NA': 'NONE', '': 'NONE'}
    )
    working['promotion_code'] = working['promotion_code'].fillna('NONE')

    # --- Parse dates ------------------------------------------------------
    working['sale_date'] = working['sale_date'].apply(_parse_multi_format_date)

    # --- Numeric conversion ------------------------------------------------
    working['quantity'] = pd.to_numeric(working['quantity'], errors='coerce')
    working['unit_price'] = pd.to_numeric(
        working['unit_price'].astype(str).str.replace('$', '', regex=False).str.strip(),
        errors='coerce'
    )

    rejected_frames = []

    # --- Reject invalid dates ----------------------------------------------
    invalid_date_mask = working['sale_date'].isnull()
    rejected_frames.append(_tag_rejection(working[invalid_date_mask], 'invalid_date'))
    working = working[~invalid_date_mask]

    # --- Reject quantity <= 0 or missing -----------------------------------
    invalid_qty_mask = working['quantity'].isnull() | (working['quantity'] <= 0)
    rejected_frames.append(_tag_rejection(working[invalid_qty_mask], 'invalid_quantity'))
    working = working[~invalid_qty_mask]

    # --- Reject unit_price <= 0 or missing ----------------------------------
    invalid_price_mask = working['unit_price'].isnull() | (working['unit_price'] <= 0)
    rejected_frames.append(_tag_rejection(working[invalid_price_mask], 'invalid_unit_price'))
    working = working[~invalid_price_mask]

    # --- Remove duplicated sale_line_id, keep first valid occurrence --------
    dup_mask = working['sale_line_id'].duplicated(keep='first')
    rejected_frames.append(_tag_rejection(working[dup_mask], 'duplicate_sale_line_id'))
    working = working[~dup_mask]

    rejected_df = pd.concat(rejected_frames, ignore_index=True) if rejected_frames else pd.DataFrame()

    rejection_summary = {
        'invalid_date': int(invalid_date_mask.sum()),
        'invalid_quantity': int(invalid_qty_mask.sum()),
        'invalid_unit_price': int(invalid_price_mask.sum()),
        'duplicate_sale_line_id': int(dup_mask.sum()),
        'total_rejected': len(rejected_df),
        'total_kept': len(working),
    }

    working = working.reset_index(drop=True)
    return working, rejected_df, rejection_summary


def _tag_rejection(df, reason):
    tagged = df.copy()
    tagged['rejection_reason'] = reason
    return tagged


# --------------------------------------------------------------------
# 4) Transformation & integration with reference tables
# --------------------------------------------------------------------

def integrate_sales(clean_df, products_df, stores_df, promotions_df, targets_df):
    """
    Join cleaned transactions with the reference tables and compute the
    derived business columns required by the selected business
    requirements (Lab 1A, points 4 and 6):

        product_name, category            <- products.csv
        store_name, city, region          <- stores.csv
        discount_pct, campaign_name       <- promotions.csv (by promotion_code)
        gross_sales = quantity * unit_price
        discount_amount = gross_sales * discount_pct
        net_sales = gross_sales - discount_amount
        month, week, day_name             <- from sale_date
        sales_target                      <- monthly_targets.csv (by store_id + month)
    """
    df = clean_df.copy()

    # --- Product master ---------------------------------------------------
    products = products_df.copy()
    products['product_id'] = products['product_id'].astype(str).str.strip().str.upper()
    df = df.merge(
        products[['product_id', 'product_name', 'category']],
        on='product_id', how='left'
    )

    # --- Store master --------------------------------------------------
    stores = stores_df.copy()
    stores['store_id'] = stores['store_id'].astype(str).str.strip().str.upper()
    df = df.merge(
        stores[['store_id', 'store_name', 'city', 'region']],
        on='store_id', how='left'
    )

    # --- Promotions (only discount_pct and campaign_name are needed) ----
    promos = promotions_df.copy()
    promos['promotion_code'] = promos['promotion_code'].astype(str).str.strip().str.upper()
    promos = promos[['promotion_code', 'discount_pct', 'campaign_name']].drop_duplicates('promotion_code')
    df = df.merge(promos, on='promotion_code', how='left')
    df['discount_pct'] = df['discount_pct'].fillna(0.0)
    df['campaign_name'] = df['campaign_name'].fillna('No Campaign')

    # --- Derived sales metrics ----------------------------------------
    df['gross_sales'] = df['quantity'] * df['unit_price']
    df['discount_amount'] = df['gross_sales'] * df['discount_pct']
    df['net_sales'] = df['gross_sales'] - df['discount_amount']

    # --- Date-derived fields --------------------------------------------
    df['month'] = df['sale_date'].dt.strftime('%Y-%m')
    df['week'] = df['sale_date'].dt.isocalendar().week.astype(int)
    df['day_name'] = df['sale_date'].dt.day_name()

    # --- Monthly sales target -------------------------------------------
    targets = targets_df.copy()
    targets['store_id'] = targets['store_id'].astype(str).str.strip().str.upper()
    targets = targets.rename(columns={'month': 'month'})
    df = df.merge(
        targets[['store_id', 'month', 'sales_target']],
        on=['store_id', 'month'], how='left'
    )

    return df


# --------------------------------------------------------------------
# 5) Validation (final quality gate before loading)
# --------------------------------------------------------------------

def validate_sales(df, products_df, stores_df):
    """
    Run the final validation checks before loading. Returns a dict with
    a boolean 'passed' flag plus the detail of every check, so main.py
    can decide whether to stop the pipeline and what to write to the log.

    Checks:
        - sale_line_id is unique
        - required identifiers and dates are not null
        - quantity, unit_price, gross_sales, net_sales are positive
        - every product matches the product master
        - every store matches the store master
        - net_sales == gross_sales - discount_amount
        - (extra) discount_pct is within [0, 1]
        - (extra) sale_date is not in the future relative to today
    """
    results = {}
    valid_products = set(products_df['product_id'].astype(str).str.strip().str.upper())
    valid_stores = set(stores_df['store_id'].astype(str).str.strip().str.upper())

    results['unique_sale_line_id'] = bool(not df['sale_line_id'].duplicated().any())

    required_cols = ['sale_line_id', 'store_id', 'product_id', 'sale_date']
    results['required_fields_not_null'] = bool(df[required_cols].notnull().all().all())

    results['quantity_positive'] = bool((df['quantity'] > 0).all())
    results['unit_price_positive'] = bool((df['unit_price'] > 0).all())
    results['gross_sales_positive'] = bool((df['gross_sales'] > 0).all())
    results['net_sales_positive'] = bool((df['net_sales'] > 0).all())

    results['products_match_master'] = bool(df['product_id'].isin(valid_products).all())
    results['stores_match_master'] = bool(df['store_id'].isin(valid_stores).all())

    recomputed_net = df['gross_sales'] - df['discount_amount']
    results['net_sales_formula_consistent'] = bool(np.isclose(df['net_sales'], recomputed_net, atol=0.01).all())

    # Extra checks
    results['discount_pct_in_range'] = bool(df['discount_pct'].between(0, 1).all())
    results['sale_date_not_in_future'] = bool((df['sale_date'] <= pd.Timestamp.now()).all())

    critical_checks = [
        'unique_sale_line_id', 'required_fields_not_null',
        'quantity_positive', 'unit_price_positive',
        'gross_sales_positive', 'net_sales_positive',
        'products_match_master', 'stores_match_master',
        'net_sales_formula_consistent',
    ]
    results['passed'] = all(results[check] for check in critical_checks)
    results['failed_checks'] = [check for check in critical_checks if not results[check]]

    return results

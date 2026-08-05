"""
extract.py

Extraction block for the retail analytics ETL pipeline.

Responsibility of this module ONLY:
    - Read each raw transaction source (CSV, JSON, XML) and expose it as a
      pandas DataFrame with a common technical schema.
    - Read the reference/master tables (products, stores, promotions,
      monthly targets) as-is.

This module must NOT perform cleaning, validation, or business
transformations (no renaming for business meaning, no filtering of
"invalid" rows, no numeric coercion beyond what is needed to read the
file). Those responsibilities belong to transform.py. The only
"standardization" done here is structural: making every transaction
source line up under the same column names so later stages can treat
them uniformly.
"""

import os
import json
import pandas as pd
import xml.etree.ElementTree as ET

# Common technical schema every transaction source is mapped into.
# This mirrors the field list agreed on with the client (Lab 1A, point 6).
SALES_COLUMNS = [
    'sale_line_id',
    'sale_date',
    'store_id',
    'product_id',
    'quantity',
    'unit_price',
    'promotion_code',
    'payment_method',
]


def extract_sales_cali(path):
    """
    Extract the Cali transactions, delivered as a CSV file with the
    common field names already in English.

    Parameters
    ----------
    path : str
        Path to the CSV file (e.g. data/raw/sales_cali.csv)

    Returns
    -------
    pd.DataFrame with SALES_COLUMNS plus a 'source_store' technical tag.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=SALES_COLUMNS + ['source_system'])

    df = pd.read_csv(path, dtype=str)
    df = df.reindex(columns=SALES_COLUMNS)
    df['source_system'] = 'sales_cali.csv'
    return df


def extract_sales_bogota(path):
    """
    Extract the Bogotá transactions, delivered as a JSON file (a plain
    JSON array of objects, not JSON Lines) with field names in Spanish.

    Only the field names are mapped to the common schema here -- this is
    a structural rename, not a business transformation. Values are kept
    as-is (as strings) so cleaning decisions stay in transform.py.

    Parameters
    ----------
    path : str
        Path to the JSON file (e.g. data/raw/sales_bogota.json)

    Returns
    -------
    pd.DataFrame with SALES_COLUMNS plus a 'source_system' technical tag.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=SALES_COLUMNS + ['source_system'])

    with open(path, 'r', encoding='utf-8') as f:
        raw_records = json.load(f)

    field_map = {
        'id_linea': 'sale_line_id',
        'fecha': 'sale_date',
        'sucursal': 'store_id',
        'codigo_producto': 'product_id',
        'unidades': 'quantity',
        'precio': 'unit_price',
        'promocion': 'promotion_code',
        'medio_pago': 'payment_method',
    }

    records = []
    for row in raw_records:
        mapped = {field_map[k]: v for k, v in row.items() if k in field_map}
        records.append(mapped)

    df = pd.DataFrame(records, dtype=str) if records else pd.DataFrame(columns=SALES_COLUMNS)
    df = df.reindex(columns=SALES_COLUMNS)
    df['source_system'] = 'sales_bogota.json'
    return df


def extract_sales_medellin(path):
    """
    Extract the Medellín transactions, delivered as an XML file with a
    <sales><sale>...</sale></sales> structure and its own tag names.

    Parameters
    ----------
    path : str
        Path to the XML file (e.g. data/raw/sales_medellin.xml)

    Returns
    -------
    pd.DataFrame with SALES_COLUMNS plus a 'source_system' technical tag.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=SALES_COLUMNS + ['source_system'])

    tree = ET.parse(path)
    root = tree.getroot()

    field_map = {
        'line_id': 'sale_line_id',
        'date': 'sale_date',
        'branch_code': 'store_id',
        'sku': 'product_id',
        'units': 'quantity',
        'unit_value': 'unit_price',
        'promo_code': 'promotion_code',
        'payment': 'payment_method',
    }

    records = []
    for sale in root.findall('sale'):
        row = {}
        for tag, target_col in field_map.items():
            node = sale.find(tag)
            row[target_col] = node.text if node is not None else None
        records.append(row)

    df = pd.DataFrame(records, dtype=str) if records else pd.DataFrame(columns=SALES_COLUMNS)
    df = df.reindex(columns=SALES_COLUMNS)
    df['source_system'] = 'sales_medellin.xml'
    return df


def extract_all_sales(raw_path):
    """
    Convenience wrapper that runs the three transaction extractors and
    returns each DataFrame separately (concatenation is a transform-stage
    decision, not an extraction one -- but combining raw, unmodified
    extracts is still purely structural, so main.py may choose to
    concatenate right after this call).

    Parameters
    ----------
    raw_path : str
        Directory holding the raw source files
        (sales_cali.csv, sales_bogota.json, sales_medellin.xml).

    Returns
    -------
    dict with keys 'cali', 'bogota', 'medellin' -> DataFrame
    """
    return {
        'cali': extract_sales_cali(os.path.join(raw_path, 'sales_cali.csv')),
        'bogota': extract_sales_bogota(os.path.join(raw_path, 'sales_bogota.json')),
        'medellin': extract_sales_medellin(os.path.join(raw_path, 'sales_medellin.xml')),
    }


# --------------------------------------------------------------------
# Reference / master tables
# --------------------------------------------------------------------

def extract_products(path):
    """Read the product master table as-is (no transformation)."""
    return pd.read_csv(path)


def extract_stores(path):
    """Read the store master table as-is (no transformation)."""
    return pd.read_csv(path)


def extract_promotions(path):
    """Read the promotions table as-is (no transformation)."""
    return pd.read_csv(path)


def extract_monthly_targets(path):
    """Read the monthly sales targets table as-is (no transformation)."""
    return pd.read_csv(path)

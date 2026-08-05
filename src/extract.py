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
    if not os.path.exists(path):
        return pd.DataFrame(columns=SALES_COLUMNS + ['source_system'])

    df = pd.read_csv(path, dtype=str)
    df = df.reindex(columns=SALES_COLUMNS)
    df['source_system'] = 'sales_cali.csv'
    return df


def extract_sales_bogota(path):
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
    return {
        'cali': extract_sales_cali(os.path.join(raw_path, 'sales_cali.csv')),
        'bogota': extract_sales_bogota(os.path.join(raw_path, 'sales_bogota.json')),
        'medellin': extract_sales_medellin(os.path.join(raw_path, 'sales_medellin.xml')),
    }


# Reference / tables


def extract_products(path):
    #Read the products table
    return pd.read_csv(path)


def extract_stores(path):
    #Read the stores table
    return pd.read_csv(path)


def extract_promotions(path):
    #Read the promotions table
    return pd.read_csv(path)


def extract_monthly_targets(path):
    #Read the monthly sales targets table
    return pd.read_csv(path)

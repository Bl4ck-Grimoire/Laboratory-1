# Lab 1B – ETL: Retail Analytics Platform

`Johann Eduardo Gonzalez Sandoval`
`Juan David Lasso Chaparro`

This project implements the ETL pipeline that turns the raw, multi-format
sales data into a single analytical dataset and SQLite database that 
a retail dashboard could query directly.

It follows the standard Extract → Profile → Clean → Transform → Validate → Load.

---

## 1. Project structure

```
Lab1B_ETL/
├── data/
│   ├── raw/           # Source files exactly as delivered by the client
│   ├── processed/      # Pipeline outputs (CSV, profiling summary, rejected rows)
│   └── output/         # Reserved for further downstream exports
│
├── database/
│   └── retail_analytics.db   # SQLite analytical database
│
├── src/
│   ├── extract.py      # Extraction block
│   ├── transform.py     # Profiling, cleaning, integration, validation
│   ├── load.py          # CSV + SQLite loading
│   ├── queries.py       # Analytical query menu
│   ├── log.py           # Logging utility
│   └── main.py           # Pipeline orchestrator (entry point)
│
├── logs/
│   └── log_file.txt      # Execution log
│
├── docs/
│   └── pipeline_diagram.png
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 2. Data sources

| File | Format | Origin | Notes |
|---|---|---|---|
| `sales_cali.csv` | CSV | Cali store (S01) | Field names already match the common schema |
| `sales_bogota.json` | JSON (array of objects) | Bogotá store (S02) | Field names in Spanish |
| `sales_medellin.xml` | XML | Medellín store (S03) | Own tag names, different date format |
| `products.csv` | CSV | Product master | product_id, product_name, category, list_price, unit_cost |
| `stores.csv` | CSV | Store master | store_id, store_name, city, region |
| `promotions.csv` | CSV | Promotions | promotion_code, product_id, start_date, end_date, discount_pct, campaign_name |
| `monthly_targets.csv` | CSV | Sales planning | store_id, month, sales_target |

All three transaction sources are mapped to the same common technical
schema before anything else happens to them:

`sale_line_id, sale_date, store_id, product_id, quantity, unit_price, promotion_code, payment_method`

---

## 3. Extraction

`src/extract.py` contains one function per transaction format
(`extract_sales_cali`, `extract_sales_bogota`, `extract_sales_medellin`)
plus one function per reference table. Each transaction extractor only
renames fields into the common schema — it does not clean, validate, or
calculate anything. Values are kept as raw strings so that every cleaning
decision stays visible and traceable in the transform stage.

---

## 4. Data profiling — findings and derived cleaning decisions

This is the output of `profile_sales()`, run on the 763 raw rows
resulting from combining the three transaction sources (241 + 281 + 241),
before any cleaning. The full machine-readable version is written to
`data/processed/profiling_summary.json` on every run.

| # | Profiling finding | Value found | Cleaning decision derived from it |
|---|---|---|---|
| 1 | Row count / columns / dtypes | 763 rows, 9 columns, all read as `str` | Confirms numeric fields (`quantity`, `unit_price`) must be explicitly converted with `pd.to_numeric`, since every source was extracted as text to avoid silent type coercion during extraction. |
| 2 | Duplicate `sale_line_id` | 3 duplicates | Rule: **remove duplicated `sale_line_id`, keeping the first valid occurrence** — a repeated ID cannot represent two different transaction lines. |
| 3 | Invalid quantities (`quantity <= 0`) | 2 rows (one `0`, one `-1`) | Rule: **reject rows where `quantity <= 0`** — a sale cannot have zero or negative units sold; this is not something to impute, it signals a corrupted record. |
| 4 | Invalid prices (`unit_price <= 0`) | 1 row (`-86000`) | Rule: **reject rows where `unit_price <= 0`** — a negative price has no valid business meaning and would corrupt every downstream revenue metric. |
| 5 | Unparseable dates | 1 row (empty `sale_date`) | Rule: **reject rows whose date cannot be parsed** under any of the three known source formats — a transaction without a valid date cannot be placed in any trend, monthly, or target comparison. |
| 6 | `unit_price` sometimes arrives as text | 1 value found as `"$220000"` (Bogotá) | Rule: **strip currency symbols and coerce to numeric** before any threshold check, otherwise this row would be misclassified as "non-numeric" instead of a valid price. |
| 7 | Inconsistent `store_id` casing | `s02` found instead of `S02` | Rule: **standardize IDs to trimmed, uppercase strings** before joining with `stores.csv`, or this row would fail to match the store master. |
| 8 | Inconsistent `product_id` formatting | `" P005 "` found with leading/trailing spaces | Rule: **trim whitespace and uppercase `product_id`** before joining with `products.csv`, for the same reason as above. |
| 9 | Inconsistent `payment_method` casing/whitespace | `' card '`, `'CASH'`, `'Card'`, `'Cash'` all present | Rule: **trim whitespace and title-case text fields** so `'Card'`, `'CASH'` and `' card '` are recognized as the same category in any grouping or KPI. |
| 10 | Missing/placeholder promotion codes | Represented three different ways depending on source: empty/`NaN` (CSV, JSON), the literal string `"None"` (XML empty tag), and the literal string `"N/A"` (XML) | Rule: **represent "no promotion" with a single consistent marker (`"NONE"`)** across all sources — otherwise a `GROUP BY promotion_code` or a join with `promotions.csv` would silently split "no promotion" into four different buckets. |

**Rejection outcome:** of the 763 combined rows, 7 were rejected during
cleaning (1 invalid date, 2 invalid quantities, 1 invalid price, 3
duplicate IDs — duplicates are counted after the other filters, so a
row can only be flagged once), leaving **756 valid rows** that move on to
transformation and integration.

Rejected rows are not silently discarded: they are written to
`data/processed/rejected_sales.csv` with a `rejection_reason` column, so
they can be audited later instead of just disappearing from the pipeline.

---

## 5. Cleaning & harmonization rules (summary)

Implemented in `clean_sales()`:

- Standardize `sale_line_id`, `store_id`, `product_id` (trim + uppercase).
- Trim whitespace and title-case `payment_method`.
- Parse `sale_date` under the three known source formats (`YYYY-MM-DD`,
  `DD/MM/YYYY`, `MM-DD-YYYY`) into a single `datetime` type.
- Convert `quantity` and `unit_price` to numeric, stripping currency
  symbols first.
- Remove duplicated `sale_line_id`, keeping the first valid occurrence.
- Reject rows with an unparseable date, `quantity <= 0`, or
  `unit_price <= 0`.
- Represent every missing/placeholder promotion code consistently as
  `"NONE"`.

Every rule above exists because a specific profiling finding required it
— see the table in section 4.

---

## 6. Transformation & integration

Implemented in `integrate_sales()`. Only the fields needed to answer the
business requirements from Lab 1A are added:

| Column | Source | Purpose |
|---|---|---|
| `product_name`, `category` | `products.csv` | Product category performance (Business Q1) |
| `store_name`, `city`, `region` | `stores.csv` | Store/region comparison (Business Q3, Q5) |
| `discount_pct`, `campaign_name` | `promotions.csv` | Promotion effectiveness (Business Q2, Q4) |
| `gross_sales` = `quantity × unit_price` | derived | Base revenue figure |
| `discount_amount` = `gross_sales × discount_pct` | derived | Promotion impact |
| `net_sales` = `gross_sales − discount_amount` | derived | Actual revenue |
| `month`, `week`, `day_name` | from `sale_date` | Trend analysis over time |
| `sales_target` | `monthly_targets.csv` (by `store_id` + `month`) | Target vs. actual (Business Q5) |

---

## 7. Validation (final quality gate before loading)

Implemented in `validate_sales()`. If any **critical** check fails, the
pipeline stops before writing the CSV or the database, and the failure
reason is recorded in the log.

Critical checks:
- `sale_line_id` is unique.
- Required identifiers and dates (`sale_line_id`, `store_id`,
  `product_id`, `sale_date`) are not null.
- `quantity`, `unit_price`, `gross_sales`, `net_sales` are all positive.
- Every `product_id` matches the product master.
- Every `store_id` matches the store master.
- `net_sales` equals `gross_sales − discount_amount` (formula consistency).

Additional checks (not critical, but recorded):
- `discount_pct` is within the valid `[0, 1]` range.
- `sale_date` is not in the future relative to the run date.

---

## 8. Loading

- `data/processed/integrated_sales.csv` — the full integrated dataset.
- `database/retail_analytics.db` — SQLite database, table
  `sales_analytics`, holding the same data.

The database is the analytical output of the pipeline. All downstream
queries (section 9) read from SQLite, never from the raw or processed
files directly.

---

## 9. Analytical queries

`src/queries.py` provides a simple interactive menu, each option tied to
a business question from Lab 1A:

| # | Query | Business question |
|---|---|---|
| 1 | Product category performance | Which product categories are performing well, and which ones are struggling? |
| 2 | Sales by region and store | Which specific stores and regions are underperforming? |
| 3 | Store target achievement | Which stores are hitting the targets, and which aren't? |
| 4 | Promotion effectiveness | Are promotions actually improving sales? |
| 5 | Pricing and discount impact | Which pricing and discount strategies are generating the highest sales lift? |
| 6 | Monthly sales trend | Trend over time, so managers can compare to last month |

---

## 10. Logging

`src/log.py` appends a timestamped, leveled line
(`timestamp,LEVEL,message`) to `logs/log_file.txt` for every stage of the
pipeline, including row counts in and out of each phase and the reason
for any critical failure. The same messages are also printed to the
console while `main.py` runs.

---

## 11. How to run the project

### Requirements

- Python 3.10+
- Install dependencies from the project root:

First open a terminal in the route of your project.
A good practice is to do a virtual enviroment which prevent version conflicts 
between libraries, so in the terminal.

```bash
python -m venv .venv
```

And activate it with

```bash
.venv\Scripts\Activate 
```

If everything went good you should see `"(.venv)"` before the route in your terminal

```bash
pip install -r requirements.txt
```

### Run the full pipeline

From the project root:

```bash
python src/main.py
```

This single command runs Extract → Profile → Clean → Transform
→ Validate → Load in order, and produces:

- `data/processed/integrated_sales.csv`
- `data/processed/profiling_summary.json`
- `data/processed/rejected_sales.csv` (only if any rows were rejected)
- `database/retail_analytics.db`
- `logs/log_file.txt`

### Run the analytical query menu

After `main.py` has run at least once (so the database exists):

```bash
python src/queries.py
```

Select a query number from the menu, or `0` to exit.

---

## 12. Reflection

Building a dashboard is not the first step in a data engineering project
— it is one of the last. Before any chart could be designed, this project
required understanding the business problem, defining objectives and
KPIs, mapping which systems held which data, profiling the raw data to
find its real quality issues, and only then cleaning, integrating, and
validating it. Skipping straight to "build the dashboard" would have
meant building it on top of duplicated transactions, negative prices, and
four different spellings of "no promotion" — numbers that would have
looked fine on screen while being wrong underneath.

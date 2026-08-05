import os
import sqlite3
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'retail_analytics.db')
TABLE_NAME = 'sales_analytics'


QUERIES = {
    '1': {
        'title': "Product category performance",
        'business_question': "Which product categories are performing well, and which ones are struggling? (Lab 1A, section 3)",
        'sql': f"""
            SELECT category,
                   ROUND(SUM(net_sales), 0) AS total_net_sales,
                   SUM(quantity) AS units_sold
            FROM {TABLE_NAME}
            GROUP BY category
            ORDER BY total_net_sales DESC;
        """,
    },
    '2': {
        'title': "Sales by region and store",
        'business_question': "Which specific stores and regions are underperforming? (Lab 1A, section 3)",
        'sql': f"""
            SELECT region, store_name,
                   ROUND(SUM(net_sales), 0) AS total_net_sales
            FROM {TABLE_NAME}
            GROUP BY region, store_name
            ORDER BY total_net_sales ASC;
        """,
    },
    '3': {
        'title': "Store target achievement",
        'business_question': "Which stores are hitting the targets, and which aren't? (Lab 1A, section 3 and 8)",
        'sql': f"""
            SELECT store_name, month,
                   ROUND(SUM(net_sales), 0) AS actual_sales,
                   MAX(sales_target) AS sales_target,
                   ROUND(100.0 * SUM(net_sales) / NULLIF(MAX(sales_target), 0), 1) AS target_achievement_pct
            FROM {TABLE_NAME}
            GROUP BY store_name, month
            ORDER BY store_name, month;
        """,
    },
    '4': {
        'title': "Promotion effectiveness",
        'business_question': "Are promotions actually improving sales? (Lab 1A, section 3)",
        'sql': f"""
            SELECT campaign_name,
                   promotion_code,
                   ROUND(SUM(net_sales), 0) AS total_net_sales,
                   SUM(quantity) AS units_sold
            FROM {TABLE_NAME}
            WHERE promotion_code <> 'NONE'
            GROUP BY campaign_name, promotion_code
            ORDER BY total_net_sales DESC;
        """,
    },
    '5': {
        'title': "Pricing and discount impact",
        'business_question': "Which pricing and discount strategies are generating the highest sales lift? (Lab 1A, section 3)",
        'sql': f"""
            SELECT product_name,
                   ROUND(AVG(discount_pct) * 100, 1) AS avg_discount_pct,
                   ROUND(SUM(discount_amount), 0) AS total_discount_given,
                   ROUND(SUM(net_sales), 0) AS total_net_sales
            FROM {TABLE_NAME}
            WHERE discount_pct > 0
            GROUP BY product_name
            ORDER BY total_net_sales DESC;
        """,
    },
    '6': {
        'title': "Monthly sales trend",
        'business_question': "Trend over time so managers can compare to last month (Lab 1A, transcript + section 4)",
        'sql': f"""
            SELECT month,
                   ROUND(SUM(net_sales), 0) AS total_net_sales
            FROM {TABLE_NAME}
            GROUP BY month
            ORDER BY month;
        """,
    },
}


def run_query(choice, sql_connection):
    query = QUERIES.get(choice)
    if not query:
        print("Invalid option.\n")
        return
    print(f"\n--- {query['title']} ---")
    print(f"Business question: {query['business_question']}\n")
    result = pd.read_sql(query['sql'], sql_connection)
    print(result.to_string(index=False))
    print()


def show_menu():
    print("\n=== Retail Analytics - Query Menu ===")
    for key, query in QUERIES.items():
        print(f"  {key}. {query['title']}")
    print("  0. Exit")


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Run main.py first to build it.")
        return

    sql_connection = sqlite3.connect(DB_PATH)

    while True:
        show_menu()
        choice = input("Select a query: ").strip()
        if choice == '0':
            break
        run_query(choice, sql_connection)

    sql_connection.close()


if __name__ == "__main__":
    main()

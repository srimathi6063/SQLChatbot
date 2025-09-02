import os
import re
import logging
from difflib import get_close_matches
from ibm_watsonx_ai.foundation_models import ModelInference
from mcp_mysql import mysql_query, get_table_schema, get_all_tables_in_db

# Initialize IBM Watsonx AI Model once
class WatsonxClient:
    def __init__(self):
        self.api_key = os.getenv("WATSONX_API_KEY")
        self.model_id = os.getenv("WATSONX_MODEL_ID")
        self.project_id = os.getenv("WATSONX_PROJECT_ID")
        self.credentials = {
            "apikey": self.api_key,
            "url": "https://us-south.ml.cloud.ibm.com"
        }
        self.inference = ModelInference(
            model_id=self.model_id, 
            credentials=self.credentials, 
            project_id=self.project_id
        )

    def generate_text(self, prompt):
        response = self.inference.generate(prompt, params={"max_new_tokens": 512})
        return response['results'][0]['generated_text'].strip()

watsonx_client = WatsonxClient()


def fetch_all_databases():
    """
    Fetches the list of all database names from MySQL server.
    Returns list like ['information_schema', 'mysql', 'PO_APP', 'Task', ...]
    """
    try:
        result = mysql_query("SHOW DATABASES;")
        if result and "rows" in result:
            print([row[0] for row in result["rows"]],"This is my DatabaseName")
            return [row[0] for row in result["rows"]]
    except Exception as e:
        logging.error(f"Error fetching databases: {e}")
    # Fallback to env default only if failed
    return [os.getenv("MYSQL_DATABASE")]


def detect_and_normalize_names(user_input, available_dbs):
    """
    This uses Watsonx LLM to identify and normalize database name, table name, and column names
    based on user input and available databases/tables.

    Returns a dict: {
      "database": <exact_db_name>,
      "table": <exact_table_name>,
      "column": <exact_column_name or None>
    }
    """
    # Step 1: For all available databases, fetch top tables (to limit prompt size)
    db_tables = {}
    for db in available_dbs:
        try:
            tables = get_all_tables_in_db(db)
            db_tables[db] = tables
        except Exception as e:
            logging.warning(f"Could not fetch tables for DB {db}: {e}")
            db_tables[db] = []

    # Prepare a summarized schema description for prompt
    schema_info_str = ""
    for db, tables in db_tables.items():
        schema_info_str += f"\nDatabase `{db}` has tables: {', '.join(tables)}"

#     prompt = f"""
# You are an expert SQL assistant.

# User input:
# \"\"\"{user_input}\"\"\"

# Available database: Task
# Available table in Task: Invoice_Data
# Invoice_Data table columns: id, billing_organization_name, billing_address, billing_contact_information, billing_phone_number, billing_gst_number, billing_hsn_number, shipping_organization_name, shipping_address, shipping_contact_information, shipping_phone_number, shipping_gst_number, shipping_hsn_number, invoice_number, invoice_date, due_date, total_amount, subtotal, tax_amount, discount, po_number, currency, payment_terms, verification_status, file_path, extracted_at, created_at, updated_at, line_items, file_name

# Please identify exactly:
# - The database name (choose from "Task" or null if none specified)
# - The main table name (choose from "Invoice_Data" or null if none specified)
# - The exact column name in Invoice_Data if mentioned; otherwise null

# If the user input is ambiguous or does not explicitly refer to any, return null for those fields.

# Return ONLY this JSON dictionary with keys "database", "table", and "column", for example:

# {{
#   "database": ...,
#   "table": ...,
#   "column": ...
# }}
# """

    prompt = f"""
You are an expert SQL assistant specialized in understanding user queries and mapping them exactly to database schema elements.

User input:
\"\"\"{user_input}\"\"\"

Schema information for matching:

- Available database: `Task`
- Available table in `Task`: `Invoice_Data`
- Columns in `Invoice_Data`:
  id, billing_organization_name, billing_address, billing_contact_information, billing_phone_number,
  billing_gst_number, billing_hsn_number, shipping_organization_name, shipping_address,
  shipping_contact_information, shipping_phone_number, shipping_gst_number, billing_hsn_number,
  invoice_number, invoice_date, due_date, total_amount, subtotal, tax_amount, discount, po_number,
  currency, payment_terms, verification_status, file_path, extracted_at, created_at,
  updated_at, line_items, file_name

Your task:

- Analyze the user input and exactly identify if it explicitly mentions any of the following:
  1. The database name (must be `Task` or `null`)
  2. The main table name (must be `Invoice_Data` or `null`)
  3. An exact column name from the columns listed above (or `null` if none mentioned)

- If the user input references synonyms or common terms related to columns (e.g., "total revenue" relates to `total_amount`), you may map accordingly only if the mention is clear.

- If there is ambiguity or no explicit mention of any database, table, or column name, return `null` for those fields.

Important:

- Do NOT guess or invent names.
- Only respond with the JSON dictionary below WITHOUT ANY additional text or explanation.

Example output JSON:

{{
  "database": "Task",
  "table": "Invoice_Data",
  "column": "total_amount"
}}

If nothing matches explicitly, return:

{{
  "database": null,
  "table": null,
  "column": null
}}
"""



    response = watsonx_client.generate_text(prompt)

    logging.info(f"Name detection LLM response: {response}")

    # Parse JSON out of response safely
    import json
    try:
        detected = json.loads(response)
    except Exception:
        # Attempt to extract JSON substring naive fallback
        try:
            json_start = response.index("{")
            json_end = response.rindex("}") + 1
            detected = json.loads(response[json_start:json_end])
        except Exception as e:
            logging.error(f"Could not parse LLM JSON response: {e}")
            detected = {"database": None, "table": None, "column": None}

    return detected


def build_full_sql_query(user_input, db_name, table_name, column_name=None):
    """
    Build a valid SQL query string by instructing Watsonx LLM
    using exact database/table/column names previously predicted.
    If column_name is given, build a query accordingly (for column info or aggregations).
    If not, try to generate a sensible query for the input and known schema.
    """
    # Get columns info for given database & table to improve prompt
    columns = []
    if db_name and table_name:
        columns = get_table_schema(db_name, table_name)

    schema_info = ""
    if columns:
        schema_info = f"\nTable `{table_name}` columns: {', '.join(columns)}"

#     prompt = f"""
# You are an expert SQL generator.

# The user wants to run a query on the database `{db_name}`, table `{table_name}`.

# Columns in the table: {', '.join(columns)}{schema_info}

# User input or question:
# \"\"\"{user_input}\"\"\"

# Instructions:
# - Always generate a **valid MySQL query**.
# - Use fully qualified table names like `{db_name}.{table_name}`.
# - Use the exact column names from the table.
# - Do not include explanations—only return the SQL query.
# - If the user mentions "total revenue", interpret it as the `total_amount` column.
# - if the user mention 'products' means this will be line_item description present in the line_item array.

# Examples:

# > User: Who are the top 5 customers by total amount?  
# ```sql
# SELECT org_name, SUM(CAST(total_amount AS FLOAT)) AS total_amount_sum
# FROM Task.Invoice_Data
# GROUP BY org_name
# ORDER BY total_amount_sum DESC
# LIMIT 5;
# User: What are the invoices in March month?

 
# SELECT *
# FROM Task.Invoice_Data
# WHERE MONTH(invoice_date) = 3;
# User: Total invoice amount of UNIWARE SYSTEMS PVT LTD organization?

 
# SELECT SUM(CAST(total_amount AS FLOAT))
# FROM Task.Invoice_Data
# WHERE org_name = 'UNIWARE SYSTEMS PVT LTD';
# User: Show me the highest total amount invoice customer.

 
# SELECT org_name, invoice_number, total_amount
# FROM Task.Invoice_Data
# ORDER BY CAST(total_amount AS FLOAT) DESC
# LIMIT 1;
# User: Summarize the table
# SELECT * FROM Task.Invoice_Data;
# If the line_items column contains an array of JSON objects like:


# [
#  { {
#     "s_no": 1,
#     "description": "AMC of DELL EMC Data Domain 6300 – Renewal",
#     "quantity": 1,
#     "unit_price": 550000.00,
#     "total_per_product": 550000.00
#   },
#   {
#     "s_no": 2,
#     "description": "Uniware Support for One Year – Uniware 8/5 On-Demand Remote Support",
#     "quantity": 1,
#     "unit_price": 40000.00,
#     "total_per_product": 40000.00
#   }
# }
#   ]


# Example
# "Which product appears in the most invoices?"

 
# SELECT 
#   description AS product,
#   COUNT(DISTINCT id) AS invoice_count
# FROM Task.Invoice_Data,
#   JSON_TABLE(
#     line_items,
#     '$[*]' COLUMNS (
#       description VARCHAR(255) PATH '$.description'
#     )
#   ) AS items
# GROUP BY description
# ORDER BY invoice_count DESC
# LIMIT 1;
# "What is the total quantity sold for each product?

# Based on these examples and rules, generate only the appropriate SQL query for the given user input.
# """
    prompt=f"""
You are an expert SQL generator.

The user wants to run a query on the database `{db_name}`, table `{table_name}`.

Columns in the table: {', '.join(columns)}{schema_info}

User input or question:
\"\"\"{user_input}\"\"\"

Instructions:
- Always generate a **valid MySQL query**.
- Use fully qualified table names like `{db_name}.{table_name}`.
- Use the exact column names from the table.
- Do not include explanations—only return the SQL query.
- If the user mentions "total revenue" or "total amount", interpret it as the `total_amount` column.
- If the user mentions "products" or "product", this refers to the `description` field inside the JSON array in the `line_items` column.

Examples:

> User: Who are the top 5 customers by total amount?  
SELECT billing_organization_name, SUM(CAST(total_amount AS DECIMAL(18,2))) AS total_amount_sum
FROM {db_name}.{table_name}
GROUP BY billing_organization_name
ORDER BY total_amount_sum DESC
LIMIT 5;

 

> User: What are the invoices in March month?
SELECT *
FROM {db_name}.{table_name}
WHERE MONTH(invoice_date) = 3;


> User: Total invoice amount of UNIWARE SYSTEMS PVT LTD organization?
SELECT SUM(CAST(total_amount AS DECIMAL(18,2)))
FROM {db_name}.{table_name}
WHERE billing_organization_name = 'UNIWARE SYSTEMS PVT LTD';


> User: Show me the highest total amount invoice customer.
SELECT billing_organization_name, invoice_number, total_amount
FROM {db_name}.{table_name}
ORDER BY CAST(total_amount AS DECIMAL(18,2)) DESC
LIMIT 1;



> User: Summarize the table
SELECT * FROM {db_name}.{table_name};



If the `line_items` column contains an array of JSON objects like:

[
{
  {
    "S.NO": 1,
    "description": "AMC of DELL EMC Data Domain 6300 – Renewal",
    "quantity": 1,
    "unit_price": 550000.00,
    "total_per_product": 550000.00
  },
  {
    "S.NO": 2,
    "description": "Uniware Support for One Year – Uniware 8/5 On-Demand Remote Support",
    "quantity": 1,
    "unit_price": 40000.00,
    "total_per_product": 40000.00
  }

  }
]

Example:
"Which product appears in the most invoices?"
SELECT
items.description AS product,
COUNT(DISTINCT id) AS invoice_count
FROM {db_name}.{table_name},
JSON_TABLE(
line_items,
'$[*]' COLUMNS (
description VARCHAR(255) PATH '$.description'
)
) AS items
GROUP BY items.description
ORDER BY invoice_count DESC
LIMIT 1;

 

Example:
"What is the total quantity sold for each product?"
SELECT
items.description AS product,
SUM(CAST(items.quantity AS UNSIGNED)) AS total_quantity_sold
FROM {db_name}.{table_name},
JSON_TABLE(
line_items,
'$[*]' COLUMNS (
description VARCHAR(255) PATH '$.description',
quantity VARCHAR(50) PATH '$.quantity'
)
) AS items
GROUP BY items.description
ORDER BY total_quantity_sold DESC;

 

Based on these examples and rules, generate only the appropriate SQL query for the given user input.


"""
    if column_name:
        prompt += f"\nThe user specifically mentioned a column `{column_name}` that may be in the query."

    response = watsonx_client.generate_text(prompt)
    logging.info(f"Generated SQL from LLM: {response}")

    # Extract SQL (naive - look for SQL code or from first SQL keyword)
    sql_query = extract_sql_from_llm_response(response)
    print(sql_query,"This is my sql querrryyyyyyyyyyyy")
    return sql_query


def extract_sql_from_llm_response(response_text):
    """
    Extract SQL from the LLM response by locating code blocks or starting at SQL keywords.
    """
    import re
    # Look for code block fenced by backticks
    code_blocks = re.findall(r"``````", response_text, re.DOTALL | re.IGNORECASE)
    if code_blocks:
        return code_blocks[0].strip()
    code_blocks = re.findall(r"``````", response_text, re.DOTALL | re.IGNORECASE)
    if code_blocks:
        return code_blocks[0].strip()

    # Otherwise find first SQL keyword and return from there
    sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH', 'SHOW', 'DESCRIBE', 'EXPLAIN']
    pattern = re.compile("(" + "|".join(sql_keywords) + ")", re.IGNORECASE)
    match = pattern.search(response_text)
    if match:
        print(response_text[match.start():].strip(),"if keywrd matchessssss")
        return response_text[match.start():].strip()

    # fallback: return full response
    print(response_text.strip(),"response_text.strip()")
    return response_text.strip()


def extract_column_from_sql_error(error_msg):
    """
    Extract unknown column name from MySQL error message.
    """
    matches = re.findall(r"Unknown column '(.+?)' in", error_msg)
    if matches:
        return matches[0]
    return None


def fix_sql_query_column(sql, error_msg, db_name, table_name):
    """
    Attempt to fix SQL by replacing unknown column with closest matching column in actual schema.
    """
    invalid_col = extract_column_from_sql_error(error_msg)
    if not invalid_col:
        return None

    columns = get_table_schema(db_name, table_name)
    if not columns:
        return None

    matches = get_close_matches(invalid_col, columns, n=1, cutoff=0.6)
    if not matches:
        return None

    corrected_col = matches[0]
    fixed_sql = re.sub(re.escape(invalid_col), corrected_col, sql, flags=re.IGNORECASE)
    print( "fixed_sql", fixed_sql)
    return fixed_sql


def handle_user_query(user_input):
    """
    Main entry point.

    Logic:
    1. Fetch all available databases.
    2. Use LLM + database metadata to detect exact DB, table, column names from user input.
    3. Generate fully qualified, exact SQL query.
    4. Try executing query with MCP.
    5. If error about unknown columns, auto-fix once.
    6. Return results and diagnostic info.
    """

    logging.info(f"Received user input: {user_input}")

    # Step 1: Fetch all databases dynamically
    available_dbs = fetch_all_databases()

    # Step 2: Detect exact database, table, and column names using LLM helper
    detected = detect_and_normalize_names(user_input, available_dbs)
    db_name = detected.get("database") or os.getenv("MYSQL_DATABASE")
    # table_name = detected.get("table")
    table_name = detected.get("table") or "Invoice_Data"
    column_name = detected.get("column")

    # Security fallback & logging
    if db_name not in available_dbs:
        logging.warning(f"Detected DB '{db_name}' not in available databases list; falling back to default")
        db_name = os.getenv("MYSQL_DATABASE")

    logging.info(f"Normalized names - DB: {db_name}, Table: {table_name}, Column: {column_name}")

    # Step 3: Build SQL query with exact names
    try:
        sql_query = build_full_sql_query(user_input, db_name=db_name, table_name=table_name, column_name=column_name)
    except Exception as e:
        logging.error(f"Error generating SQL query: {e}")
        return {"error": f"AI generation failed: {str(e)}"}

    # Step 4: Try executing the query
    try:
        result = mysql_query(sql_query, db_name=db_name)
        return {
            "sql": sql_query,
            "result": result,
            "corrected": False,
            "database": db_name,
            "table": table_name,
            "column": column_name
        }
    except Exception as exec_err:
        error_msg = str(exec_err)
        logging.warning(f"Query execution failed: {error_msg}")

        # Step 5: Try to auto-fix unknown column errors once
        fixed_sql = fix_sql_query_column(sql_query, error_msg, db_name, table_name)
        if fixed_sql and fixed_sql != sql_query:
            logging.info(f"Retrying with fixed SQL:\n{fixed_sql}")
            try:
                fixed_result = mysql_query(fixed_sql, db_name=db_name)
                return {
                    "sql": fixed_sql,
                    "result": fixed_result,
                    "corrected": True,
                    "original_sql": sql_query,
                    "database": db_name,
                    "table": table_name,
                    "column": column_name
                }
            except Exception as second_err:
                logging.error(f"Execution failed even after fix: {second_err}")
                return {"error": f"Execution failed after fix: {second_err}", "sql": fixed_sql}

        # If no fix possible, return original error
        print (f"Execution failed: {error_msg}")
        print (f"Original SQL: {sql_query}")
        return {"error": f"Query execution error: {error_msg}", "sql": sql_query}

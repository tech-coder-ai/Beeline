-- Beeline demo dataset: loaded automatically by the hive-init container.

CREATE DATABASE IF NOT EXISTS sales;
USE sales;

DROP TABLE IF EXISTS dim_customers;
CREATE TABLE dim_customers (
  customer_id   INT,
  customer_name STRING,
  region        STRING,
  segment       STRING,
  signup_date   STRING
)
COMMENT 'Customer master data with region and segment'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='0');

DROP TABLE IF EXISTS dim_products;
CREATE TABLE dim_products (
  product_id   INT,
  product_name STRING,
  category     STRING,
  unit_price   DECIMAL(10,2)
)
COMMENT 'Product catalog with category and list price'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='0');

DROP TABLE IF EXISTS fact_sales;
CREATE TABLE fact_sales (
  order_id    INT,
  order_date  STRING,
  customer_id INT,
  product_id  INT,
  region      STRING,
  quantity    INT,
  unit_price  DECIMAL(10,2),
  amount      DECIMAL(12,2),
  cost        DECIMAL(12,2),
  margin      DECIMAL(12,2)
)
COMMENT 'Order-line grain sales fact table, 24 months of history'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='0');

LOAD DATA LOCAL INPATH '/seed/dim_customers.csv' OVERWRITE INTO TABLE dim_customers;
LOAD DATA LOCAL INPATH '/seed/dim_products.csv' OVERWRITE INTO TABLE dim_products;
LOAD DATA LOCAL INPATH '/seed/fact_sales.csv' OVERWRITE INTO TABLE fact_sales;

ANALYZE TABLE dim_customers COMPUTE STATISTICS;
ANALYZE TABLE dim_products COMPUTE STATISTICS;
ANALYZE TABLE fact_sales COMPUTE STATISTICS;

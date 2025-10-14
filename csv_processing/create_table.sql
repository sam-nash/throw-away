-- This SQL command creates a BigQuery table with the schema matching the sample CSV files.
-- Replace `your_dataset` with the ID of your BigQuery dataset.

CREATE TABLE `your_dataset.your_table` (
  id INT64,
  name STRING,
  value INT64
);

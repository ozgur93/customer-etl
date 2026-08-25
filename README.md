# Customer ETL

A small Python ETL pipeline for reading customer data from CSV, validating its schema and records, normalizing values, and writing clean and rejected records to separate outputs.

The project is intentionally compact and focuses on core data engineering practices: explicit data contracts, data quality checks, reproducible configuration, operational logging, controlled error handling, and automated tests.

## Features

- Uses `pathlib.Path` for source and output paths.
- Reads customer data from CSV and validates the expected schema.
- Normalizes status values by trimming whitespace and converting them to uppercase.
- Validates customer IDs, statuses, ages, and signup dates.
- Supports multiple rejection reasons for the same record.
- Separates valid records from rejected records.
- Prepares clean ages as pandas `Int64` and signup dates as datetime values.
- Writes clean and rejected records to separate CSV files.
- Produces a pipeline report with record counts, integrity results, rejection counts, and output paths.
- Uses operational logging and a dedicated `PipelineError` exception hierarchy.
- Treats expected data quality problems as rejected records rather than pipeline failures.
- Reads runtime configuration from environment variables with safe defaults and fail-fast validation.

## Data Quality Rules

| Field | A record is rejected when |
| --- | --- |
| `customer_id` | The value is missing or duplicated. |
| `status` | The normalized value is not `ACTIVE` or `INACTIVE`. |
| `age` | The value is non-numeric or is not a whole number. |
| `signup_date` | The value cannot be parsed with the `YYYY-MM-DD` format. |

Rejected records include boolean validation flags and a pipe-delimited `reject_reason` value. A record can therefore contain more than one rejection reason.

## Project Structure

```text
customer-etl/
|-- data/
|   `-- customers_raw.csv
|-- main.py
|-- test_main.py
|-- .gitignore
`-- README.md
```

The `output/` directory is created by the pipeline when needed and is intentionally excluded from Git.

## Requirements

- Python 3
- pandas
- pytest (for running the test suite)

Install the dependencies into your preferred virtual environment:

```powershell
python -m pip install pandas pytest
```

## Run the Pipeline

From the project root:

```powershell
python main.py
```

With no environment variables set, the pipeline uses:

- Source: `data/customers_raw.csv`
- Output directory: `output/`

## Configuration

| Environment variable | Purpose | Default |
| --- | --- | --- |
| `CUSTOMER_ETL_DATA_FILE` | Path to the source CSV file. | `data/customers_raw.csv` |
| `CUSTOMER_ETL_OUTPUT_DIR` | Directory for generated output files. | `output/` |

Example for PowerShell:

```powershell
$env:CUSTOMER_ETL_DATA_FILE = "C:\path\to\customers.csv"
$env:CUSTOMER_ETL_OUTPUT_DIR = "C:\path\to\output"
python main.py
```

An environment variable containing an empty or whitespace-only value is rejected with a `ConfigurationError`.

## Outputs

| File | Contents |
| --- | --- |
| `customers_clean.csv` | Validated and load-ready customer records. |
| `customers_reject.csv` | Rejected records, validation flags, and rejection reasons. |

Both files are written under the configured output directory.

## Tests

Run the complete test suite from the project root:

```powershell
python -m pytest test_main.py -v
```

Current test status: **32 passed**.

The tests cover configuration, schema validation, transformations, row-level validation, clean/reject splitting, load preparation, output writing, exception wrapping, pipeline integrity, and an end-to-end pipeline run.

## Error Handling

Pipeline-level failures derive from `PipelineError`, including configuration, source read, schema validation, integrity, load preparation, and output write failures. Technical causes are preserved through Python exception chaining, while the program entry point logs pipeline failures once and exits with a failure status.

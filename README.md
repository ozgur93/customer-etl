# Customer ETL

A compact Python data engineering project demonstrating CSV-based ETL and REST API extraction workflows.

The project focuses on practical data engineering patterns including explicit data contracts, data quality validation, clean/reject processing, operational error handling, REST API pagination, retry and rate-limit handling, environment-based configuration, stable DataFrame schemas, reproducible dependencies, and automated tests.

## Features

### CSV Customer ETL

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

### REST API Extraction

- Retrieves user data from the GoREST REST API.
- Supports pagination through `page` and `per_page` parameters.
- Reads pagination metadata from response headers.
- Uses request timeouts and HTTP status validation.
- Retries transient timeout and connection failures.
- Applies exponential backoff between retry attempts.
- Handles HTTP 429 rate-limit responses separately.
- Parses and validates JSON responses.
- Uses a dedicated API exception hierarchy for request, parsing, schema, pagination, and rate-limit failures.
- Supports optional Bearer token authentication.
- Loads local environment variables with `python-dotenv`.
- Converts JSON records into a pandas DataFrame.
- Applies a stable DataFrame column contract.
- Writes the extracted API data to CSV.
- Separates extraction, transformation, persistence, and top-level orchestration responsibilities.

The REST API DataFrame contract is:

```text
id
name
email
gender
status
```

Unexpected API fields are excluded from the final DataFrame. Missing expected fields remain as missing values.

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
|-- api_extraction.py
|-- main.py
|-- test_api_extraction.py
|-- test_main.py
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

The `output/` directory is created when needed and is intentionally excluded from Git.

Local `.env` files are also excluded from Git.

## Requirements

- Python 3
- pandas
- requests
- python-dotenv
- pytest

Install the project dependencies into your preferred virtual environment:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

### CSV Pipeline

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

### REST API Authentication

The REST API extraction flow supports an optional GoREST Bearer token.

Create a local `.env` file based on:

```text
.env.example
```

and set:

```text
GOREST_API_TOKEN=
```

If no token is required, the value can remain empty.

Real credentials should never be committed to Git.

## Running the Pipelines

### CSV Customer ETL

From the project root:

```powershell
python main.py
```

With no environment variables set, the pipeline uses:

```text
Source: data/customers_raw.csv
Output: output/
```

### REST API Extraction

From the project root:

```powershell
python api_extraction.py
```

The extraction flow is:

```text
REST API
   |
   v
Pagination
   |
   v
JSON parsing and validation
   |
   v
DataFrame conversion
   |
   v
Stable schema contract
   |
   v
CSV output
```

The generated API data is written to:

```text
output/users_api.csv
```

## Outputs

| File | Contents |
| --- | --- |
| `customers_clean.csv` | Validated and load-ready customer records. |
| `customers_reject.csv` | Rejected records, validation flags, and rejection reasons. |
| `users_api.csv` | User records extracted from the REST API using the defined DataFrame schema. |

Generated files are written under the `output/` directory.

## Tests

Run the complete test suite from the project root:

```powershell
python -m pytest
```

The tests cover areas including:

- Configuration
- CSV schema validation
- Data transformations
- Row-level data quality validation
- Clean/reject splitting
- Load preparation
- Output writing
- Pipeline integrity
- End-to-end CSV pipeline behavior
- API request behavior
- JSON parsing and response validation
- Pagination
- Retry and exponential backoff
- Rate-limit handling
- Bearer token configuration
- DataFrame schema behavior
- API extraction orchestration
- CSV persistence

External behavior such as network requests and selected filesystem operations is isolated with mocks and pytest fixtures where appropriate.

## Error Handling

The CSV pipeline uses a `PipelineError` hierarchy for pipeline-level failures including configuration, source reading, schema validation, integrity checks, load preparation, and output writing.

The REST API extraction layer uses dedicated exception types for request failures, invalid response schemas, JSON parsing failures, invalid pagination metadata, and rate-limit responses.

Underlying technical causes are preserved through Python exception chaining where appropriate.

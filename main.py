from pathlib import Path
import pandas as pd
import logging
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)

class PipelineError(Exception):
    pass

class SchemaValidationError(PipelineError):
    pass

class SourceReadError(PipelineError):
    pass

class PipelineIntegrityError(PipelineError):
    pass

class LoadPreparationError(PipelineError):
    pass

class OutputWriteError(PipelineError):
    pass

class ConfigurationError(PipelineError):
    pass

@dataclass(frozen=True)
class PipelineConfig:
    data_file: Path
    output_dir: Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_FILE = BASE_DIR / "data" / "customers_raw.csv"

DEFAULT_OUTPUT_DIR = BASE_DIR / "output"

EXPECTED_COLUMNS = ["customer_id","name","email","country","signup_date","status","age"]
VALID_STATUSES = ["ACTIVE", "INACTIVE"]



def load_config():
    
    environment_data_file = os.getenv("CUSTOMER_ETL_DATA_FILE")
    environment_output_dir = os.getenv("CUSTOMER_ETL_OUTPUT_DIR")
        
    if environment_data_file is None:
        resolved_data_file = DEFAULT_DATA_FILE
    elif not environment_data_file.strip():
        raise ConfigurationError("CUSTOMER_ETL_DATA_FILE cannot be empty.")
    else:
        resolved_data_file = Path(environment_data_file)
        
    if environment_output_dir is None:
        resolved_output_dir = DEFAULT_OUTPUT_DIR
    elif not environment_output_dir.strip():
        raise ConfigurationError("CUSTOMER_ETL_OUTPUT_DIR cannot be empty.")
    else:
        resolved_output_dir = Path(environment_output_dir)
        
    config = PipelineConfig(
        data_file=resolved_data_file,
        output_dir=resolved_output_dir,
    )

    return config


def read_source(path):
    try:
        df = pd.read_csv(path)
        return df
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise SourceReadError(f"Failed to read source file. path={path}") from exc



def validate_schema(df):
    
    # kolon valid kontrolü
    column_names = df.columns.tolist()
    columns_is_valid = sorted(column_names) == sorted(EXPECTED_COLUMNS)

    if not columns_is_valid:
        raise SchemaValidationError(f"Schema validation failed. expected_columns={EXPECTED_COLUMNS} actual_columns={column_names}") 


def profile_raw_data(df):
    raw_data_profile_result = {}

    raw_data_profile_result["status_counts"] = df["status"].value_counts(dropna=False)

    return raw_data_profile_result


def transform(df):
    transformed_df = df.copy()

    transformed_df["status"] = transformed_df["status"].str.strip().str.upper()

    return transformed_df


def validate_rows(df):
    row_validation_result = {}

    # customer_id kolonunda null değer
    row_validation_result["null_customer_id_mask"] = df["customer_id"].isnull()

    # customer_id kolonunda mükerrer değer
    row_validation_result["duplicate_customer_id_mask"] = df["customer_id"].duplicated(keep=False)

    # status kolonunda geçersiz değer
    row_validation_result["invalid_status_mask"] = ~df["status"].isin(VALID_STATUSES)

    # age kolonunda geçersiz değer
    age_numeric = pd.to_numeric(df["age"], errors="coerce")
    non_numeric_age_mask = age_numeric.isna() & df["age"].notna()

    # age kolonunda ondalık değerler
    non_integer_age_mask = age_numeric.notna() & (age_numeric % 1 != 0)

    row_validation_result["invalid_age_mask"] = non_numeric_age_mask | non_integer_age_mask

    # signup_date kolonunda geçersiz tarih formatı
    signup_date_parsed = pd.to_datetime(df["signup_date"],format="%Y-%m-%d",errors="coerce")
    row_validation_result["invalid_signup_date_mask"] = signup_date_parsed.isna() & df["signup_date"].notna()
    

    return row_validation_result


def summarize_row_validation(row_validation):
    validation_counts = {}
    
    validation_counts["null_customer_id"] = int(row_validation["null_customer_id_mask"].sum())
    validation_counts["duplicate_customer_id"] = int(row_validation["duplicate_customer_id_mask"].sum())
    validation_counts["invalid_status"] = int(row_validation["invalid_status_mask"].sum())
    validation_counts["invalid_age"] = int(row_validation["invalid_age_mask"].sum())
    validation_counts["invalid_signup_date"] = int(row_validation["invalid_signup_date_mask"].sum())
    
    return validation_counts
    


def build_reject_reason(row):
    reasons = []
    if row["is_null_customer_id"]:
        reasons.append("null_customer_id")
    if row["is_duplicate_customer_id"]:
        reasons.append("duplicate_customer_id")
    if row["is_invalid_status"]:
        reasons.append("invalid_status")
    if row["is_invalid_age"]:
        reasons.append("invalid_age")
    if row["is_invalid_signup_date"]:
        reasons.append("invalid_signup_date")
    return "|".join(reasons)


def split_records(df, row_validation):
    reject_mask = (
        row_validation["null_customer_id_mask"] 
        | row_validation["duplicate_customer_id_mask"] 
        | row_validation["invalid_status_mask"] 
        | row_validation["invalid_age_mask"]
        | row_validation["invalid_signup_date_mask"]
    )
    reject_df = df[reject_mask].copy()

    clean_df = df[~reject_mask].copy()

    reject_df["is_null_customer_id"] = row_validation["null_customer_id_mask"]
    reject_df["is_duplicate_customer_id"] = row_validation["duplicate_customer_id_mask"]
    reject_df["is_invalid_status"] = row_validation["invalid_status_mask"]
    reject_df["is_invalid_age"] = row_validation["invalid_age_mask"]
    reject_df["is_invalid_signup_date"] = row_validation["invalid_signup_date_mask"]
    reject_df["reject_reason"] = reject_df.apply(build_reject_reason, axis=1)

    return clean_df, reject_df


def prepare_for_load(clean_df):
    load_df = clean_df.copy()
    
    try:
        load_df["age"] = pd.to_numeric(load_df["age"], errors="raise").astype("Int64")
        load_df["signup_date"] = pd.to_datetime(load_df["signup_date"], format="%Y-%m-%d", errors="raise")
    except (ValueError, TypeError, OverflowError) as exc:
        raise LoadPreparationError("Load preparation failed.") from exc

    return load_df



def build_output_paths(output_dir):
    clean_output_file = output_dir / "customers_clean.csv"
    reject_output_file = output_dir / "customers_reject.csv"
    
    return clean_output_file, reject_output_file



def write_outputs(load_df, reject_df, output_dir):
        
    clean_output_file, reject_output_file = build_output_paths(output_dir)
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        load_df.to_csv(clean_output_file, index=False, encoding="utf-8", date_format="%Y-%m-%d")
        reject_df.to_csv(reject_output_file, index=False, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise OutputWriteError(f"Failed to write output files. path={output_dir}") from exc

    return clean_output_file, reject_output_file


def build_pipeline_report(
    source_df,
    load_df,
    reject_df,
    clean_output_path,
    reject_output_path):

    pipeline_report = {}

    pipeline_report["total_records"] = len(source_df.index)

    pipeline_report["clean_records"] = len(load_df.index)

    pipeline_report["reject_records"] = len(reject_df.index)

    pipeline_report["records_match"] = len(source_df.index) == len(load_df.index) + len(reject_df.index)

    split_reason = reject_df["reject_reason"].str.split("|").explode()
    pipeline_report["reject_reason_counts"] = split_reason.value_counts().to_dict()

    pipeline_report["clean_output_path"] = str(clean_output_path)

    pipeline_report["reject_output_path"] = str(reject_output_path)

    return pipeline_report


def main():
    logger.info("Pipeline started.")
    
    config = load_config()

    df = read_source(config.data_file)
    logger.info("Data read: success. path=%s rows=%d columns=%d",config.data_file,len(df),len(df.columns))

    validate_schema(df)
    logger.info("Schema validation passed.")

    raw_data_profile = profile_raw_data(df)
    logger.debug("Raw status profile created. status_counts=%s", raw_data_profile["status_counts"].to_dict())
    
    new_df = transform(df)
    logger.info("Status normalization completed. rows=%d", len(new_df))

    row_validation = validate_rows(new_df)
    
    validation_counts = summarize_row_validation(row_validation)
    
    logger.debug("Row validation details. validation_counts=%s", validation_counts)
    logger.info("Row validation completed.")

    clean_df, reject_df = split_records(new_df, row_validation)
    
    total_records = len(new_df)
    clean_records = len(clean_df)
    reject_records = len(reject_df)
    records_match = len(new_df) == len(clean_df) + len(reject_df)
    
    if not records_match:
        raise PipelineIntegrityError(f"Record count mismatch. total_records={total_records}, clean_records={clean_records}, reject_records={reject_records}")
        
    
    logger.info("Split completed. total_records=%d clean_records=%d reject_records=%d", total_records, clean_records, reject_records)
    
    if reject_records > 0:
        logger.warning("Reject records detected. reject_records=%d validation_counts=%s", reject_records, validation_counts)

    load_df = prepare_for_load(clean_df)
    logger.info("Load preparation completed. prepared_rows=%d", len(load_df))
    logger.debug("Load preparation details. column_types=%s", load_df.dtypes.astype(str).to_dict())

    clean_output_path, reject_output_path = write_outputs(load_df,reject_df,output_dir=config.output_dir)
    
    logger.info("Outputs written. clean_output_path=%s reject_output_path=%s clean_records=%d reject_records=%d", 
                clean_output_path, reject_output_path, len(load_df), len(reject_df))
    
    pipeline_report = build_pipeline_report(df,load_df,reject_df,clean_output_path,reject_output_path)
    
    logger.info("Pipeline completed. total_records=%d clean_records=%d reject_records=%d records_match=%s", 
                pipeline_report["total_records"],
                pipeline_report["clean_records"],
                pipeline_report["reject_records"],
                pipeline_report["records_match"])
    
    logger.debug("Pipeline report created. pipeline_report=%s", pipeline_report)
    
    return pipeline_report
    

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        main()
    except PipelineError:
        logger.exception("Pipeline failed due to a pipeline error.")
        raise SystemExit(1)
import pandas as pd
import pytest
import main as etl

@pytest.fixture
def temporary_output_paths(tmp_path, monkeypatch):

    output_dir = tmp_path / "output"
    clean_path = output_dir / "customers_clean.csv"
    reject_path = output_dir / "customers_reject.csv"
    
    monkeypatch.setenv("CUSTOMER_ETL_OUTPUT_DIR",str(output_dir))

    return clean_path, reject_path



def test_load_config_returns_default_paths(monkeypatch):
    
    monkeypatch.delenv("CUSTOMER_ETL_DATA_FILE", raising=False)
    monkeypatch.delenv("CUSTOMER_ETL_OUTPUT_DIR", raising=False)
    config = etl.load_config()
    assert isinstance(config, etl.PipelineConfig)
    assert config.data_file == etl.DEFAULT_DATA_FILE
    assert config.output_dir == etl.DEFAULT_OUTPUT_DIR
    
    
def test_load_config_reads_data_file_from_environment(tmp_path, monkeypatch):
    environment_data_file = tmp_path / "customers_from_env.csv"

    monkeypatch.setenv("CUSTOMER_ETL_DATA_FILE",str(environment_data_file))

    config = etl.load_config()

    assert config.data_file == environment_data_file
    
    
    
def test_load_config_reads_output_dir_from_environment(tmp_path, monkeypatch):
    environment_output_dir = tmp_path / "custom_output"

    monkeypatch.setenv("CUSTOMER_ETL_OUTPUT_DIR",str(environment_output_dir))

    config = etl.load_config()

    assert config.output_dir == environment_output_dir
    
    
@pytest.mark.parametrize(
    "invalid_data_file",
    [
        "",
        "   ",
    ],
)
def test_load_config_rejects_empty_data_file(invalid_data_file,monkeypatch):
    monkeypatch.setenv("CUSTOMER_ETL_DATA_FILE",invalid_data_file)

    with pytest.raises(etl.ConfigurationError):
        etl.load_config()
        
        
@pytest.mark.parametrize(
    "invalid_output_dir",
    [
        "",
        "   ",
    ],
)
def test_load_config_rejects_empty_output_dir(invalid_output_dir,monkeypatch):
    monkeypatch.delenv("CUSTOMER_ETL_DATA_FILE",raising=False)
    monkeypatch.setenv("CUSTOMER_ETL_OUTPUT_DIR",invalid_output_dir)

    with pytest.raises(etl.ConfigurationError):
        etl.load_config()
    
    

@pytest.mark.parametrize(
    "raw_status, expected_status",
    [
        (" active ", "ACTIVE"),
        ("inactive", "INACTIVE")
    ],
)
def test_transform_normalizes_status_values(raw_status, expected_status):
    
    input_df = pd.DataFrame({"status": [raw_status]})
    result_df = etl.transform(input_df)
    assert result_df["status"].tolist() == [expected_status]

    
    
def test_validate_schema_raises_error_when_columns_are_missing():
    input_df = pd.DataFrame({
        "customer_id": [1],
        "name": ["Ayşe"]
    })
    
    with pytest.raises(etl.SchemaValidationError):
        etl.validate_schema(input_df)



def test_validate_schema_accepts_expected_columns():
    input_df = pd.DataFrame(columns=[
        "customer_id",
        "name",
        "email",
        "country",
        "signup_date",
        "status",
        "age",
])
    etl.validate_schema(input_df)
    
@pytest.mark.parametrize(
    "status, expected_is_invalid",
    [
        ("ACTIVE", False),
        ("PENDING", True),
    ],
)
def test_validate_rows_marks_invalid_status(status, expected_is_invalid):
    input_df = pd.DataFrame({
        "customer_id": [1],
        "status": [status],
        "age": [30],
        "signup_date": ["2025-01-10"],
})

    row_validation = etl.validate_rows(input_df)
    assert row_validation["invalid_status_mask"].tolist() == [expected_is_invalid]
    
    
    
def test_validate_rows_marks_all_duplicate_customer_ids():
    input_df = pd.DataFrame({
        "customer_id": [101, 101, 102],
        "status": ["ACTIVE", "ACTIVE", "INACTIVE"],
        "age": [30, 31, 32],
        "signup_date": [
            "2025-01-10",
            "2025-01-11",
            "2025-01-12",
        ],
    })

    row_validation = etl.validate_rows(input_df)
    assert row_validation["duplicate_customer_id_mask"].tolist() == [True, True, False]
    

def test_validate_rows_marks_null_customer_id():
    input_df = pd.DataFrame({
        "customer_id": [101, None],
        "status": ["ACTIVE", "ACTIVE"],
        "age": [30, 31],
        "signup_date": ["2025-01-10", "2025-01-11"],
    })

    row_validation = etl.validate_rows(input_df)
    assert row_validation["null_customer_id_mask"].tolist() == [False, True]
    
    
    
@pytest.mark.parametrize(
    "age, expected_is_invalid",
    [
        (30, False),
        ("unknown", True),
        (25.5, True),
    ],
)
def test_validate_rows_marks_invalid_ages(age, expected_is_invalid):
    input_df = pd.DataFrame({
    "customer_id": [201],
    "status": ["ACTIVE"],
    "age": [age],
    "signup_date": ["2025-01-10"],
})
    
    row_validation = etl.validate_rows(input_df)
    assert row_validation["invalid_age_mask"].tolist() == [expected_is_invalid]

    
    
@pytest.mark.parametrize(
    "signup_date, expected_is_invalid",
    [
        ("2025-01-10", False),
        ("not-a-date", True),
    ],
)
def test_validate_rows_marks_invalid_signup_date(signup_date, expected_is_invalid):
    input_df = pd.DataFrame({
    "customer_id": [301],
    "status": ["ACTIVE"],
    "age": [30],
    "signup_date": [signup_date],
})

    row_validation = etl.validate_rows(input_df)
    assert row_validation["invalid_signup_date_mask"].tolist() == [expected_is_invalid]
    
    
    
def test_split_records_separates_clean_and_reject_records():
    input_df = pd.DataFrame({
        "customer_id": [1, 2],
        "status": ["ACTIVE", "PENDING"],
        "age": [30, 31],
        "signup_date": ["2025-01-10", "2025-01-11"],
    })

    row_validation = etl.validate_rows(input_df)

    clean_df, reject_df = etl.split_records(input_df, row_validation)
    
    assert clean_df["customer_id"].tolist() == [1]
    assert reject_df["customer_id"].tolist() == [2]
    assert reject_df["reject_reason"].tolist() == ["invalid_status"]
    
    
def test_split_records_combines_multiple_reject_reasons():
    input_df = pd.DataFrame({
        "customer_id": [None],
        "status": ["PENDING"],
        "age": ["unknown"],
        "signup_date": ["not-a-date"],
    })

    row_validation = etl.validate_rows(input_df)
    _, reject_df = etl.split_records(input_df, row_validation)
    assert reject_df["reject_reason"].tolist()  == ["null_customer_id|invalid_status|invalid_age|invalid_signup_date"]
    
    
def test_prepare_for_load_converts_column_types():
    clean_df = pd.DataFrame({
        "age": ["30", "31"],
        "signup_date": ["2025-01-10", "2025-01-11"],
    })

    load_df = etl.prepare_for_load(clean_df)
    assert str(load_df["age"].dtype) == "Int64"
    assert pd.api.types.is_datetime64_any_dtype(load_df["signup_date"].dtype)
    
    
def test_prepare_for_load_raises_error_for_invalid_age():
    clean_df = pd.DataFrame({
        "age": ["unknown"],
        "signup_date": ["2025-01-10"],
    })

    with pytest.raises(etl.LoadPreparationError):
        etl.prepare_for_load(clean_df)
        

def test_build_pipeline_report_contains_counts_and_reject_reasons():
    source_df = pd.DataFrame({
        "customer_id": [1, 2, 3],
    })

    load_df = pd.DataFrame({
        "customer_id": [1],
    })

    reject_df = pd.DataFrame({
        "reject_reason": [
            "invalid_status",
            "invalid_age|invalid_status",
        ],
    })
    
    pipeline_report = etl.build_pipeline_report(
        source_df=source_df,
        load_df=load_df,
        reject_df=reject_df,
        clean_output_path="clean.csv",
        reject_output_path="reject.csv"
    )
    
    assert pipeline_report["total_records"] == 3
    assert pipeline_report["clean_records"] == 1
    assert pipeline_report["reject_records"] == 2
    assert pipeline_report["records_match"] is True
    assert pipeline_report["reject_reason_counts"] == {"invalid_status": 2,"invalid_age": 1}
    assert pipeline_report["clean_output_path"] == "clean.csv"
    assert pipeline_report["reject_output_path"] == "reject.csv"
    
    
def test_read_source_reads_csv_file(tmp_path):
    source_path = tmp_path / "customers.csv"

    source_df = pd.DataFrame({
        "customer_id": [1, 2],
        "status": ["ACTIVE", "INACTIVE"],
    })

    source_df.to_csv(source_path, index=False)
    
    result_df = etl.read_source(source_path)
    assert result_df.columns.tolist() == ["customer_id", "status"]
    assert result_df["customer_id"].tolist() == [1, 2]
    assert result_df["status"].tolist() == ["ACTIVE", "INACTIVE"]
    
    
def test_read_source_raises_error_when_file_does_not_exist(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(etl.SourceReadError):
        etl.read_source(missing_path)
        
        
def test_build_output_paths_derives_file_paths(tmp_path):
    output_dir = tmp_path / "output"

    clean_output_file, reject_output_file = etl.build_output_paths(output_dir)

    assert clean_output_file == output_dir / "customers_clean.csv"
    assert reject_output_file == output_dir / "customers_reject.csv"
        
        
def test_write_outputs_writes_files_to_temporary_directory(temporary_output_paths):
    
    clean_path, reject_path = temporary_output_paths

    load_df = pd.DataFrame({
        "customer_id": [1],
        "signup_date": pd.to_datetime(["2025-01-10"]),
    })

    reject_df = pd.DataFrame({
        "customer_id": [2],
        "reject_reason": ["invalid_status"],
    })

    returned_clean_path, returned_reject_path = etl.write_outputs(load_df, reject_df,output_dir=clean_path.parent)
    
    assert returned_clean_path == clean_path
    assert returned_reject_path == reject_path
    
    assert clean_path.exists()
    assert reject_path.exists()

    assert pd.read_csv(clean_path)["customer_id"].tolist() == [1]
    assert pd.read_csv(reject_path)["customer_id"].tolist() == [2]
    

def test_write_outputs_wraps_os_error(tmp_path,monkeypatch):
    load_df = pd.DataFrame({
        "customer_id": [1],
    })

    reject_df = pd.DataFrame({
        "customer_id": [2],
    })

    def raise_os_error(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", raise_os_error)


    with pytest.raises(etl.OutputWriteError) as exc_info:
        etl.write_outputs(load_df, reject_df,output_dir=tmp_path)

    assert isinstance(exc_info.value.__cause__, OSError)
    
    
def test_main_runs_pipeline_with_temporary_files(
    tmp_path,
    monkeypatch,
    temporary_output_paths,
):
    source_path = tmp_path / "customers_raw.csv"
    clean_path, reject_path = temporary_output_paths

    source_df = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "name": ["Ayşe", "Mehmet", "Zeynep"],
        "email": [
            "ayse@example.com",
            "mehmet@example.com",
            "zeynep@example.com",
        ],
        "country": ["TR", "TR", "TR"],
        "signup_date": [
            "2025-01-10",
            "2025-01-11",
            "2025-01-12",
        ],
        "status": [" active ", "PENDING", "INACTIVE"],
        "age": [30, 31, 32],
    })


    source_df.to_csv(source_path, index=False)

    monkeypatch.setenv("CUSTOMER_ETL_DATA_FILE",str(source_path))

    pipeline_report = etl.main()


    assert pipeline_report["total_records"] == 3
    assert pipeline_report["clean_records"] == 2
    assert pipeline_report["reject_records"] == 1
    assert pipeline_report["records_match"] is True
    assert clean_path.exists()
    assert reject_path.exists()

    clean_df = pd.read_csv(clean_path)
    reject_df = pd.read_csv(reject_path)
    
    assert clean_df["customer_id"].tolist() == [1, 3]
    assert clean_df["status"].tolist() == ["ACTIVE", "INACTIVE"]
    assert reject_df["customer_id"].tolist() == [2]
    assert reject_df["reject_reason"].tolist() == ["invalid_status"]
    
    
def test_main_raises_integrity_error_when_records_disappear(monkeypatch):
    source_df = pd.DataFrame({
        "customer_id": [1],
        "name": ["Ayşe"],
        "email": ["ayse@example.com"],
        "country": ["TR"],
        "signup_date": ["2025-01-10"],
        "status": ["ACTIVE"],
        "age": [30],
    })

    def fake_read_source(_path):
        return source_df.copy()

    def fake_split_records(_df, _row_validation):
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(etl, "read_source", fake_read_source)
    monkeypatch.setattr(etl, "split_records", fake_split_records)

    with pytest.raises(etl.PipelineIntegrityError):
        etl.main()

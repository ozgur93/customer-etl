import pytest
import api_extraction as api
from unittest.mock import Mock, call
import pandas as pd


def test_validate_users_response_schema_accepts_list_of_dictionaries():
    users = [{'id': 1, 'name': 'ahmet'},{'id': 2, 'name': 'mehmet'}]
    
    api.validate_users_response_schema(users)
    
def test_validate_users_response_schema_accepts_empty_list():
    users = []
    
    api.validate_users_response_schema(users)
    
    
@pytest.mark.parametrize(
    "invalid_users",
    [
        {"users": []},
        "unexpected",
        None,
    ],
)
def test_validate_users_response_schema_rejects_non_list(invalid_users):
    with pytest.raises(api.ApiResponseSchemaError):
        api.validate_users_response_schema(invalid_users)
        
        
def test_validate_users_response_schema_rejects_non_dictionary_record():
    users = [{"id": 1}, "bad-record"]

    with pytest.raises(api.ApiResponseSchemaError):
        api.validate_users_response_schema(users)
        
        
def test_request_users_response_sends_expected_request(monkeypatch):
    fake_response = Mock()
    fake_response.status_code = 200
    fake_get = Mock(return_value=fake_response)

    monkeypatch.setattr(api.requests, "get", fake_get)
    
    monkeypatch.delenv(api.API_TOKEN_ENV_VAR, raising=False)

    result = api.request_users_response()

    fake_get.assert_called_once_with(
        api.USERS_API_URL,
        params={"page": 1, "per_page": api.DEFAULT_PAGE_SIZE},
        headers={"Accept": "application/json"},
        timeout=api.REQUEST_TIMEOUT_SECONDS,
    )

    fake_response.raise_for_status.assert_called_once_with()

    assert result is fake_response
    
    
@pytest.mark.parametrize(
    "request_error",
    [
        api.requests.Timeout("simulated timeout"),
        api.requests.ConnectionError("simulated connection failure"),
    ],
)
def test_request_users_response_wraps_transport_errors(request_error,monkeypatch):
    fake_get = Mock(side_effect=request_error)
    monkeypatch.setattr(api.requests, "get", fake_get)
    
    fake_sleep = Mock()
    monkeypatch.setattr(api.time, "sleep", fake_sleep)

    with pytest.raises(api.ApiRequestError) as exc_info:
        api.request_users_response()

    assert exc_info.value.__cause__ is request_error
    assert fake_get.call_count == api.MAX_RETRIES + 1
    assert fake_sleep.call_args_list == [
        call(1),
        call(2),
    ]
    
    
def test_request_users_response_wraps_http_error(monkeypatch):
    http_error = api.requests.HTTPError("simulated HTTP error")

    fake_response = Mock()
    fake_response.status_code = 500
    fake_response.raise_for_status.side_effect = http_error

    fake_get = Mock(return_value=fake_response)
    monkeypatch.setattr(api.requests, "get", fake_get)
    
    fake_sleep = Mock()
    monkeypatch.setattr(api.time, "sleep", fake_sleep)

    with pytest.raises(api.ApiRequestError) as exc_info:
        api.request_users_response()

    assert exc_info.value.__cause__ is http_error
    fake_get.assert_called_once()
    fake_sleep.assert_not_called()
    
    
def test_parse_users_response_wraps_invalid_json():
    json_error = api.requests.exceptions.JSONDecodeError("simulated invalid JSON","",0)

    fake_response = Mock()
    fake_response.json.side_effect = json_error

    with pytest.raises(api.ApiResponseParseError) as exc_info:
        api.parse_users_response(fake_response)

    assert exc_info.value.__cause__ is json_error
    
    
def test_parse_users_response_returns_parsed_users():
    expected_users = [
        {
            "id": 1,
            "name": "Ayşe",
        }
    ]

    fake_response = Mock()
    fake_response.json.return_value = expected_users

    result = api.parse_users_response(fake_response)

    fake_response.json.assert_called_once_with()
    assert result == expected_users
    
    
def test_fetch_all_users_combines_paginated_results(monkeypatch):
    first_response = Mock()
    first_response.headers = {api.PAGINATION_PAGES_HEADER: "2"}
    first_response.json.return_value = [
        {"id": 1},
        {"id": 2},
    ]

    second_response = Mock()
    second_response.json.return_value = [
        {"id": 3},
    ]

    fake_request = Mock(side_effect=[first_response,second_response])
    monkeypatch.setattr(api,"request_users_response",fake_request)

    result = api.fetch_all_users(per_page=2)

    assert result == [
        {"id": 1},
        {"id": 2},
        {"id": 3},
    ]

    assert fake_request.call_args_list == [
        call(page=1, per_page=2),
        call(page=2, per_page=2),
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {api.PAGINATION_PAGES_HEADER: "unknown"},
        {api.PAGINATION_PAGES_HEADER: "-1"},
    ],
)
def test_get_total_pages_rejects_invalid_metadata(headers):
    fake_response = Mock()
    fake_response.headers = headers

    with pytest.raises(api.ApiPaginationError):
        api.get_total_pages(fake_response)
        
        
def test_request_users_response_raises_rate_limit_error(monkeypatch):
    fake_response = Mock()
    fake_response.status_code = 429
    fake_response.headers = {
        api.RATE_LIMIT_RESET_HEADER: "41"
    }

    fake_get = Mock(return_value=fake_response)
    monkeypatch.setattr(api.requests, "get", fake_get)
    
    fake_sleep = Mock()
    monkeypatch.setattr(api.time, "sleep", fake_sleep)

    with pytest.raises(api.ApiRateLimitError) as exc_info:
        api.request_users_response()

    assert "retry_after_seconds=41" in str(exc_info.value)
    fake_response.raise_for_status.assert_not_called()
    fake_get.assert_called_once()
    fake_sleep.assert_not_called()
    
    
@pytest.mark.parametrize(
    "retry_number, expected_seconds",
    [
        (0,1),
        (1,2),
        (2,4),
    ],
)
def test_calculate_backoff_seconds(retry_number, expected_seconds):
    result = api.calculate_backoff_seconds(retry_number)
    assert result == expected_seconds
    
    
def test_request_users_response_retries_after_timeout(monkeypatch):
    fake_response = Mock()
    fake_response.status_code = 200
    fake_get = Mock(
        side_effect=[
            api.requests.Timeout("simulated timeout"),
            fake_response,
        ]
    )
    monkeypatch.setattr(api.requests, "get", fake_get)
    
    fake_sleep = Mock()
    monkeypatch.setattr(api.time, "sleep", fake_sleep)
    
    result = api.request_users_response()
    
    assert result is fake_response
    assert fake_get.call_count == 2
    fake_sleep.assert_called_once_with(1)
    
    
def test_get_api_token_returns_environment_variable(monkeypatch):
    monkeypatch.setenv(api.API_TOKEN_ENV_VAR, "fake-token")
    result = api.get_api_token()
    
    assert result == "fake-token"
    
def test_get_api_token_returns_none_when_environment_variable_is_missing(monkeypatch):
    monkeypatch.delenv(api.API_TOKEN_ENV_VAR, raising=False)
    result = api.get_api_token()
    
    assert result is None
    
def test_build_request_headers_without_token(monkeypatch):
    monkeypatch.delenv(api.API_TOKEN_ENV_VAR, raising=False)

    result = api.build_request_headers()

    assert result == {
        "Accept": "application/json",
    }
    
def test_build_request_headers_with_token(monkeypatch):
    monkeypatch.setenv(api.API_TOKEN_ENV_VAR, "fake-token")

    result = api.build_request_headers()

    assert result == {
            "Accept": "application/json",
            "Authorization": "Bearer fake-token",
        }
    
def test_request_users_response_sends_bearer_token_when_available(monkeypatch):
    monkeypatch.setenv(api.API_TOKEN_ENV_VAR, "fake-token")
    
    fake_response = Mock()
    fake_response.status_code = 200
    fake_get = Mock(return_value=fake_response)
    monkeypatch.setattr(api.requests, "get", fake_get)
    
    result = api.request_users_response()
    
    
    fake_get.assert_called_once_with(
        api.USERS_API_URL,
        params={"page": 1, "per_page": api.DEFAULT_PAGE_SIZE},
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer fake-token",
        },
        timeout=api.REQUEST_TIMEOUT_SECONDS,
    )
    
    assert result is fake_response
    
@pytest.mark.parametrize(
    "token_value",
    [
        "",
        "   ",
    ],
)
def test_get_api_token_returns_none_for_blank_value(token_value, monkeypatch):
    monkeypatch.setenv(api.API_TOKEN_ENV_VAR, token_value)
    result = api.get_api_token()
    
    assert result is None
    
def test_get_api_token_strips_surrounding_whitespace(monkeypatch):
        monkeypatch.setenv(api.API_TOKEN_ENV_VAR, "  fake-token  ")
        result = api.get_api_token()
        
        assert result == "fake-token"
        
def test_users_to_dataframe_converts_records():
    users = [
        {"id": 1, "name": "Ayşe", "status": "active"},
        {"id": 2, "name": "Mehmet", "status": "inactive"},
    ]
    
    result = api.users_to_dataframe(users)
    
    assert list(result.columns) == api.USER_COLUMNS
    assert len(result) == 2
    assert result.loc[0, "name"] == "Ayşe"
    assert result.loc[1, "status"] == "inactive"
    
def test_users_to_dataframe_accepts_empty_list():
    users = []

    result = api.users_to_dataframe(users)

    assert result.empty
    assert list(result.columns) == api.USER_COLUMNS
    
def test_users_to_dataframe_handles_records_with_different_fields():
    users = [
        {
            "id": 1,
            "name": "Ayşe",
            "status": "active",
        },
        {
            "id": 2,
            "name": "Mehmet",
            "phone": "555-1234",
        },
    ]

    result = api.users_to_dataframe(users)

    assert list(result.columns) == api.USER_COLUMNS
    assert "phone" not in result.columns
    assert pd.isna(result.loc[1, "status"])
    
def test_extract_users_dataframe_orchestrates_fetch_and_conversion(monkeypatch):
    users = [
        {"id": 1, "name": "Ayşe"},
        {"id": 2, "name": "Mehmet"},
    ]
    
    expected_df = pd.DataFrame(users)
    
    fake_fetch = Mock(return_value=users)
    fake_to_dataframe = Mock(return_value=expected_df)
    
    monkeypatch.setattr(api, "fetch_all_users", fake_fetch)
    monkeypatch.setattr(api, "users_to_dataframe", fake_to_dataframe)
    
    result = api.extract_users_dataframe(per_page=25)
    
    fake_fetch.assert_called_once_with(per_page=25)
    fake_to_dataframe.assert_called_once_with(users)
    assert result is expected_df
    
def test_save_users_dataframe_writes_csv(tmp_path):
    users_df = pd.DataFrame(
        [
            {"id": 1, "name": "Ayşe"},
            {"id": 2, "name": "Mehmet"},
        ]
    )

    output_path = tmp_path / "nested" / "users.csv"

    result = api.save_users_dataframe(users_df, output_path=output_path)

    assert result == output_path
    assert output_path.exists()

    saved_df = pd.read_csv(output_path)

    assert len(saved_df) == 2
    assert list(saved_df.columns) == ["id", "name"]
    assert saved_df.loc[0, "name"] == "Ayşe"
    
def test_run_users_extraction_orchestrates_extract_and_save(
    monkeypatch,
    tmp_path,
):
    expected_df = pd.DataFrame(
        [
            {"id": 1, "name": "Ayşe"},
            {"id": 2, "name": "Mehmet"},
        ]
    )

    output_path = tmp_path / "users.csv"

    fake_extract = Mock(return_value=expected_df)
    fake_save = Mock(return_value=output_path)

    monkeypatch.setattr(
        api,
        "extract_users_dataframe",
        fake_extract,
    )
    monkeypatch.setattr(
        api,
        "save_users_dataframe",
        fake_save,
    )

    result = api.run_users_extraction(
        per_page=25,
        output_path=output_path,
    )

    fake_extract.assert_called_once_with(per_page=25)

    fake_save.assert_called_once_with(
        expected_df,
        output_path=output_path,
    )

    assert result == output_path
import pytest
import api_extraction as api
from unittest.mock import Mock, call


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

    with pytest.raises(api.ApiRequestError) as exc_info:
        api.request_users_response()

    assert exc_info.value.__cause__ is request_error
    
    
def test_request_users_response_wraps_http_error(monkeypatch):
    http_error = api.requests.HTTPError("simulated HTTP error")

    fake_response = Mock()
    fake_response.status_code = 500
    fake_response.raise_for_status.side_effect = http_error

    fake_get = Mock(return_value=fake_response)
    monkeypatch.setattr(api.requests, "get", fake_get)

    with pytest.raises(api.ApiRequestError) as exc_info:
        api.request_users_response()

    assert exc_info.value.__cause__ is http_error
    
    
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

    with pytest.raises(api.ApiRateLimitError) as exc_info:
        api.request_users_response()

    assert "retry_after_seconds=41" in str(exc_info.value)
    fake_response.raise_for_status.assert_not_called()
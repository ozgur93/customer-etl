import requests

class ApiExtractionError(Exception):
    pass

class ApiResponseSchemaError(ApiExtractionError):
    pass

class ApiRequestError(ApiExtractionError):
    pass

class ApiRateLimitError(ApiRequestError):
    pass

class ApiResponseParseError(ApiExtractionError):
    pass

class ApiPaginationError(ApiExtractionError):
    pass


USERS_API_URL = "https://gorest.co.in/public/v2/users"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_PAGE_SIZE = 100
PAGINATION_PAGES_HEADER = "X-Pagination-Pages"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"


def validate_users_response_schema(users):
    if not isinstance(users, list):
        raise ApiResponseSchemaError(
            f"Users response must be a list. actual_type={type(users).__name__}"
        )

    if not all(isinstance(user, dict) for user in users):
        raise ApiResponseSchemaError(
            "Every user record must be a dictionary."
        )
        


def get_total_pages(response):
    raw_total_pages = response.headers.get(PAGINATION_PAGES_HEADER)

    try:
        total_pages = int(raw_total_pages)
    except (TypeError, ValueError) as exc:
        raise ApiPaginationError("Invalid pagination metadata. "
            f"header={PAGINATION_PAGES_HEADER} "
            f"value={raw_total_pages}"
        ) from exc

    if total_pages < 0:
        raise ApiPaginationError(f"Total pages cannot be negative. total_pages={total_pages}")

    return total_pages



def request_users_response(page=1, per_page=DEFAULT_PAGE_SIZE):
    try:
        response = requests.get(
            USERS_API_URL,
            params={"page": page, "per_page": per_page},
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        
        if response.status_code == 429:
            reset_after_seconds = response.headers.get(RATE_LIMIT_RESET_HEADER)
            raise ApiRateLimitError(
                "API rate limit exceeded. "
                f"retry_after_seconds={reset_after_seconds}"
            )

        response.raise_for_status()
    except requests.RequestException as exc:
        raise ApiRequestError(f"Failed to request users. url={USERS_API_URL} page={page}") from exc

    return response



def parse_users_response(response):
    try:
        users = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ApiResponseParseError(
            "Failed to parse users response as JSON."
        ) from exc

    validate_users_response_schema(users)

    return users



def fetch_all_users(per_page=DEFAULT_PAGE_SIZE):
    first_response = request_users_response(page=1,per_page=per_page)
    all_users = parse_users_response(first_response)

    total_pages = get_total_pages(first_response)

    for page in range(2, total_pages + 1):
        response = request_users_response(page=page,per_page=per_page)
        users = parse_users_response(response)
        all_users.extend(users)

    return all_users



if __name__ == "__main__":
    response = request_users_response()

    print(response.status_code)
    print(response.url)
    print(response.headers)
    print(response.text[:150])
    
    users = parse_users_response(response)

    print(type(users))
    print(type(users).__name__)
    print(type(users[0]))
    print(users[0])
    
    total_pages = get_total_pages(response)
    
    print(total_pages)
    
    # all_users = fetch_all_users()
    
    # print(len(all_users))
import requests
import time
import os
from dotenv import load_dotenv
import pandas as pd
from pathlib import Path

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


load_dotenv()
USERS_API_URL = "https://gorest.co.in/public/v2/users"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_PAGE_SIZE = 100
PAGINATION_PAGES_HEADER = "X-Pagination-Pages"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"
MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 1
API_TOKEN_ENV_VAR = "GOREST_API_TOKEN"
USER_COLUMNS = [
    "id",
    "name",
    "email",
    "gender",
    "status",
]
API_OUTPUT_PATH = Path("output") / "users_api.csv"




def validate_users_response_schema(users):
    if not isinstance(users, list):
        raise ApiResponseSchemaError(
            f"Users response must be a list. actual_type={type(users).__name__}"
        )

    if not all(isinstance(user, dict) for user in users):
        raise ApiResponseSchemaError(
            "Every user record must be a dictionary."
        )



def get_api_token():
    token = os.getenv(API_TOKEN_ENV_VAR)

    if token is None:
        return None

    token = token.strip()

    if not token:
        return None

    return token



def build_request_headers():
    token = get_api_token()
    
    if token is None:
        headers = {"Accept": "application/json"}
    else:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        
    return headers

    
    
def calculate_backoff_seconds(retry_number):
    backoff_seconds = BACKOFF_BASE_SECONDS * (2 ** retry_number)
    
    return backoff_seconds



def request_users_response(page=1, per_page=DEFAULT_PAGE_SIZE):
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                USERS_API_URL,
                params={"page": page, "per_page": per_page},
                headers=build_request_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
                
            if response.status_code == 429:
                reset_after_seconds = response.headers.get(RATE_LIMIT_RESET_HEADER)
                raise ApiRateLimitError(
                    "API rate limit exceeded. "
                    f"retry_after_seconds={reset_after_seconds}"
                )

            response.raise_for_status()
                    
            return response
            
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == MAX_RETRIES:
                raise ApiRequestError(f"Failed to request users. url={USERS_API_URL} page={page}") from exc

            backoff_seconds = calculate_backoff_seconds(attempt)
            time.sleep(backoff_seconds)
              
        except requests.RequestException as exc:
            raise ApiRequestError(f"Failed to request users. url={USERS_API_URL} page={page}") from exc



def parse_users_response(response):
    try:
        users = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ApiResponseParseError(
            "Failed to parse users response as JSON."
        ) from exc

    validate_users_response_schema(users)

    return users



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



def fetch_all_users(per_page=DEFAULT_PAGE_SIZE):
    first_response = request_users_response(page=1,per_page=per_page)
    all_users = parse_users_response(first_response)

    total_pages = get_total_pages(first_response)

    for page in range(2, total_pages + 1):
        response = request_users_response(page=page,per_page=per_page)
        users = parse_users_response(response)
        all_users.extend(users)

    return all_users



def users_to_dataframe(users):
    validate_users_response_schema(users)

    df = pd.DataFrame(users)
    df = df.reindex(columns=USER_COLUMNS)

    return df



def extract_users_dataframe(per_page=DEFAULT_PAGE_SIZE):
    users = fetch_all_users(per_page=per_page)
    users_df = users_to_dataframe(users)

    return users_df



def save_users_dataframe(users_df, output_path=API_OUTPUT_PATH):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    users_df.to_csv(output_path, index=False)
    
    return output_path



def run_users_extraction(per_page=DEFAULT_PAGE_SIZE,output_path=API_OUTPUT_PATH):
    
    users_df = extract_users_dataframe(per_page=per_page)
    saved_path = save_users_dataframe(users_df,output_path=output_path)

    return saved_path



if __name__ == "__main__":
    saved_path = run_users_extraction()
    print(f"Users saved to: {saved_path}")
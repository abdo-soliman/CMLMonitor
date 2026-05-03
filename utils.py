import os
import re
from enum import Enum


class WorkloadType(str, Enum):
    ALL = "all"
    SESSION = "session"
    APPLICATION = "application"
    JOB = "job"
    # MODEL = "model"
    # BATCH = "batch"


class SearchFilters(str, Enum):
    ALL = "all"
    USERNAME = "username"
    USER_FULLNAME = "user_fullname"
    PROJECT = "project"
    SESSION_NAME = "session_name"
    NAMESPACE = "namespace"
    SESSION_ID = "session_id"
    STATUS = "status"
    AGE = "age"
    RESOURCES = "resources"


class OrderByFilters(str, Enum):
    ALL = "all"
    AGE = "age"
    RESOURCES = "resources"


def validate_config_file(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"{file_path} does not exist or is not a file")

    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"{file_path} is not readable")


def is_none_or_empty(variable):
    if variable is None or variable == "":
        return True

    return False


def validate_none_or_empty(variable):
    if variable is None:
        raise ValueError("All Config variables must be avialable with correct vaules")

    if variable == "":
        raise ValueError("All Config variables must be avialable with correct vaules")

    return variable


def safe_str(val):
    return str(val) if val is not None else ""


def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None  # Returns None if the port is blank or invalid


def safe_bool(val):
    # Database stores '1' or '0', but this also catches 'true' just in case
    return str(val).strip().lower() in ['1', 'true', 'yes']


def split_age(age):
    matches = re.findall(r"(\d+)([dhms])", age)
    # Convert to dictionary
    age_dict = {letter: int(number) for number, letter in matches}
    if "d" not in age_dict:
        age_dict["d"] = 0

    if "h" not in age_dict:
        age_dict["h"] = 0

    if "m" not in age_dict:
        age_dict["m"] = 0

    if "s" not in age_dict:
        age_dict["s"] = 0

    age_dict["d"] = age_dict["d"]  + int(age_dict["h"] / 24)
    age_dict["h"] = (age_dict["h"] % 24) + int(age_dict["m"] / 60)
    age_dict["m"] = (age_dict["m"] % 60) + int(age_dict["s"] / 60)
    age_dict["s"] = age_dict["s"] % 60

    return age_dict


def age_toseconds(age_dict):
    # day to seconds 24*60*60=86400, hours to seconds 60*60=3600
    return (age_dict["d"] * 86400) + (age_dict["h"] * 3600) + (age_dict["m"] * 60) + age_dict["s"]


def seconds_to_age(seconds):
    age_dict = { "d": 0, "h": 0, "m": 0, "s": 0 }
    
    age_dict["s"] = seconds % 60
    minutes = int(seconds / 60)

    age_dict["m"] = minutes % 60
    hours = int(minutes / 60)

    age_dict["h"] = hours % 24
    age_dict["d"] = int(hours / 24)

    return age_dict


def age_dict_tostring(age_dict):
    age_string = ""

    age_string = age_string + f"{age_dict['d']}d" if age_dict["d"] > 0 else age_string
    age_string = age_string + f"{age_dict['h']}h" if age_dict["h"] > 0 else age_string
    age_string = age_string + f"{age_dict['m']}m" if age_dict["m"] > 0 else age_string
    age_string = age_string + f"{age_dict['s']}s" if age_dict["s"] > 0 else age_string

    return age_string


def keep_only_arabic(string):
    # if no string provided return None
    if string is None:
        return None, False

    # This pattern matches any character that is NOT in the Arabic Unicode range
    # The '^' inside the brackets means "NOT"
    non_arabic_pattern = r'[^\u0600-\u06FF\s]' 

    # Check if the string contains at least one Arabic character
    has_arabic = re.search(r'[\u0600-\u06FF]', string)
    if has_arabic:
        cleaned_string = re.sub(non_arabic_pattern, '', string) # We replace non-Arabic characters with an empty string ''
        cleaned_string = " ".join(cleaned_string.split()) # Clean up extra whitespace
        return cleaned_string, has_arabic

    # If no Arabic is found, return the original string
    return string, has_arabic


def pagination_to_indecies(page_size, page_number, total_size):
    page_size = page_size if page_size in [25, 50, 100] else 25

    max_number_of_pages = int(total_size / page_size)
    if total_size % page_size > 0:
        max_number_of_pages = int(total_size / page_size) + 1

    page_number = page_number if page_number > 0 and page_number <= max_number_of_pages else 1

    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size

    return start_index, end_index, page_number, page_size, max_number_of_pages

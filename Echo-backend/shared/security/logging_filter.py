import logging
import re


SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(access_token[\"'=:\s]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(secret[\"'=:\s]+)[^\"'\s,;&}]+"),
    re.compile(r"(?i)(openid[\"'=:\s]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(js_code=)[^&\s]+"),
    re.compile(r"(?i)(token=)[^&\s]+"),
    re.compile(r"(?i)(key=)[^&\s]+"),
)


def redact_sensitive_text(value: object) -> object:
    if not isinstance(value, str):
        return value

    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def _redact_log_argument(value: object) -> object:
    redacted = redact_sensitive_text(value)
    if redacted is not value:
        return redacted

    rendered = str(value)
    redacted_rendered = redact_sensitive_text(rendered)
    return redacted_rendered if redacted_rendered != rendered else value


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: _redact_log_argument(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_log_argument(value) for value in record.args)
        return True


def install_sensitive_data_filter() -> None:
    root_logger = logging.getLogger()
    sensitive_filter = next(
        (
            existing_filter
            for existing_filter in root_logger.filters
            if isinstance(existing_filter, SensitiveDataFilter)
        ),
        None,
    )
    if sensitive_filter is None:
        sensitive_filter = SensitiveDataFilter()
        root_logger.addFilter(sensitive_filter)
    for handler in root_logger.handlers:
        if not any(
            isinstance(existing_filter, SensitiveDataFilter)
            for existing_filter in handler.filters
        ):
            handler.addFilter(sensitive_filter)

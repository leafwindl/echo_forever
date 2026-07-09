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


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_sensitive_text(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_sensitive_text(value) for value in record.args)
        return True


def install_sensitive_data_filter() -> None:
    root_logger = logging.getLogger()
    if any(isinstance(existing_filter, SensitiveDataFilter) for existing_filter in root_logger.filters):
        return

    sensitive_filter = SensitiveDataFilter()
    root_logger.addFilter(sensitive_filter)
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)

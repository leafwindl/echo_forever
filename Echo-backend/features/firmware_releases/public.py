from features.firmware_releases.domain.entities import FirmwareRelease
from features.firmware_releases.infrastructure.postgres_repository import (
    PostgresFirmwareReleaseRepository,
)


def get_latest_firmware_release(
    board_type: str, board_variant: str = ""
) -> FirmwareRelease | None:
    return PostgresFirmwareReleaseRepository().find_latest(board_type, board_variant)

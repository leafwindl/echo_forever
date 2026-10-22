"""Live device connections shared by transport and calibration use cases."""

active_device_sessions: dict[str, object] = {}

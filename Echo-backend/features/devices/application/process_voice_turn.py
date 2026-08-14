from collections.abc import Awaitable, Callable

from features.devices.domain.entities import DeviceTurnResult
from features.devices.domain.services import (
    DeviceChatNotifier,
    DeviceConversationService,
    DeviceVoiceRecognizer,
)


class ProcessDeviceVoiceTurn:
    """Recognize one completed utterance and run the existing Echo call flow."""

    def __init__(
        self,
        *,
        recognizer: DeviceVoiceRecognizer,
        conversation: DeviceConversationService,
        notifier: DeviceChatNotifier,
    ):
        self.recognizer = recognizer
        self.conversation = conversation
        self.notifier = notifier

    async def execute(
        self,
        *,
        user_id: str,
        pcm16_audio: bytes,
        request_id: str,
        on_recognized: Callable[[str], Awaitable[None]] | None = None,
    ) -> DeviceTurnResult:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ValueError("Device is not mapped to an Echo user")
        if not pcm16_audio:
            raise ValueError("Device audio is empty")

        user_text = (await self.recognizer.recognize_pcm16(pcm16_audio)).strip()
        if not user_text:
            raise ValueError("Device speech was not recognized")
        if on_recognized is not None:
            await on_recognized(user_text)

        result = await self.conversation.reply(
            user_id=clean_user_id,
            user_text=user_text,
            request_id=request_id,
        )
        await self.notifier.notify_latest_turn(clean_user_id)
        return result

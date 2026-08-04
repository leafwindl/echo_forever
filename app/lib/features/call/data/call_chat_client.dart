import 'package:echo_app/features/chat/data/chat_api.dart';
import 'package:echo_app/features/chat/data/dto/chat_dtos.dart';

class CallChatReply {
  const CallChatReply({required this.reply, required this.audioUrls});

  final String reply;
  final List<String> audioUrls;
}

abstract interface class CallChatClient {
  Future<CallChatReply> send(String text);
}

class ApiCallChatClient implements CallChatClient {
  const ApiCallChatClient(this._api);

  final ChatApi _api;

  @override
  Future<CallChatReply> send(String text) async {
    final response = await _api.sendMessage(
      ChatRequestDto(message: text, mode: 'call'),
    );
    return CallChatReply(reply: response.reply, audioUrls: response.audioUrls);
  }
}

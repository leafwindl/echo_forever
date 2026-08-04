import 'package:echo_app/core/network/dio_client.dart';
import 'package:echo_app/features/letters/domain/letter.dart';

class LettersApi {
  const LettersApi(this._client);

  final DioClient _client;

  static const listPath = '/letters';
  static const itemPath = '/letters';

  Future<LetterListResponseDto> listLetters({int limit = 50}) async {
    final response = await _client.get<Map<String, dynamic>>(
      listPath,
      queryParameters: <String, dynamic>{'limit': limit},
    );
    return LetterListResponseDto.fromJson(response.data!);
  }

  Future<DailyLetter> getLetter(String letterId) async {
    final response = await _client.get<Map<String, dynamic>>(
      '$itemPath/${Uri.encodeComponent(letterId)}',
    );
    return DailyLetter.fromJson(response.data!);
  }

  Future<DailyLetter> markRead(String letterId) async {
    final response = await _client.post<Map<String, dynamic>>(
      '$itemPath/${Uri.encodeComponent(letterId)}/read',
    );
    return DailyLetter.fromJson(response.data!);
  }
}

class LetterListResponseDto {
  const LetterListResponseDto({required this.items, required this.unreadCount});

  factory LetterListResponseDto.fromJson(Map<String, dynamic> json) {
    return LetterListResponseDto(
      items: (json['items'] as List? ?? const <Object?>[])
          .whereType<Map<String, dynamic>>()
          .map(DailyLetter.fromJson)
          .toList(growable: false),
      unreadCount: json['unread_count'] as int? ?? 0,
    );
  }

  final List<DailyLetter> items;
  final int unreadCount;
}

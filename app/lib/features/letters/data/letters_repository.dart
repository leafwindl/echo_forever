import 'package:echo_app/features/letters/data/letters_api.dart';
import 'package:echo_app/features/letters/domain/letter.dart';

abstract interface class LettersRepository {
  Future<LetterListResult> listLetters({required int limit});

  Future<DailyLetter> getLetter(String letterId);

  Future<DailyLetter> markRead(String letterId);
}

class LettersRepositoryImpl implements LettersRepository {
  const LettersRepositoryImpl(this._api);

  final LettersApi _api;

  @override
  Future<LetterListResult> listLetters({required int limit}) async {
    final response = await _api.listLetters(limit: limit);
    return LetterListResult(
      items: response.items,
      unreadCount: response.unreadCount,
    );
  }

  @override
  Future<DailyLetter> getLetter(String letterId) {
    return _api.getLetter(letterId);
  }

  @override
  Future<DailyLetter> markRead(String letterId) {
    return _api.markRead(letterId);
  }
}

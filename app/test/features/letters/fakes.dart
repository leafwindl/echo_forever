import 'package:echo_app/features/letters/data/letters_repository.dart';
import 'package:echo_app/features/letters/domain/letter.dart';

class FakeLettersRepository implements LettersRepository {
  FakeLettersRepository({List<DailyLetter>? letters})
    : letters = List<DailyLetter>.of(letters ?? <DailyLetter>[letterFixture()]);

  List<DailyLetter> letters;
  Object? listError;
  Object? getError;
  Object? readError;
  int listCalls = 0;
  int getCalls = 0;
  int readCalls = 0;
  final List<String> fetchedIds = <String>[];
  final List<String> readIds = <String>[];

  @override
  Future<LetterListResult> listLetters({required int limit}) async {
    listCalls += 1;
    if (listError != null) throw listError!;
    final items = letters.take(limit).toList(growable: false);
    return LetterListResult(
      items: items,
      unreadCount: items.where((letter) => letter.status.isUnread).length,
    );
  }

  @override
  Future<DailyLetter> getLetter(String letterId) async {
    getCalls += 1;
    fetchedIds.add(letterId);
    if (getError != null) throw getError!;
    return letters.firstWhere((letter) => letter.letterId == letterId);
  }

  @override
  Future<DailyLetter> markRead(String letterId) async {
    readCalls += 1;
    readIds.add(letterId);
    if (readError != null) throw readError!;
    final index = letters.indexWhere((letter) => letter.letterId == letterId);
    final current = letters[index];
    final updated = DailyLetter(
      letterId: current.letterId,
      localDate: current.localDate,
      timezone: current.timezone,
      status: LetterStatus.read,
      subject: current.subject,
      content: current.content,
      publishedAt: current.publishedAt,
      readAt: '2026-08-04T09:00:00Z',
    );
    letters[index] = updated;
    return updated;
  }
}

DailyLetter letterFixture({
  String letterId = 'letter-1',
  String localDate = '2026-08-04',
  String timezone = 'Asia/Shanghai',
  LetterStatus status = LetterStatus.ready,
  String subject = '写给你的信',
  String content = '我们聊过的事，会在这里慢慢沉淀下来。',
  String? publishedAt = '2026-08-04T08:00:00Z',
  String? readAt,
}) {
  return DailyLetter(
    letterId: letterId,
    localDate: localDate,
    timezone: timezone,
    status: status,
    subject: subject,
    content: content,
    publishedAt: publishedAt,
    readAt: readAt,
  );
}

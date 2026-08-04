import 'package:echo_app/core/di/providers.dart';
import 'package:echo_app/core/storage/secure_store.dart';
import 'package:echo_app/features/stickers/domain/sticker.dart';
import 'package:echo_app/features/stickers/presentation/stickers_controller.dart';
import 'package:echo_app/features/stickers/presentation/stickers_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../support/fake_session_store.dart';
import '../fakes.dart';

void main() {
  testWidgets('picks an image and saves it through upload plus confirm', (
    tester,
  ) async {
    final repository = FakeStickersRepository(items: <StickerItem>[]);
    await _pumpStickers(
      tester,
      repository,
      picker: _FakeStickerImagePicker(
        const StickerUploadSelection(
          path: '/tmp/wave.png',
          name: 'wave.png',
          byteLength: 100,
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('choose-sticker-button')));
    await tester.pumpAndSettle();

    expect(repository.uploadedNames, <String>['wave.png']);
    expect(repository.confirmedIds, <String>['uploaded-1']);
    expect(find.text('已存进私人库'), findsOneWidget);
    expect(find.text('saved sticker'), findsOneWidget);
  });

  testWidgets('confirms delete before removing a user sticker', (tester) async {
    final repository = FakeStickersRepository(
      items: <StickerItem>[stickerFixture(description: 'delete me')],
    );
    await _pumpStickers(tester, repository);
    expect(find.text('delete me'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.delete_outline_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pumpAndSettle();

    expect(repository.deletedIds, <String>['stk-1']);
    expect(find.text('delete me'), findsNothing);
  });
}

Future<void> _pumpStickers(
  WidgetTester tester,
  FakeStickersRepository repository, {
  StickerImagePicker? picker,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        secureStoreProvider.overrideWithValue(FakeSessionStore(testSession())),
        stickersRepositoryProvider.overrideWithValue(repository),
        if (picker != null)
          stickerImagePickerProvider.overrideWithValue(picker),
      ],
      child: const MaterialApp(home: StickersPage()),
    ),
  );
  await tester.pumpAndSettle();
}

class _FakeStickerImagePicker implements StickerImagePicker {
  const _FakeStickerImagePicker(this.selection);

  final StickerUploadSelection? selection;

  @override
  Future<StickerUploadSelection?> pickSticker() async => selection;
}

import 'dart:async';

import 'package:echo_app/features/devices/presentation/device_network_connection_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('waits for hardware response before reporting success', (
    tester,
  ) async {
    final result = Completer<bool>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DeviceNetworkConnectionDialog(connect: () => result.future),
        ),
      ),
    );
    expect(find.text('正在等待硬件回应'), findsOneWidget);
    expect(find.text('检测通过，硬件已回应'), findsNothing);
    result.complete(true);
    await tester.pumpAndSettle();
    expect(find.text('检测通过，硬件已回应'), findsOneWidget);
  });

  testWidgets('failure fits a small viewport with large text', (tester) async {
    tester.view.physicalSize = const Size(320, 480);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(1.6)),
          child: child!,
        ),
        home: Scaffold(
          body: DeviceNetworkConnectionDialog(connect: () async => false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('未收到硬件回应'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

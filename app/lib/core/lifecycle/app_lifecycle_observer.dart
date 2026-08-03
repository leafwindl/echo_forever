import 'package:flutter/widgets.dart';

class AppLifecycleObserver with WidgetsBindingObserver {
  AppLifecycleObserver(this.onStateChanged);

  final ValueChanged<AppLifecycleState> onStateChanged;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    onStateChanged(state);
  }
}

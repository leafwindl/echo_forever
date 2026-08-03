import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void bootstrap(Widget app) {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(ProviderScope(child: app));
}

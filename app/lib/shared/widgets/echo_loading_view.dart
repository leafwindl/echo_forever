import 'package:flutter/material.dart';

class EchoLoadingView extends StatelessWidget {
  const EchoLoadingView({this.label = '加载中…', super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(label),
        ],
      ),
    );
  }
}

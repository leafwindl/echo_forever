abstract interface class Metrics {
  void timing(String name, Duration duration);
}

class NoopMetrics implements Metrics {
  const NoopMetrics();

  @override
  void timing(String name, Duration duration) {}
}

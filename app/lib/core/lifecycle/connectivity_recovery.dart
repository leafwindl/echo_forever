class ConnectivityRecovery {
  const ConnectivityRecovery();

  Future<void> recoverIdempotentReads() async {
    // Feature controllers register idempotent GET recovery in later milestones.
  }
}

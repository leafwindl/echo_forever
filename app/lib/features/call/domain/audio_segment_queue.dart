class AudioSegmentQueue {
  const AudioSegmentQueue._();

  /// Keeps the server order while rejecting schemes that just_audio should not
  /// open from remote call responses.
  static List<Uri> sanitize(List<String> urls) {
    return urls
        .map(Uri.tryParse)
        .whereType<Uri>()
        .where(
          (uri) =>
              uri.isAbsolute && (uri.scheme == 'http' || uri.scheme == 'https'),
        )
        .toList(growable: false);
  }
}

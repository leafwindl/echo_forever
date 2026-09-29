import 'dart:async';
import 'dart:typed_data';
import 'package:echo_app/core/errors/app_exception.dart';
import 'package:echo_app/core/errors/error_message_mapper.dart';
import 'package:echo_app/features/devices/data/speaker_people_api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

class SpeakerPeopleDialog extends ConsumerStatefulWidget {
  const SpeakerPeopleDialog({super.key, required this.deviceId});
  final String deviceId;
  @override
  ConsumerState<SpeakerPeopleDialog> createState() =>
      _SpeakerPeopleDialogState();
}

class _SpeakerPeopleDialogState extends ConsumerState<SpeakerPeopleDialog> {
  final _recorder = AudioRecorder();
  final _name = TextEditingController();
  final _audio = <int>[];
  StreamSubscription<Uint8List>? _subscription;
  Completer<void>? _done;
  Timer? _timer;
  Timer? _requestTimer;
  Map<String, dynamic>? _pending;
  Map<String, dynamic>? _calibration;
  bool _polling = false;
  List<SpeakerPerson> _people = [];
  SpeakerPerson? _person;
  bool _consent = false,
      _busy = false,
      _recording = false,
      _streamFailed = false;
  int _seconds = 0;
  String? _message;
  static const _prompts = [
    '今天我想和你聊聊最近发生的一件开心的事情。',
    '我平时喜欢听音乐，也喜欢和家人朋友一起散步。',
    '我希望每天都能发现一些新的、有意思的事情。',
    '周末有空的时候，我想给自己安排一次轻松的旅行。',
  ];
  SpeakerPeopleApi get _api => ref.read(speakerPeopleApiProvider);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _requestTimer = Timer.periodic(
      const Duration(seconds: 3),
      (_) => unawaited(_poll()),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    _requestTimer?.cancel();
    unawaited(_subscription?.cancel());
    unawaited(_recorder.dispose());
    _name.dispose();
    super.dispose();
  }

  String _error(Object error) => error is AppException
      ? error.detail ?? ErrorMessageMapper.toChinese(error)
      : '录音或设备操作失败，请重试';
  Future<void> _poll() async {
    if (_polling || _busy || _recording || !mounted) return;
    _polling = true;
    try {
      final pending = await _api.pending(widget.deviceId);
      final calibration = await _api.calibration(widget.deviceId);
      final people = await _api.list(widget.deviceId);
      if (mounted && !_busy && !_recording) {
        setState(() {
          _pending = pending;
          if (_calibration != null && calibration == null) {
            final calibratedId = _calibration!['person_id'] as String;
            final matches = people.where((item) => item.id == calibratedId);
            final wasCalibrated = _people.any(
              (item) => item.id == calibratedId && item.hardwareCalibrated,
            );
            _message = matches.isNotEmpty &&
                    matches.first.hardwareCalibrated &&
                    !wasCalibrated
                ? '硬件校准已通过独立验证'
                : '校准会话已结束，请查看 Echo 播报及校准状态';
          }
          _calibration = calibration;
          _people = people;
          final selectedId = _person?.id;
          if (selectedId != null) {
            final matches = people.where((item) => item.id == selectedId);
            _person = matches.isEmpty ? null : matches.first;
          }
        });
      }
    } on Object {
      // A failed refresh must not leave an old approval button actionable.
      if (mounted) setState(() => _pending = null);
    } finally {
      _polling = false;
    }
  }

  Future<void> _startCalibration(SpeakerPerson person) async {
    final consent = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('为${person.name}校准 Echo 声音'),
        content: const Text(
          '请确认由本人对 Echo 朗读 App 显示的四句话，并已同意保存声纹特征。前三段采样，第四段独立验证；录音不会保存。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('本人同意，开始'),
          ),
        ],
      ),
    );
    if (consent != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final session = await _api.startCalibration(widget.deviceId, person.id);
      if (mounted) {
        setState(() {
          _calibration = session;
          _message = '请由${person.name}对 Echo 朗读当前句子';
        });
      }
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancelCalibration() async {
    setState(() => _busy = true);
    try {
      await _api.cancelCalibration(widget.deviceId);
      if (mounted) {
        setState(() {
          _calibration = null;
          _message = '已取消本次校准';
        });
      }
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _removeCalibration(SpeakerPerson person) async {
    setState(() => _busy = true);
    try {
      await _api.removeCalibration(widget.deviceId, person.id);
      if (mounted) {
        setState(() => _message = '已删除硬件校准');
        await _load();
      }
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _approve(bool approved) async {
    if (_pending == null || _busy) return;
    final sessionId = _pending!['session_id'] as String;
    setState(() => _busy = true);
    try {
      await _api.approve(widget.deviceId, sessionId, approved);
      if (mounted) {
        setState(() {
          _pending = null;
          _message = approved ? '已批准，请对 Echo 说“开始录入”' : '已取消硬件录入';
        });
      }
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _load() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final people = await _api.list(widget.deviceId);
      if (mounted) setState(() => _people = people);
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _create() async {
    if (_busy || !_consent || _name.text.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final person = await _api.create(widget.deviceId, _name.text);
      if (mounted) setState(() => _person = person);
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() async {
    if (_busy || _recording) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      if (!await _recorder.hasPermission()) {
        if (mounted) setState(() => _message = '请允许 Echo Dev 使用麦克风');
        return;
      }
      _audio.clear();
      _seconds = 0;
      _streamFailed = false;
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: 16000,
          numChannels: 1,
          echoCancel: false,
          noiseSuppress: false,
          autoGain: false,
        ),
      );
      if (!mounted) {
        await _recorder.stop();
        return;
      }
      _done = Completer<void>();
      _subscription = stream.listen(
        (chunk) {
          final remaining = 384000 - _audio.length;
          if (remaining > 0) _audio.addAll(chunk.take(remaining));
        },
        onError: (Object error) {
          _streamFailed = true;
          if (!(_done?.isCompleted ?? true)) _done!.complete();
          unawaited(_stop());
        },
        onDone: () {
          if (!(_done?.isCompleted ?? true)) _done!.complete();
        },
      );
      setState(() => _recording = true);
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        setState(() => _seconds++);
        if (_seconds >= 10) unawaited(_stop());
      });
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    if (!_recording || _busy) return;
    _timer?.cancel();
    setState(() {
      _recording = false;
      _busy = true;
    });
    try {
      await _recorder.stop();
      await _done?.future.timeout(const Duration(seconds: 2));
      if (_streamFailed) {
        if (mounted) setState(() => _message = '录音中断，本段未保存，请重录');
        return;
      }
      if (_audio.length < 96000) {
        if (mounted) setState(() => _message = '请至少录制 3 秒');
        return;
      }
      if (!mounted) return;
      final person = await _api.sample(widget.deviceId, _person!.id, _audio);
      if (mounted) {
        setState(() {
          _person = person;
          _message = person.active ? '录入与独立验证已完成' : '本段已保存，请录制下一句';
        });
      }
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      await _subscription?.cancel();
      _subscription = null;
      _audio.clear();
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(SpeakerPerson person) async {
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('删除 ${person.name} 的声纹？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (approved != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await _api.delete(widget.deviceId, person.id);
    } on Object catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        await _load();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final person = _person;
    final index = (person?.sampleCount ?? 0).clamp(0, 3);
    return PopScope(
      canPop: !_busy && !_recording,
      child: AlertDialog(
        title: const Text('人员声纹'),
        content: SizedBox(
          width: 360,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_pending?['state'] == 'approval') ...[
                  Text('Echo 请求录入：${_pending!['display_name']}'),
                  Wrap(
                    spacing: 8,
                    children: [
                      TextButton(
                        onPressed: _busy ? null : () => _approve(false),
                        child: const Text('拒绝'),
                      ),
                      FilledButton(
                        onPressed: _busy ? null : () => _approve(true),
                        child: const Text('批准本次录入'),
                      ),
                    ],
                  ),
                ],
                if (person == null) ...[
                  for (final item in _people)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(item.name),
                      subtitle: Text(item.active ? '已录入' : '待完成录入'),
                      onTap: _busy
                          ? null
                          : () => setState(() {
                              _person = item;
                              _message = null;
                            }),
                      trailing: IconButton(
                        tooltip: '删除声纹',
                        icon: const Icon(Icons.delete_outline),
                        onPressed: _busy ? null : () => _delete(item),
                      ),
                    ),
                  TextField(
                    controller: _name,
                    maxLength: 40,
                    enabled: !_busy,
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(labelText: '新成员称呼'),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _consent,
                    onChanged: _busy
                        ? null
                        : (value) => setState(() => _consent = value ?? false),
                    title: const Text('录入者已同意保存声纹，用于称呼识别。原始录音处理后不保留，可随时删除声纹。'),
                  ),
                ] else ...[
                  Text(person.name),
                  const SizedBox(height: 12),
                  if (person.active) ...[
                    Text(person.hardwareCalibrated ? 'Echo 硬件声纹：已校准' : 'Echo 硬件声纹：未校准'),
                    if (_calibration?['person_id'] == person.id) ...[
                      const SizedBox(height: 12),
                      Text(
                        (_calibration!['sample_count'] as int) == 3
                            ? '独立验证 4 / 4'
                            : '硬件采样 ${(_calibration!['sample_count'] as int) + 1} / 3',
                      ),
                      const SizedBox(height: 8),
                      Text(_calibration!['prompt'] as String),
                      if ((_calibration!['error'] as String).isNotEmpty)
                        Text(_calibration!['error'] as String),
                      TextButton(
                        onPressed: _busy ? null : _cancelCalibration,
                        child: const Text('取消校准'),
                      ),
                    ] else ...[
                      FilledButton.icon(
                        onPressed: _busy || _calibration != null
                            ? null
                            : () => _startCalibration(person),
                        icon: const Icon(Icons.mic),
                        label: Text(person.hardwareCalibrated ? '重新校准' : '开始硬件校准'),
                      ),
                      if (person.hardwareCalibrated)
                        TextButton(
                          onPressed: _busy ? null : () => _removeCalibration(person),
                          child: const Text('删除硬件校准'),
                        ),
                    ],
                  ],
                  Text(
                    person.active
                        ? '声纹档案已就绪'
                        : index == 3
                        ? '独立验证'
                        : '录入 ${index + 1} / 3',
                  ),
                  if (!person.active) ...[
                    const SizedBox(height: 12),
                    Text(_prompts[index]),
                    const SizedBox(height: 12),
                    Text('$_seconds 秒'),
                  ],
                ],
                if (_busy)
                  const Padding(
                    padding: EdgeInsets.all(12),
                    child: LinearProgressIndicator(),
                  ),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_message!),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _busy || _recording
                ? null
                : () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
          if (person == null)
            FilledButton(
              onPressed: _busy || !_consent || _name.text.trim().isEmpty
                  ? null
                  : _create,
              child: const Text('新增成员'),
            )
          else if (person.active)
            TextButton(
              onPressed: _busy
                  ? null
                  : () {
                      setState(() {
                        _person = null;
                        _message = null;
                        _consent = false;
                        _name.clear();
                      });
                      unawaited(_load());
                    },
              child: const Text('返回人员列表'),
            )
          else
            FilledButton.icon(
              onPressed: _busy
                  ? null
                  : _recording
                  ? _stop
                  : _start,
              icon: Icon(_recording ? Icons.stop : Icons.mic),
              label: Text(_recording ? '结束录音' : '开始录音'),
            ),
        ],
      ),
    );
  }
}

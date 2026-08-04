import 'package:echo_app/features/persona/domain/persona.dart';
import 'package:echo_app/features/persona/presentation/persona_form_model.dart';
import 'package:flutter/material.dart';

const _presetTopics = <String>[
  '医疗建议',
  '情感分析',
  '家庭话题',
];

class PersonaEditorFields extends StatefulWidget {
  const PersonaEditorFields({
    required this.draft,
    required this.onChanged,
    this.showEnabledSwitch = true,
    super.key,
  });

  final PersonaDraft draft;
  final ValueChanged<PersonaDraft> onChanged;
  final bool showEnabledSwitch;

  @override
  State<PersonaEditorFields> createState() => _PersonaEditorFieldsState();
}

class _PersonaEditorFieldsState extends State<PersonaEditorFields> {
  late final TextEditingController _preferredNameController;
  late final TextEditingController _aboutUserController;
  late final TextEditingController _customTopicController;

  @override
  void initState() {
    super.initState();
    _preferredNameController = TextEditingController(
      text: widget.draft.preferredName,
    );
    _aboutUserController = TextEditingController(text: widget.draft.aboutUser);
    _customTopicController = TextEditingController();
  }

  @override
  void didUpdateWidget(covariant PersonaEditorFields oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncController(_preferredNameController, widget.draft.preferredName);
    _syncController(_aboutUserController, widget.draft.aboutUser);
  }

  @override
  void dispose() {
    _preferredNameController.dispose();
    _aboutUserController.dispose();
    _customTopicController.dispose();
    super.dispose();
  }

  void _syncController(TextEditingController controller, String value) {
    if (controller.text == value) {
      return;
    }
    controller.value = controller.value.copyWith(
      text: value,
      selection: TextSelection.collapsed(offset: value.length),
      composing: TextRange.empty,
    );
  }

  void _emit(PersonaDraft next) {
    widget.onChanged(next);
  }

  void _toggleTopic(String topic) {
    final avoidTopics = List<String>.of(widget.draft.avoidTopics);
    if (avoidTopics.contains(topic)) {
      avoidTopics.remove(topic);
    } else {
      if (avoidTopics.length >= maxAvoidTopics) {
        _showMessage('最多添加 $maxAvoidTopics 个话题');
        return;
      }
      avoidTopics.add(topic);
    }
    _emit(widget.draft.copyWith(avoidTopics: avoidTopics));
  }

  void _addCustomTopic() {
    final topic = _customTopicController.text.trim();
    if (topic.isEmpty) {
      return;
    }
    if (topic.length > maxAvoidTopicLength) {
      _showMessage('单个话题最多 $maxAvoidTopicLength 个字');
      return;
    }
    if (widget.draft.avoidTopics.any(
      (item) => item.toLowerCase() == topic.toLowerCase(),
    )) {
      _showMessage('这个话题已经添加过了');
      return;
    }
    if (widget.draft.avoidTopics.length >= maxAvoidTopics) {
      _showMessage('最多添加 $maxAvoidTopics 个话题');
      return;
    }
    final avoidTopics = <String>[...widget.draft.avoidTopics, topic];
    _emit(widget.draft.copyWith(avoidTopics: avoidTopics));
    _customTopicController.clear();
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final draft = widget.draft;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Section(
          title: '称呼',
          subtitle: '先告诉 Echo 怎么称呼你',
          child: TextField(
            controller: _preferredNameController,
            maxLength: maxPreferredNameLength,
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              hintText: '例如：小叶',
              counterText: '',
            ),
            onChanged: (value) => _emit(draft.copyWith(preferredName: value)),
          ),
        ),
        _Section(
          title: '聊天方式',
          child: _ChoiceGroup<PersonaReplyStyle>(
            value: draft.replyStyle,
            options: PersonaReplyStyle.values,
            labelFor: (value) => value.label,
            onSelected: (value) => _emit(draft.copyWith(replyStyle: value)),
          ),
        ),
        _Section(
          title: '回复长度',
          child: _ChoiceGroup<PersonaReplyLength>(
            value: draft.replyLength,
            options: PersonaReplyLength.values,
            labelFor: (value) => value.label,
            onSelected: (value) => _emit(draft.copyWith(replyLength: value)),
          ),
        ),
        _Section(
          title: '陪伴偏好',
          child: _ChoiceGroup<PersonaSupportMode>(
            value: draft.supportMode,
            options: PersonaSupportMode.values,
            labelFor: (value) => value.label,
            onSelected: (value) => _emit(draft.copyWith(supportMode: value)),
          ),
        ),
        _Section(
          title: '主动程度',
          child: _ChoiceGroup<PersonaProactivity>(
            value: draft.proactivity,
            options: PersonaProactivity.values,
            labelFor: (value) => value.label,
            onSelected: (value) => _emit(draft.copyWith(proactivity: value)),
          ),
        ),
        _Section(
          title: '关系节奏',
          child: _ChoiceGroup<RelationshipPace>(
            value: draft.relationshipPace,
            options: RelationshipPace.values,
            labelFor: (value) => value.label,
            onSelected: (value) =>
                _emit(draft.copyWith(relationshipPace: value)),
          ),
        ),
        _Section(
          title: '亲近表达',
          child: _ChoiceGroup<AffectionStyle>(
            value: draft.affectionStyle,
            options: AffectionStyle.values,
            labelFor: (value) => value.label,
            onSelected: (value) =>
                _emit(draft.copyWith(affectionStyle: value)),
          ),
        ),
        _Section(
          title: '避免话题',
          subtitle: '最多 $maxAvoidTopics 个，单个不超过 $maxAvoidTopicLength 个字',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  for (final topic in _presetTopics)
                    FilterChip(
                      selected: draft.avoidTopics.contains(topic),
                      label: Text(topic),
                      onSelected: (_) => _toggleTopic(topic),
                    ),
                  for (final topic in draft.avoidTopics
                      .where((topic) => !_presetTopics.contains(topic)))
                    FilterChip(
                      selected: true,
                      label: Text(topic),
                      onSelected: (_) => _toggleTopic(topic),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: <Widget>[
                  Expanded(
                    child: TextField(
                      controller: _customTopicController,
                      maxLength: maxAvoidTopicLength,
                      textInputAction: TextInputAction.done,
                      decoration: const InputDecoration(
                        hintText: '添加其他话题',
                        counterText: '',
                      ),
                      onSubmitted: (_) => _addCustomTopic(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: _addCustomTopic,
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('添加'),
                  ),
                ],
              ),
            ],
          ),
        ),
        _Section(
          title: '关于你',
          subtitle: '最多 $maxAboutUserLength 个字',
          child: TextField(
            controller: _aboutUserController,
            maxLength: maxAboutUserLength,
            minLines: 3,
            maxLines: 5,
            decoration: const InputDecoration(
              hintText: '例如：最近在准备面试，希望聊天时少一点追问',
            ),
            onChanged: (value) => _emit(draft.copyWith(aboutUser: value)),
          ),
        ),
        if (widget.showEnabledSwitch)
          _Section(
            title: '个性化开关',
            child: SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: const Text('启用个性化'),
              subtitle: Text(
                draft.enabled ? '当前已启用' : '关闭后使用默认交流方式',
                style: theme.textTheme.bodySmall,
              ),
              value: draft.enabled,
              onChanged: (value) => _emit(draft.copyWith(enabled: value)),
            ),
          ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.child,
    this.subtitle,
  });

  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(title, style: theme.textTheme.titleMedium),
          if (subtitle != null) ...<Widget>[
            const SizedBox(height: 4),
            Text(subtitle!, style: theme.textTheme.bodySmall),
          ],
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

class _ChoiceGroup<T extends Object> extends StatelessWidget {
  const _ChoiceGroup({
    required this.value,
    required this.options,
    required this.labelFor,
    required this.onSelected,
  });

  final T value;
  final List<T> options;
  final String Function(T value) labelFor;
  final ValueChanged<T> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: <Widget>[
        for (final option in options)
          ChoiceChip(
            label: Text(labelFor(option)),
            selected: value == option,
            onSelected: (_) => onSelected(option),
          ),
      ],
    );
  }
}

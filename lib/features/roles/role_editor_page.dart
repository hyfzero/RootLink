import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image/image.dart' as img;
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../../app/app_state.dart';
import '../../domain/models.dart';
import 'role_memory_draft.dart';

typedef RoleExportCallback = Future<void> Function(CompanionRole role);

class RoleEditorPage extends ConsumerStatefulWidget {
  const RoleEditorPage({super.key, this.role, this.onExport});
  final CompanionRole? role;
  final RoleExportCallback? onExport;

  @override
  ConsumerState<RoleEditorPage> createState() => _RoleEditorPageState();
}

class _RoleEditorPageState extends ConsumerState<RoleEditorPage> {
  static const _expressions = <String>[
    'neutral',
    'happy',
    'sad',
    'angry',
    'surprised',
  ];
  final _formKey = GlobalKey<FormState>();
  final _id = TextEditingController();
  final _name = TextEditingController();
  final _age = TextEditingController();
  final _birthday = TextEditingController();
  final _background = TextEditingController();
  final _intro = TextEditingController();
  final _traits = TextEditingController();
  final _interests = TextEditingController();
  final _tags = TextEditingController();
  late final RoleMemoryDraft _memoryDraft;
  CompanionRole? _workingRole;
  int _step = 0;
  bool _saving = false;
  String _gender = 'unknown';
  String _vocabulary = 'common';
  String _sentenceLength = 'varied';
  String _emojiUsage = 'sparse';
  double _exclamationRate = 0.1;
  double _questionRate = 0.15;
  double _ellipsisRate = 0.2;
  String _renderMode = 'original';
  double _tolerance = 50;
  double _feather = 0;
  RangeValues _horizontalCrop = const RangeValues(0, 1);
  RangeValues _verticalCrop = const RangeValues(0, 1);
  double _scale = 1;
  double _offsetX = 0;
  double _offsetY = 0;
  final Map<String, String> _pickedPortraits = <String, String>{};

  bool get _editing => widget.role != null;

  @override
  void initState() {
    super.initState();
    final role = widget.role;
    _workingRole = role;
    _memoryDraft = RoleMemoryDraft.fromJson(
      role?.memories ?? <String, dynamic>{},
    );
    if (role == null) return;
    final style = jsonMap(role.speakingStyle['base_style']);
    final edits = jsonMap(jsonMap(role.portraitEdits['edits'])['neutral']);
    _id.text = role.id;
    _name.text = role.name;
    _age.text = '${role.profile['age'] ?? ''}';
    _birthday.text = '${role.profile['birthday'] ?? ''}';
    _background.text = '${role.profile['background'] ?? ''}';
    _intro.text = role.intro;
    _traits.text = stringList(role.profile['personality_traits']).join('、');
    _interests.text = stringList(role.profile['interests']).join('、');
    _tags.text = role.tags.join('、');
    _gender = '${role.profile['gender'] ?? 'unknown'}';
    _vocabulary = '${style['vocabulary_level'] ?? 'common'}';
    _sentenceLength = '${style['sentence_length'] ?? 'varied'}';
    _emojiUsage = '${style['emoji_usage'] ?? 'sparse'}';
    _exclamationRate = jsonDouble(style['exclamation_rate'], 0.1).clamp(0, 1);
    _questionRate = jsonDouble(style['question_rate'], 0.15).clamp(0, 1);
    _ellipsisRate = jsonDouble(style['ellipsis_rate'], 0.2).clamp(0, 1);
    _renderMode = '${edits['render_mode'] ?? 'original'}';
    _tolerance = jsonDouble(edits['tolerance'], 50).clamp(0, 255);
    _feather = jsonDouble(edits['feather'], 0).clamp(0, 80);
    _scale = jsonDouble(edits['scale'], 1).clamp(0.3, 2);
    _offsetX = jsonDouble(edits['offset_x']).clamp(-200, 200);
    _offsetY = jsonDouble(edits['offset_y']).clamp(-200, 200);
  }

  @override
  void dispose() {
    for (final controller in <TextEditingController>[
      _id,
      _name,
      _age,
      _birthday,
      _background,
      _intro,
      _traits,
      _interests,
      _tags,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: const BackButton(),
      title: Text(_editing ? '编辑角色' : '创建角色'),
      actions: <Widget>[
        if (_editing && widget.onExport != null)
          IconButton(
            onPressed: _saving ? null : _export,
            tooltip: '保存并导出角色',
            icon: const Icon(Icons.ios_share_rounded),
          ),
        if (_editing)
          IconButton(
            onPressed: _saving ? null : _delete,
            tooltip: '删除角色',
            icon: const Icon(Icons.delete_outline_rounded),
          ),
        const SizedBox(width: 8),
      ],
    ),
    body: Form(
      key: _formKey,
      child: Column(
        children: <Widget>[
          _StepHeader(step: _step),
          Expanded(
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 200),
                  child: SingleChildScrollView(
                    key: ValueKey(_step),
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
                    child: _stepBody(),
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 14),
              child: Row(
                children: <Widget>[
                  if (_step > 0)
                    OutlinedButton(
                      onPressed: () => setState(() => _step--),
                      child: const Text('上一步'),
                    ),
                  const Spacer(),
                  FilledButton.icon(
                    onPressed: _saving ? null : _next,
                    icon: _saving
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Icon(
                            _step == 4
                                ? Icons.check_rounded
                                : Icons.arrow_forward_rounded,
                          ),
                    label: Text(_step == 4 ? '保存角色' : '下一步'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _stepBody() => switch (_step) {
    0 => _basicStep(),
    1 => _portraitStep(),
    2 => _personalityStep(),
    3 => _memoryStep(),
    _ => _styleStep(),
  };

  Widget _basicStep() => _EditorCard(
    title: '基础信息',
    subtitle: '这些内容决定角色在首页如何被识别。',
    children: <Widget>[
      TextFormField(
        controller: _id,
        enabled: !_editing,
        autocorrect: false,
        decoration: const InputDecoration(
          labelText: '角色 ID',
          hintText: '例如 luna',
        ),
        validator: (value) => RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value ?? '')
            ? null
            : '仅可使用字母、数字、下划线和短横线',
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _name,
        decoration: const InputDecoration(labelText: '名字'),
        validator: (value) => value?.trim().isEmpty == false ? null : '请输入名字',
      ),
      const SizedBox(height: 12),
      Row(
        children: <Widget>[
          Expanded(
            child: TextFormField(
              controller: _age,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '年龄'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _gender,
              decoration: const InputDecoration(labelText: '性别'),
              items: const <DropdownMenuItem<String>>[
                DropdownMenuItem(value: 'unknown', child: Text('未指定')),
                DropdownMenuItem(value: 'female', child: Text('女性')),
                DropdownMenuItem(value: 'male', child: Text('男性')),
                DropdownMenuItem(value: 'nonbinary', child: Text('非二元')),
              ],
              onChanged: (value) =>
                  setState(() => _gender = value ?? 'unknown'),
            ),
          ),
        ],
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _birthday,
        decoration: const InputDecoration(
          labelText: '生日',
          hintText: '例如 2 月 14 日',
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _intro,
        maxLines: 2,
        decoration: const InputDecoration(labelText: '一句话介绍'),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _tags,
        decoration: const InputDecoration(
          labelText: '标签',
          hintText: '用逗号或顿号分隔',
        ),
      ),
    ],
  );

  Widget _portraitStep() => _EditorCard(
    title: '角色立绘',
    subtitle: '可分别选择五种情绪。未选择的情绪会沿用现有立绘。',
    children: <Widget>[
      Wrap(
        spacing: 10,
        runSpacing: 10,
        children: _expressions.map((expression) {
          final picked = _pickedPortraits[expression];
          return SizedBox(
            width: 128,
            child: OutlinedButton(
              onPressed: () => _pickPortrait(expression),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  vertical: 18,
                  horizontal: 8,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(18),
                ),
              ),
              child: Column(
                children: <Widget>[
                  Icon(
                    picked == null
                        ? Icons.add_photo_alternate_outlined
                        : Icons.check_circle,
                  ),
                  const SizedBox(height: 8),
                  Text(_expressionLabel(expression)),
                  if (picked != null)
                    Text(
                      p.basename(picked),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
      const SizedBox(height: 20),
      SegmentedButton<String>(
        segments: const <ButtonSegment<String>>[
          ButtonSegment(value: 'original', label: Text('保留原图')),
          ButtonSegment(value: 'cutout', label: Text('背景抠图')),
        ],
        selected: <String>{_renderMode},
        onSelectionChanged: (value) =>
            setState(() => _renderMode = value.first),
      ),
      if (_renderMode == 'cutout') ...<Widget>[
        const SizedBox(height: 16),
        _LabeledSlider(
          label: '颜色容差',
          value: _tolerance,
          min: 0,
          max: 255,
          onChanged: (value) => setState(() => _tolerance = value),
        ),
        _LabeledSlider(
          label: '边缘柔化',
          value: _feather,
          min: 0,
          max: 80,
          onChanged: (value) => setState(() => _feather = value),
        ),
      ],
      _LabeledSlider(
        label: '缩放',
        value: _scale,
        min: 0.3,
        max: 2,
        fractionDigits: 2,
        onChanged: (value) => setState(() => _scale = value),
      ),
      const SizedBox(height: 4),
      Text('裁剪范围', style: Theme.of(context).textTheme.titleSmall),
      _CropRangeSlider(
        label: '左右',
        value: _horizontalCrop,
        onChanged: (value) => setState(() => _horizontalCrop = value),
      ),
      _CropRangeSlider(
        label: '上下',
        value: _verticalCrop,
        onChanged: (value) => setState(() => _verticalCrop = value),
      ),
      _LabeledSlider(
        label: '水平偏移',
        value: _offsetX,
        min: -200,
        max: 200,
        onChanged: (value) => setState(() => _offsetX = value),
      ),
      _LabeledSlider(
        label: '垂直偏移',
        value: _offsetY,
        min: -200,
        max: 200,
        onChanged: (value) => setState(() => _offsetY = value),
      ),
      Text(
        '抠图会综合图片四角估算背景色；图片处理会在独立 isolate 中执行。',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ],
  );

  Widget _personalityStep() => _EditorCard(
    title: '人格',
    subtitle: '清晰的人格描述能让长期对话更稳定。',
    children: <Widget>[
      TextFormField(
        controller: _traits,
        decoration: const InputDecoration(
          labelText: '性格特质',
          hintText: '冷静、耐心、幽默',
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _interests,
        decoration: const InputDecoration(
          labelText: '兴趣',
          hintText: '音乐、游戏、编程',
        ),
      ),
      const SizedBox(height: 12),
      TextFormField(
        controller: _background,
        minLines: 5,
        maxLines: 10,
        decoration: const InputDecoration(labelText: '背景故事'),
      ),
    ],
  );

  Widget _memoryStep() => _EditorCard(
    title: '角色记忆',
    subtitle: '按类型逐条编辑。日度与月度总结由系统维护，只在这里查看。',
    children: <Widget>[
      _editableMemoryCategory('episodic', '情节记忆', '角色经历过的事件与互动'),
      const SizedBox(height: 10),
      _editableMemoryCategory('preference', '偏好记忆', '喜好、厌恶与行为倾向'),
      const SizedBox(height: 10),
      _editableMemoryCategory('fact', '事实记忆', '稳定的背景信息与已知事实'),
      const SizedBox(height: 10),
      _summaryMemoryCategory('daily_summary', '日度总结', '按天生成的对话摘要'),
      const SizedBox(height: 10),
      _summaryMemoryCategory('monthly_summary', '月度总结', '按月归纳的长期摘要'),
    ],
  );

  Widget _editableMemoryCategory(String type, String title, String subtitle) {
    final entries = _memoryDraft.entries
        .where((entry) => entry.memoryType == type)
        .toList(growable: false);
    return _MemoryCategory(
      title: title,
      subtitle: subtitle,
      count: entries.length,
      initiallyExpanded: entries.isNotEmpty,
      children: <Widget>[
        if (entries.isEmpty) const _EmptyMemoryCategory(),
        for (final entry in entries) ...<Widget>[
          _EditableMemoryCard(
            key: ValueKey('${entry.id}-${_memoryDraft.entries.indexOf(entry)}'),
            entry: entry,
            onChanged: (updated) => setState(() {
              final index = _memoryDraft.entries.indexWhere(
                (candidate) => identical(candidate, entry),
              );
              if (index >= 0) _memoryDraft.entries[index] = updated;
            }),
            onDelete: () => setState(() => _memoryDraft.entries.remove(entry)),
          ),
          const SizedBox(height: 10),
        ],
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => _addMemory(type),
            icon: const Icon(Icons.add_rounded),
            label: const Text('添加记忆'),
          ),
        ),
      ],
    );
  }

  Widget _summaryMemoryCategory(String type, String title, String subtitle) {
    final summaries = _memoryDraft.summaries(type);
    return _MemoryCategory(
      title: title,
      subtitle: subtitle,
      count: summaries.length,
      initiallyExpanded: summaries.isNotEmpty,
      children: <Widget>[
        if (summaries.isEmpty) const _EmptyMemoryCategory(readOnly: true),
        for (final summary in summaries) ...<Widget>[
          _SummaryMemoryCard(summary: summary),
          const SizedBox(height: 10),
        ],
      ],
    );
  }

  void _addMemory(String type) {
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    setState(() {
      _memoryDraft.entries.add(
        MemoryEntry(
          id: 'mem_${const Uuid().v4()}',
          content: '',
          memoryType: type,
          timestamp: now,
          context: '角色设定',
        ),
      );
    });
  }

  Widget _styleStep() => _EditorCard(
    title: '语言风格',
    subtitle: '控制角色的常用词汇、句长和语气倾向。',
    children: <Widget>[
      DropdownButtonFormField<String>(
        initialValue: _vocabulary,
        decoration: const InputDecoration(labelText: '词汇级别'),
        items: const <DropdownMenuItem<String>>[
          DropdownMenuItem(value: 'simple', child: Text('简单')),
          DropdownMenuItem(value: 'common', child: Text('日常')),
          DropdownMenuItem(value: 'academic', child: Text('专业 / 学术')),
        ],
        onChanged: (value) => setState(() => _vocabulary = value ?? 'common'),
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        initialValue: _sentenceLength,
        decoration: const InputDecoration(labelText: '句子长度'),
        items: const <DropdownMenuItem<String>>[
          DropdownMenuItem(value: 'short', child: Text('简短')),
          DropdownMenuItem(value: 'varied', child: Text('长短交替')),
          DropdownMenuItem(value: 'long', child: Text('偏长')),
        ],
        onChanged: (value) =>
            setState(() => _sentenceLength = value ?? 'varied'),
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        initialValue: _emojiUsage,
        decoration: const InputDecoration(labelText: 'Emoji 使用'),
        items: const <DropdownMenuItem<String>>[
          DropdownMenuItem(value: 'none', child: Text('不用')),
          DropdownMenuItem(value: 'sparse', child: Text('偶尔')),
          DropdownMenuItem(value: 'frequent', child: Text('经常')),
        ],
        onChanged: (value) => setState(() => _emojiUsage = value ?? 'sparse'),
      ),
      const SizedBox(height: 12),
      _LabeledSlider(
        label: '感叹号倾向',
        value: _exclamationRate,
        min: 0,
        max: 1,
        fractionDigits: 2,
        onChanged: (value) => setState(() => _exclamationRate = value),
      ),
      _LabeledSlider(
        label: '提问倾向',
        value: _questionRate,
        min: 0,
        max: 1,
        fractionDigits: 2,
        onChanged: (value) => setState(() => _questionRate = value),
      ),
      _LabeledSlider(
        label: '省略号倾向',
        value: _ellipsisRate,
        min: 0,
        max: 1,
        fractionDigits: 2,
        onChanged: (value) => setState(() => _ellipsisRate = value),
      ),
    ],
  );

  Future<void> _pickPortrait(String expression) async {
    const group = XTypeGroup(
      label: '图片',
      extensions: <String>['png', 'jpg', 'jpeg', 'webp'],
    );
    final file = await openFile(acceptedTypeGroups: const <XTypeGroup>[group]);
    if (file != null) setState(() => _pickedPortraits[expression] = file.path);
  }

  void _next() {
    if (_step == 0 && !_formKey.currentState!.validate()) return;
    if (_step < 4) {
      setState(() => _step++);
      return;
    }
    _save();
  }

  Future<void> _save() async {
    await _saveRole(exportAfterSave: false);
  }

  Future<void> _export() async {
    await _saveRole(exportAfterSave: true);
  }

  Future<void> _saveRole({required bool exportAfterSave}) async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final role = await _persistRole();
      if (exportAfterSave) {
        await widget.onExport?.call(role);
      } else if (mounted) {
        Navigator.of(context).pop(role);
      }
    } catch (error) {
      if (mounted) {
        final action = exportAfterSave ? '保存或导出失败' : '保存失败';
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$action：$error')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<CompanionRole> _persistRole() async {
    final dependency = ref.read(dependenciesProvider);
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    final original = _workingRole;
    final id = _id.text.trim();
    final profile = <String, dynamic>{
      ...?original?.profile,
      'name': _name.text.trim(),
      'age': int.tryParse(_age.text.trim()) ?? _age.text.trim(),
      'gender': _gender,
      'birthday': _birthday.text.trim(),
      'personality_traits': _split(_traits.text),
      'interests': _split(_interests.text),
      'background': _background.text.trim(),
      'speaking_style': original?.profile['speaking_style'] ?? 'custom',
      'relationship_state':
          original?.profile['relationship_state'] ?? 'neutral',
    };
    final state = <String, dynamic>{
      ...?original?.state,
      'mood': original?.state['mood'] ?? 'neutral',
      'energy': original?.state['energy'] ?? 0.6,
      'affinity': original?.state['affinity'] ?? 0.5,
      'trust': original?.state['trust'] ?? 0.5,
      'updated_at': now,
    };
    final memories = _memoryDraft.toJson();
    final oldBase = jsonMap(original?.speakingStyle['base_style']);
    final style = <String, dynamic>{
      ...?original?.speakingStyle,
      'base_style': <String, dynamic>{
        ...oldBase,
        'vocabulary_level': _vocabulary,
        'sentence_length': _sentenceLength,
        'emoji_usage': _emojiUsage,
        'exclamation_rate': _exclamationRate,
        'question_rate': _questionRate,
        'ellipsis_rate': _ellipsisRate,
      },
      'influence_weight': original?.speakingStyle['influence_weight'] ?? 0.2,
    };
    final portraits = Map<String, dynamic>.from(
      original?.portraits ?? <String, dynamic>{},
    );
    final edits = jsonMap(original?.portraitEdits['edits']);
    for (final entry in _pickedPortraits.entries) {
      final source = File(entry.value);
      final bytes = await source.readAsBytes();
      final suffix = const Uuid().v4().substring(0, 8);
      final sourceRelative =
          'assets/portrait_sources/${entry.key}-$suffix${p.extension(source.path).toLowerCase()}';
      final processedRelative = 'assets/portraits/${entry.key}-$suffix.png';
      final sourceTarget = File(
        p.join(dependency.layout.brain(id).path, sourceRelative),
      );
      final processedTarget = File(
        p.join(dependency.layout.brain(id).path, processedRelative),
      );
      await sourceTarget.parent.create(recursive: true);
      await processedTarget.parent.create(recursive: true);
      await source.copy(sourceTarget.path);
      final processed = await dependency.portraits.process(
        source: bytes,
        renderMode: _renderMode,
        backgroundColor: _cornerColor(bytes),
        tolerance: _tolerance.round(),
        feather: _feather.round(),
        cropBox: _cropBox(bytes),
        scale: _scale,
        offsetX: _offsetX.round(),
        offsetY: _offsetY.round(),
        canvasWidth: 390,
        canvasHeight: 520,
      );
      await processedTarget.writeAsBytes(processed, flush: true);
      portraits[entry.key] = processedRelative;
      edits[entry.key] = <String, dynamic>{
        ...jsonMap(edits[entry.key]),
        'source_path': sourceRelative,
        'processed_path': processedRelative,
        'render_mode': _renderMode,
        'background_color': _cornerColor(bytes),
        'tolerance': _tolerance.round(),
        'feather': _feather.round(),
        'crop_box': _cropBox(bytes),
        'scale': _scale,
        'offset_x': _offsetX.round(),
        'offset_y': _offsetY.round(),
      };
    }
    final neutral =
        '${portraits['neutral'] ?? original?.standingImagePath ?? ''}';
    final ui = <String, dynamic>{
      ...?original?.ui,
      'type': original?.type ?? 'Custom',
      'tags': _split(_tags.text),
      'intro': _intro.text.trim(),
      'accent_color': original?.accentColor ?? '#5578E7',
      'avatar': neutral,
      'standing_image': neutral,
      'portraits': portraits,
      'last_message': original?.lastMessage ?? '',
      'last_time': original?.lastTime ?? '',
    };
    final role = CompanionRole(
      id: id,
      profile: profile,
      state: state,
      memories: memories,
      speakingStyle: style,
      ui: ui,
      config:
          original?.config ??
          <String, dynamic>{
            'response': <String, dynamic>{
              'max_tokens': 2000,
              'max_sentences': 5,
            },
          },
      portraitEdits: <String, dynamic>{
        ...?original?.portraitEdits,
        'version': original?.portraitEdits['version'] ?? 1,
        'layout':
            original?.portraitEdits['layout'] ??
            <String, dynamic>{'canvas_width': 390, 'canvas_height': 520},
        'edits': edits,
      },
    );
    await ref.read(rolesProvider.notifier).save(role);
    _workingRole = role;
    _pickedPortraits.clear();
    return role;
  }

  List<int>? _cropBox(List<int> bytes) {
    if (_horizontalCrop.start == 0 &&
        _horizontalCrop.end == 1 &&
        _verticalCrop.start == 0 &&
        _verticalCrop.end == 1) {
      return null;
    }
    final decoded = img.decodeImage(Uint8List.fromList(bytes));
    if (decoded == null) return null;
    return <int>[
      (decoded.width * _horizontalCrop.start).round(),
      (decoded.height * _verticalCrop.start).round(),
      (decoded.width * _horizontalCrop.end).round(),
      (decoded.height * _verticalCrop.end).round(),
    ];
  }

  List<int> _cornerColor(List<int> bytes) {
    final image = img.decodeImage(Uint8List.fromList(bytes));
    if (image == null || image.width == 0 || image.height == 0) {
      return const <int>[255, 255, 255];
    }
    final sampleWidth = (image.width * 0.04).round().clamp(1, 12);
    final sampleHeight = (image.height * 0.04).round().clamp(1, 12);
    var red = 0.0;
    var green = 0.0;
    var blue = 0.0;
    var count = 0;
    for (final origin in <(int, int)>[
      (0, 0),
      (image.width - sampleWidth, 0),
      (0, image.height - sampleHeight),
      (image.width - sampleWidth, image.height - sampleHeight),
    ]) {
      for (var y = origin.$2; y < origin.$2 + sampleHeight; y++) {
        for (var x = origin.$1; x < origin.$1 + sampleWidth; x++) {
          final pixel = image.getPixel(x, y);
          final alpha = pixel.aNormalized;
          red += pixel.r * alpha + 255 * (1 - alpha);
          green += pixel.g * alpha + 255 * (1 - alpha);
          blue += pixel.b * alpha + 255 * (1 - alpha);
          count++;
        }
      }
    }
    return <int>[
      (red / count).round().clamp(0, 255),
      (green / count).round().clamp(0, 255),
      (blue / count).round().clamp(0, 255),
    ];
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除这个角色？'),
        content: const Text('角色目录会从本机移除。至少需要保留一个角色。'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true || widget.role == null) return;
    try {
      await ref.read(rolesProvider.notifier).delete(widget.role!.id);
      if (mounted) Navigator.pop(context);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$error')));
      }
    }
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({required this.step});
  final int step;
  static const labels = <String>['基础', '立绘', '人格', '记忆', '风格'];

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 8, 20, 18),
    child: Row(
      children: List<Widget>.generate(labels.length, (index) {
        final active = index <= step;
        return Expanded(
          child: Column(
            children: <Widget>[
              Container(
                height: 4,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  color: active
                      ? Theme.of(context).colorScheme.primary
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                labels[index],
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: index == step
                      ? Theme.of(context).colorScheme.primary
                      : null,
                ),
              ),
            ],
          ),
        );
      }),
    ),
  );
}

class _MemoryCategory extends StatelessWidget {
  const _MemoryCategory({
    required this.title,
    required this.subtitle,
    required this.count,
    required this.initiallyExpanded,
    required this.children,
  });

  final String title;
  final String subtitle;
  final int count;
  final bool initiallyExpanded;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainer,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
    ),
    child: ExpansionTile(
      initiallyExpanded: initiallyExpanded,
      shape: const Border(),
      collapsedShape: const Border(),
      tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      title: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              title,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              child: Text('$count'),
            ),
          ),
        ],
      ),
      subtitle: Text(subtitle),
      children: children,
    ),
  );
}

class _EditableMemoryCard extends StatelessWidget {
  const _EditableMemoryCard({
    super.key,
    required this.entry,
    required this.onChanged,
    required this.onDelete,
  });

  final MemoryEntry entry;
  final ValueChanged<MemoryEntry> onChanged;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
    ),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        children: <Widget>[
          TextFormField(
            initialValue: entry.content,
            minLines: 2,
            maxLines: 5,
            decoration: const InputDecoration(labelText: '内容'),
            onChanged: (value) => onChanged(entry.copyWith(content: value)),
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: entry.memoryType,
                  decoration: const InputDecoration(labelText: '类型'),
                  items: editableMemoryTypes
                      .map(
                        (type) => DropdownMenuItem<String>(
                          value: type,
                          child: Text(_memoryTypeLabel(type)),
                        ),
                      )
                      .toList(growable: false),
                  onChanged: (value) {
                    if (value != null) {
                      onChanged(entry.copyWith(memoryType: value));
                    }
                  },
                ),
              ),
              const SizedBox(width: 10),
              IconButton(
                onPressed: onDelete,
                tooltip: '删除这条记忆',
                icon: const Icon(Icons.delete_outline_rounded),
              ),
            ],
          ),
          const SizedBox(height: 10),
          TextFormField(
            initialValue: entry.context,
            decoration: const InputDecoration(
              labelText: '上下文',
              hintText: '例如：角色设定、某次对话',
            ),
            onChanged: (value) => onChanged(entry.copyWith(context: value)),
          ),
          const SizedBox(height: 10),
          Row(
            children: <Widget>[
              const Text('重要度'),
              Expanded(
                child: Slider.adaptive(
                  value: entry.importance.clamp(0, 2),
                  min: 0,
                  max: 2,
                  divisions: 20,
                  onChanged: (value) =>
                      onChanged(entry.copyWith(importance: value)),
                ),
              ),
              SizedBox(
                width: 30,
                child: Text(entry.importance.toStringAsFixed(1)),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _SummaryMemoryCard extends StatelessWidget {
  const _SummaryMemoryCard({required this.summary});
  final Map<String, dynamic> summary;

  @override
  Widget build(BuildContext context) {
    final content = '${summary['summary_text'] ?? summary['content'] ?? ''}';
    final contextText = '${summary['context'] ?? ''}'.trim();
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  Icons.lock_outline_rounded,
                  size: 16,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: 6),
                Text('只读', style: Theme.of(context).textTheme.labelMedium),
              ],
            ),
            const SizedBox(height: 8),
            SelectableText(content.isEmpty ? '（无摘要内容）' : content),
            if (contextText.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                contextText,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EmptyMemoryCategory extends StatelessWidget {
  const _EmptyMemoryCategory({this.readOnly = false});
  final bool readOnly;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 10),
    child: Text(
      readOnly ? '暂无系统摘要' : '这个分类还没有记忆',
      style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
    ),
  );
}

String _memoryTypeLabel(String type) => switch (type) {
  'episodic' => '情节记忆',
  'preference' => '偏好记忆',
  'fact' => '事实记忆',
  _ => type,
};

class _EditorCard extends StatelessWidget {
  const _EditorCard({
    required this.title,
    required this.subtitle,
    required this.children,
  });
  final String title;
  final String subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 6),
          Text(
            subtitle,
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 22),
          ...children,
        ],
      ),
    ),
  );
}

class _LabeledSlider extends StatelessWidget {
  const _LabeledSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.fractionDigits = 0,
  });
  final String label;
  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onChanged;
  final int fractionDigits;

  @override
  Widget build(BuildContext context) => Column(
    children: <Widget>[
      Row(
        children: <Widget>[
          Text(label),
          const Spacer(),
          Text(value.toStringAsFixed(fractionDigits)),
        ],
      ),
      Slider.adaptive(value: value, min: min, max: max, onChanged: onChanged),
    ],
  );
}

class _CropRangeSlider extends StatelessWidget {
  const _CropRangeSlider({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final RangeValues value;
  final ValueChanged<RangeValues> onChanged;

  @override
  Widget build(BuildContext context) => Column(
    children: <Widget>[
      Row(
        children: <Widget>[
          Text(label),
          const Spacer(),
          Text(
            '${(value.start * 100).round()}% – ${(value.end * 100).round()}%',
          ),
        ],
      ),
      RangeSlider(
        values: value,
        min: 0,
        max: 1,
        divisions: 100,
        labels: RangeLabels(
          '${(value.start * 100).round()}%',
          '${(value.end * 100).round()}%',
        ),
        onChanged: (next) {
          if (next.end - next.start >= 0.05) onChanged(next);
        },
      ),
    ],
  );
}

List<String> _split(String source) => source
    .split(RegExp(r'[,，、\n]+'))
    .map((item) => item.trim())
    .where((item) => item.isNotEmpty)
    .toList();

String _expressionLabel(String value) => switch (value) {
  'neutral' => '平静',
  'happy' => '开心',
  'sad' => '难过',
  'angry' => '生气',
  'surprised' => '惊讶',
  _ => value,
};

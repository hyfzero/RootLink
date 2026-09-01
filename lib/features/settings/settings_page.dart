import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/app_state.dart';
import '../../data/file_settings_repository.dart';
import '../../domain/models.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key, required this.onImport});

  final VoidCallback onImport;

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late UiSettings _draft;
  late final TextEditingController _apiKey;
  late final TextEditingController _userName;
  bool _obscureKey = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _draft = ref.read(settingsProvider);
    _apiKey = TextEditingController(text: _draft.apiKey);
    _userName = TextEditingController(text: _draft.userName);
  }

  @override
  void dispose() {
    _apiKey.dispose();
    _userName.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('设置'),
      actions: <Widget>[
        Padding(
          padding: const EdgeInsets.only(right: 16),
          child: FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? '保存中…' : '保存'),
          ),
        ),
      ],
    ),
    body: Align(
      alignment: Alignment.topCenter,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 40),
        children: <Widget>[
          _Section(
            title: '外观',
            child: SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: const Text('深色主题'),
              subtitle: const Text('在中性浅色与深色界面之间切换'),
              value: _draft.isDark,
              onChanged: (value) => setState(() {
                _draft = _draft.copyWith(isDark: value);
                ref.read(settingsProvider.notifier).preview(_draft);
              }),
            ),
          ),
          const SizedBox(height: 16),
          _Section(
            title: '对话模型',
            child: Column(
              children: <Widget>[
                DropdownButtonFormField<String>(
                  initialValue: _draft.modelProvider,
                  decoration: const InputDecoration(labelText: '服务商'),
                  items: <String>{...providerModels.keys, _draft.modelProvider}
                      .map(
                        (provider) => DropdownMenuItem(
                          value: provider,
                          child: Text(_providerLabel(provider)),
                        ),
                      )
                      .toList(),
                  onChanged: (provider) {
                    if (provider == null) return;
                    setState(() {
                      _draft = _draft.copyWith(
                        modelProvider: provider,
                        modelName: providerModels[provider]!.first,
                        apiKey: '',
                      );
                      _apiKey.clear();
                    });
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  key: ValueKey('${_draft.modelProvider}:${_draft.modelName}'),
                  initialValue: _draft.modelName,
                  decoration: const InputDecoration(labelText: '模型'),
                  items:
                      <String>{
                            ...providerModels[_draft.modelProvider] ??
                                <String>[],
                            _draft.modelName,
                          }
                          .map(
                            (model) => DropdownMenuItem(
                              value: model,
                              child: Text(model),
                            ),
                          )
                          .toList(),
                  onChanged: (model) {
                    if (model != null) {
                      setState(
                        () => _draft = _draft.copyWith(modelName: model),
                      );
                    }
                  },
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _apiKey,
                  obscureText: _obscureKey,
                  autocorrect: false,
                  decoration: InputDecoration(
                    labelText: _draft.modelProvider == 'ollama'
                        ? 'API 密钥（可选）'
                        : 'API 密钥',
                    suffixIcon: IconButton(
                      onPressed: () =>
                          setState(() => _obscureKey = !_obscureKey),
                      icon: Icon(
                        _obscureKey
                            ? Icons.visibility_outlined
                            : Icons.visibility_off_outlined,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Row(
                  children: <Widget>[
                    const Text('生成质量'),
                    const Spacer(),
                    Text('${_draft.tokenQuality}%'),
                  ],
                ),
                Slider.adaptive(
                  value: _draft.tokenQuality.toDouble(),
                  min: 0,
                  max: 100,
                  divisions: 20,
                  label: '${_draft.tokenQuality}%',
                  onChanged: (value) => setState(() {
                    _draft = _draft.copyWith(tokenQuality: value.round());
                  }),
                ),
                Text(
                  '质量越高，允许模型生成的内容越长。',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _Section(
            title: '你的信息',
            child: TextField(
              controller: _userName,
              decoration: const InputDecoration(
                labelText: '称呼',
                hintText: '角色如何称呼你',
              ),
            ),
          ),
          const SizedBox(height: 16),
          _Section(
            title: '本地数据',
            child: Column(
              children: <Widget>[
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.file_download_outlined),
                  title: const Text('导入角色包'),
                  subtitle: const Text('支持 amadues.character-package v1'),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: widget.onImport,
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'RootLink 0.2.0 · Flutter / Dart\n角色、对话和 API 配置均保存在本机。',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    ),
  );

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      _draft = _draft.copyWith(
        apiKey: _apiKey.text.trim(),
        userName: _userName.text.trim().isEmpty ? '用户' : _userName.text.trim(),
      );
      await ref.read(settingsProvider.notifier).save(_draft);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('设置已保存')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('保存失败：$error')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child});
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            title,
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    ),
  );
}

String _providerLabel(String value) => switch (value) {
  'minimax' => 'MiniMax',
  'deepseek' => 'DeepSeek',
  'qwen' => 'Qwen 通义千问',
  'glm' => 'GLM 智谱',
  'openai' => 'OpenAI',
  'anthropic' => 'Anthropic',
  'moonshot' || 'kimi' => 'Moonshot / Kimi',
  'ollama' => 'Ollama（本地）',
  'openrouter' => 'OpenRouter',
  _ => value,
};

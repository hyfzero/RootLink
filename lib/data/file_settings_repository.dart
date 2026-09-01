import 'dart:io';

import 'package:path/path.dart' as p;

import '../domain/models.dart';
import '../domain/repositories.dart';
import 'storage_layout.dart';

const providerModels = <String, List<String>>{
  'minimax': <String>['MiniMax-M2.5'],
  'deepseek': <String>['deepseek-v4-flash', 'deepseek-v4-pro'],
  'qwen': <String>['qwen3.6-flash', 'qwen3.7-max'],
  'glm': <String>['glm-5.1', 'glm-4.7', 'glm-4.5', 'glm-4-flash-250414'],
  'openai': <String>['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'],
  'anthropic': <String>['claude-opus-4-6', 'claude-sonnet-4-20250514'],
  'moonshot': <String>['kimi-k2.5', 'kimi-k2.5-32k'],
  'kimi': <String>['kimi-k2.5', 'kimi-k2.5-32k'],
  'ollama': <String>['llama3.1:8b', 'qwen2.5:14b'],
  'openrouter': <String>['auto', 'openrouter/hunter-alpha'],
};

const providerBaseUrls = <String, String>{
  'minimax': 'https://api.minimaxi.com/v1',
  'deepseek': 'https://api.deepseek.com',
  'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  'glm': 'https://open.bigmodel.cn/api/paas/v4',
  'openai': 'https://api.openai.com/v1',
  'anthropic': 'https://api.anthropic.com/v1',
  'moonshot': 'https://api.moonshot.cn/v1',
  'kimi': 'https://api.moonshot.cn/v1',
  'ollama': 'http://localhost:11434/v1',
  'openrouter': 'https://openrouter.ai/api/v1',
};

class FileSettingsRepository implements SettingsRepository {
  FileSettingsRepository(this.layout);

  final StorageLayout layout;
  File get _uiFile => File(p.join(layout.config.path, 'ui_settings.json'));
  File get _modelsFile => File(p.join(layout.config.path, 'models.json'));

  @override
  Future<UiSettings> load() async {
    final ui = await layout.json.readMap(_uiFile);
    final models = await layout.json.readMap(_modelsFile);
    final provider =
        (ui['model_provider'] ?? models['default_provider'] ?? 'minimax')
            .toString();
    final configuredModels =
        providerModels[provider] ?? providerModels['minimax']!;
    final requestedModel =
        (ui['model_name'] ?? models['default_model'] ?? configuredModels.first)
            .toString();
    final model = requestedModel.trim().isEmpty
        ? configuredModels.first
        : requestedModel;
    final providerData = jsonMap(jsonMap(models['providers'])[provider]);
    final extras = Map<String, dynamic>.from(ui)
      ..removeWhere(
        (key, _) => const {
          'is_dark',
          'token_quality',
          'model_provider',
          'model_name',
          'user_name',
          'user_avatar_path',
        }.contains(key),
      );
    return UiSettings(
      isDark: ui['is_dark'] == true,
      tokenQuality: jsonInt(ui['token_quality'], 50).clamp(0, 100),
      modelProvider: provider,
      modelName: model,
      apiKey: (providerData['api_key'] ?? '').toString(),
      userName: (ui['user_name'] ?? '用户').toString(),
      userAvatarPath: ui['user_avatar_path']?.toString(),
      extraFields: extras,
    );
  }

  @override
  Future<void> save(UiSettings settings) async {
    final ui = <String, dynamic>{
      ...settings.extraFields,
      'is_dark': settings.isDark,
      'token_quality': settings.tokenQuality.clamp(0, 100),
      'model_provider': settings.modelProvider,
      'model_name': settings.modelName,
      'user_name': settings.userName,
      'user_avatar_path': settings.userAvatarPath,
    };
    final models = await layout.json.readMap(_modelsFile);
    final providers = jsonMap(models['providers']);
    final existing = jsonMap(providers[settings.modelProvider]);
    providers[settings.modelProvider] = <String, dynamic>{
      ...existing,
      'base_url':
          existing['base_url'] ??
          providerBaseUrls[settings.modelProvider] ??
          '',
      'api_type':
          existing['api_type'] ??
          (settings.modelProvider == 'anthropic'
              ? 'anthropic-messages'
              : 'openai'),
      'auth_header': existing['auth_header'] ?? true,
      'api_key': settings.apiKey.trim(),
    };
    models
      ..['version'] = models['version'] ?? '1.0'
      ..['updated_at'] = DateTime.now().toIso8601String()
      ..['providers'] = providers
      ..['default_provider'] = settings.modelProvider
      ..['default_model'] = settings.modelName;
    await layout.json.writeMap(_modelsFile, models);
    await layout.json.writeMap(_uiFile, ui);
  }

  @override
  Future<ModelConfig> activeModel() async {
    final settings = await load();
    final models = await layout.json.readMap(_modelsFile);
    final provider = jsonMap(
      jsonMap(models['providers'])[settings.modelProvider],
    );
    final key = (provider['api_key'] ?? settings.apiKey).toString().trim();
    if (key.isEmpty && settings.modelProvider != 'ollama') {
      throw StateError('请先在设置中填写 API 密钥');
    }
    final headers = jsonMap(
      provider['headers'],
    ).map((key, value) => MapEntry(key, value.toString()));
    return ModelConfig(
      provider: settings.modelProvider,
      model: settings.modelName,
      apiKey: key,
      baseUrl:
          (provider['base_url'] ??
                  providerBaseUrls[settings.modelProvider] ??
                  '')
              .toString(),
      maxTokens: _qualityTokens(settings.tokenQuality),
      supportsThinking: const {
        'MiniMax-M2.5',
        'qwen3.7-max',
        'glm-5.1',
        'glm-4.7',
        'glm-4.5',
      }.contains(settings.modelName),
      apiType: (provider['api_type'] ?? 'openai').toString(),
      headers: headers,
    );
  }

  int _qualityTokens(int quality) =>
      512 + (quality.clamp(0, 100) * 35.84).round();
}

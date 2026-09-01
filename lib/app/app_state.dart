import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../data/conversation_maintenance_service.dart';
import '../data/file_role_repository.dart';
import '../data/file_session_repository.dart';
import '../data/file_settings_repository.dart';
import '../data/http_chat_provider.dart';
import '../data/image_portrait_processor.dart';
import '../data/storage_layout.dart';
import '../data/zip_character_package_service.dart';
import '../domain/models.dart';
import '../domain/rootlink_agent_runtime.dart';

class AppDependencies {
  AppDependencies(this.layout)
    : roles = FileRoleRepository(layout),
      sessions = FileSessionRepository(layout),
      settings = FileSettingsRepository(layout),
      packages = ZipCharacterPackageService(layout),
      portraits = const ImagePortraitProcessor(),
      maintenance = ConversationMaintenanceService(layout);

  final StorageLayout layout;
  final FileRoleRepository roles;
  final FileSessionRepository sessions;
  final FileSettingsRepository settings;
  final ZipCharacterPackageService packages;
  final ImagePortraitProcessor portraits;
  final ConversationMaintenanceService maintenance;
}

final dependenciesProvider = Provider<AppDependencies>(
  (ref) =>
      throw StateError('AppDependencies must be overridden during startup'),
);

class SettingsController extends StateNotifier<UiSettings> {
  SettingsController(this._dependencies, super.state);

  final AppDependencies _dependencies;

  void preview(UiSettings value) => state = value;

  Future<void> save(UiSettings value) async {
    state = value;
    await _dependencies.settings.save(value);
  }

  Future<void> toggleTheme() async {
    final previous = state;
    final next = state.copyWith(isDark: !state.isDark);
    state = next;
    try {
      await _dependencies.settings.save(next);
    } catch (_) {
      state = previous;
      rethrow;
    }
  }
}

final settingsProvider = StateNotifierProvider<SettingsController, UiSettings>(
  (ref) =>
      throw StateError('SettingsController must be overridden during startup'),
);

class RolesState {
  const RolesState({
    this.roles = const <CompanionRole>[],
    this.selectedId,
    this.isLoading = false,
    this.error,
  });

  final List<CompanionRole> roles;
  final String? selectedId;
  final bool isLoading;
  final String? error;

  CompanionRole? get selected {
    for (final role in roles) {
      if (role.id == selectedId) return role;
    }
    return roles.isEmpty ? null : roles.first;
  }

  RolesState copyWith({
    List<CompanionRole>? roles,
    String? selectedId,
    bool? isLoading,
    String? error,
    bool clearError = false,
  }) => RolesState(
    roles: roles ?? this.roles,
    selectedId: selectedId ?? this.selectedId,
    isLoading: isLoading ?? this.isLoading,
    error: clearError ? null : error ?? this.error,
  );
}

class RolesController extends StateNotifier<RolesState> {
  RolesController(this._dependencies, List<CompanionRole> initial)
    : super(
        RolesState(
          roles: initial,
          selectedId: initial.isEmpty ? null : initial.first.id,
        ),
      );

  final AppDependencies _dependencies;

  void select(String id) => state = state.copyWith(selectedId: id);

  Future<void> refresh({String? selectId}) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final roles = await _dependencies.roles.listRoles();
      final current = selectId ?? state.selectedId;
      state = RolesState(
        roles: roles,
        selectedId: roles.any((role) => role.id == current)
            ? current
            : roles.firstOrNull?.id,
      );
    } catch (error) {
      state = state.copyWith(isLoading: false, error: '$error');
    }
  }

  Future<void> save(CompanionRole role) async {
    await _dependencies.roles.saveRole(role);
    await refresh(selectId: role.id);
  }

  Future<void> delete(String id) async {
    await _dependencies.roles.deleteRole(id);
    await refresh();
  }
}

final rolesProvider = StateNotifierProvider<RolesController, RolesState>(
  (ref) =>
      throw StateError('RolesController must be overridden during startup'),
);

class ChatState {
  const ChatState({
    this.messages = const <ChatMessage>[],
    this.isLoading = true,
    this.isStreaming = false,
    this.reasoning = '',
    this.emotion = 'neutral',
    this.error,
  });

  final List<ChatMessage> messages;
  final bool isLoading;
  final bool isStreaming;
  final String reasoning;
  final String emotion;
  final String? error;

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    bool? isStreaming,
    String? reasoning,
    String? emotion,
    String? error,
    bool clearError = false,
  }) => ChatState(
    messages: messages ?? this.messages,
    isLoading: isLoading ?? this.isLoading,
    isStreaming: isStreaming ?? this.isStreaming,
    reasoning: reasoning ?? this.reasoning,
    emotion: emotion ?? this.emotion,
    error: clearError ? null : error ?? this.error,
  );
}

class ChatController extends StateNotifier<ChatState> {
  ChatController(this._dependencies, this.roleId) : super(const ChatState()) {
    unawaited(load());
  }

  static const _uuid = Uuid();
  final AppDependencies _dependencies;
  final String roleId;
  HttpChatProvider? _activeProvider;
  bool _cancelRequested = false;

  Future<void> load() async {
    try {
      final session = await _dependencies.sessions.loadToday(roleId);
      state = ChatState(messages: session.messages, isLoading: false);
    } catch (error) {
      state = ChatState(isLoading: false, error: '$error');
    }
  }

  Future<void> send(String rawText) async {
    final text = rawText.trim();
    if (text.isEmpty || state.isStreaming) return;
    _cancelRequested = false;
    final role = await _dependencies.roles.getRole(roleId);
    if (role == null) {
      state = state.copyWith(error: '角色不存在');
      return;
    }
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    final user = ChatMessage(
      id: _uuid.v4(),
      role: 'user',
      content: text,
      timestamp: now,
      tokenCount: estimateTokens(text),
    );
    final history = state.messages;
    final assistantId = _uuid.v4();
    final assistant = ChatMessage(
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: now + 0.001,
      isStreaming: true,
    );
    state = state.copyWith(
      messages: <ChatMessage>[...history, user, assistant],
      isStreaming: true,
      reasoning: '',
      clearError: true,
    );
    await _dependencies.sessions.append(roleId, user);
    var response = '';
    try {
      final model = await _dependencies.settings.activeModel();
      final provider = HttpChatProvider(model);
      _activeProvider = provider;
      final runtime = RootLinkAgentRuntime(provider: provider, model: model);
      var reasoning = '';
      await for (final event in runtime.send(
        role: role,
        message: text,
        history: history,
      )) {
        if (_cancelRequested) break;
        if (event.type == ChatStreamEventType.delta) response += event.text;
        if (event.type == ChatStreamEventType.reasoning) {
          reasoning += event.text;
        }
        state = state.copyWith(
          messages: _replaceAssistant(assistantId, response, streaming: true),
          reasoning: reasoning,
        );
      }
      if (_cancelRequested) {
        await _finishInterrupted(assistantId, response, now);
        return;
      }
      if (response.trim().isEmpty) throw StateError('模型没有返回内容');
      final completed = ChatMessage(
        id: assistantId,
        role: 'assistant',
        content: response.trim(),
        timestamp: now + 0.001,
        tokenCount: estimateTokens(response),
      );
      await _dependencies.sessions.append(roleId, completed);
      final tag = deriveReplyTag(response);
      await _dependencies.maintenance.recordReply(
        role: role,
        userText: text,
        assistantText: response,
        tag: tag,
      );
      final evolved = _dependencies.maintenance.evolveRole(
        role,
        userText: text,
        assistantText: response,
        tag: tag,
      );
      await _dependencies.roles.saveRole(evolved);
      state = state.copyWith(
        messages: _replaceAssistant(assistantId, response.trim()),
        isStreaming: false,
        emotion: tag.emotion,
      );
    } catch (error) {
      if (_cancelRequested) {
        await _finishInterrupted(assistantId, response, now);
        return;
      }
      final remaining = state.messages
          .where(
            (message) =>
                message.id != assistantId || message.content.isNotEmpty,
          )
          .map(
            (message) => message.id == assistantId
                ? message.copyWith(isStreaming: false)
                : message,
          )
          .toList();
      state = state.copyWith(
        messages: remaining,
        isStreaming: false,
        error: '$error',
      );
    } finally {
      _activeProvider = null;
      _cancelRequested = false;
    }
  }

  void cancel() {
    if (!state.isStreaming) return;
    _cancelRequested = true;
    _activeProvider?.cancel();
    state = state.copyWith(
      messages: state.messages
          .map(
            (message) => message.isStreaming
                ? message.copyWith(isStreaming: false)
                : message,
          )
          .toList(),
      isStreaming: false,
    );
  }

  Future<void> _finishInterrupted(
    String assistantId,
    String response,
    double timestamp,
  ) async {
    final partial = response.trim();
    if (partial.isEmpty) {
      state = state.copyWith(
        messages: state.messages
            .where((message) => message.id != assistantId)
            .toList(),
        isStreaming: false,
        clearError: true,
      );
      return;
    }
    final interrupted = ChatMessage(
      id: assistantId,
      role: 'assistant',
      content: partial,
      timestamp: timestamp + 0.001,
      tokenCount: estimateTokens(partial),
      extraFields: const <String, dynamic>{'interrupted': true},
    );
    await _dependencies.sessions.append(roleId, interrupted);
    state = state.copyWith(
      messages: _replaceAssistant(assistantId, partial),
      isStreaming: false,
      clearError: true,
    );
  }

  List<ChatMessage> _replaceAssistant(
    String id,
    String content, {
    bool streaming = false,
  }) => state.messages
      .map(
        (message) => message.id == id
            ? message.copyWith(content: content, isStreaming: streaming)
            : message,
      )
      .toList();

  @override
  void dispose() {
    _activeProvider?.cancel();
    super.dispose();
  }
}

final chatProvider =
    StateNotifierProvider.family<ChatController, ChatState, String>(
      (ref, roleId) => ChatController(ref.watch(dependenciesProvider), roleId),
    );

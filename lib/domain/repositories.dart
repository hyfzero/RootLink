import 'dart:io';

import 'models.dart';

abstract interface class RoleRepository {
  Future<List<CompanionRole>> listRoles();
  Future<CompanionRole?> getRole(String id);
  Future<void> saveRole(CompanionRole role);
  Future<void> deleteRole(String id);
  Future<void> seedDefaultsIfEmpty();
  File? resolveAsset(CompanionRole role, String relativePath);
}

abstract interface class SessionRepository {
  Future<DaySession> loadToday(String roleId);
  Future<DaySession> append(String roleId, ChatMessage message);
  Future<List<DaySession>> recent(String roleId, {int days = 30});
  Future<void> archiveStale(String roleId);
}

abstract interface class SettingsRepository {
  Future<UiSettings> load();
  Future<void> save(UiSettings settings);
  Future<ModelConfig> activeModel();
}

abstract interface class ChatProvider {
  Future<String> complete(ChatRequest request);
  Stream<ChatStreamEvent> stream(ChatRequest request);
  void cancel();
}

abstract interface class AgentRuntime {
  Stream<ChatStreamEvent> send({
    required CompanionRole role,
    required String message,
    required List<ChatMessage> history,
  });
}

abstract interface class CharacterPackageService {
  Future<String> exportRole(String roleId, String outputPath);
  Future<String> importRole(String packagePath, {bool overwrite = true});
}

abstract interface class PortraitProcessor {
  Future<List<int>> process({
    required List<int> source,
    required String renderMode,
    required List<int> backgroundColor,
    required int tolerance,
    required int feather,
    required List<int>? cropBox,
    required double scale,
    required int offsetX,
    required int offsetY,
    required int canvasWidth,
    required int canvasHeight,
  });
}

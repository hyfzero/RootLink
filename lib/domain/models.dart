import 'dart:convert';

/// A map-backed value that keeps fields introduced by older or newer builds.
Map<String, dynamic> jsonMap(Object? value) => value is Map
    ? value.map((key, item) => MapEntry(key.toString(), item))
    : <String, dynamic>{};

List<String> stringList(Object? value) => value is List
    ? value.whereType<Object>().map((item) => item.toString()).toList()
    : <String>[];

double jsonDouble(Object? value, [double fallback = 0]) =>
    value is num ? value.toDouble() : double.tryParse('$value') ?? fallback;

int jsonInt(Object? value, [int fallback = 0]) =>
    value is num ? value.toInt() : int.tryParse('$value') ?? fallback;

class CompanionRole {
  CompanionRole({
    required this.id,
    required this.profile,
    required this.state,
    required this.memories,
    required this.speakingStyle,
    required this.ui,
    required this.config,
    required this.portraitEdits,
  });

  final String id;
  final Map<String, dynamic> profile;
  final Map<String, dynamic> state;
  final Map<String, dynamic> memories;
  final Map<String, dynamic> speakingStyle;
  final Map<String, dynamic> ui;
  final Map<String, dynamic> config;
  final Map<String, dynamic> portraitEdits;

  String get name => (profile['name'] ?? id).toString();
  String get type => (ui['type'] ?? 'Custom').toString();
  String get intro => (ui['intro'] ?? profile['background'] ?? '').toString();
  String get statusText => (ui['status_text'] ?? '').toString();
  String get accentColor => (ui['accent_color'] ?? '#5578E7').toString();
  String get avatarPath => (ui['avatar'] ?? '').toString();
  String get standingImagePath =>
      (ui['standing_image'] ?? portraits['neutral'] ?? '').toString();
  List<String> get tags => stringList(ui['tags']);
  Map<String, dynamic> get portraits => jsonMap(ui['portraits']);
  String get lastMessage => (ui['last_message'] ?? '').toString();
  String get lastTime => (ui['last_time'] ?? '').toString();
  double get lastTimestamp => jsonDouble(ui['last_timestamp']);

  CompanionRole copyWith({
    Map<String, dynamic>? profile,
    Map<String, dynamic>? state,
    Map<String, dynamic>? memories,
    Map<String, dynamic>? speakingStyle,
    Map<String, dynamic>? ui,
    Map<String, dynamic>? config,
    Map<String, dynamic>? portraitEdits,
  }) => CompanionRole(
    id: id,
    profile: profile ?? this.profile,
    state: state ?? this.state,
    memories: memories ?? this.memories,
    speakingStyle: speakingStyle ?? this.speakingStyle,
    ui: ui ?? this.ui,
    config: config ?? this.config,
    portraitEdits: portraitEdits ?? this.portraitEdits,
  );
}

class ChatMessage {
  ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.timestamp,
    this.tokenCount,
    this.isStreaming = false,
    Map<String, dynamic>? extraFields,
  }) : extraFields = extraFields ?? <String, dynamic>{};

  final String id;
  final String role;
  final String content;
  final double timestamp;
  final int? tokenCount;
  final bool isStreaming;
  final Map<String, dynamic> extraFields;

  bool get isUser => role == 'user';

  factory ChatMessage.fromJson(Map<String, dynamic> source) {
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere(
        (key, _) => const {
          'id',
          'role',
          'content',
          'timestamp',
          'token_count',
        }.contains(key),
      );
    return ChatMessage(
      id: (source['id'] ?? '').toString(),
      role: (source['role'] ?? 'assistant').toString(),
      content: (source['content'] ?? source['text'] ?? '').toString(),
      timestamp: jsonDouble(source['timestamp']),
      tokenCount: source['token_count'] == null
          ? null
          : jsonInt(source['token_count']),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'id': id,
    'role': role,
    'content': content,
    'timestamp': timestamp,
    if (tokenCount != null) 'token_count': tokenCount,
  };

  ChatMessage copyWith({String? content, bool? isStreaming}) => ChatMessage(
    id: id,
    role: role,
    content: content ?? this.content,
    timestamp: timestamp,
    tokenCount: tokenCount,
    isStreaming: isStreaming ?? this.isStreaming,
    extraFields: extraFields,
  );
}

class DaySession {
  DaySession({
    required this.date,
    required this.messages,
    this.messageCount = 0,
    this.totalTokensEstimate = 0,
    this.summaryGenerated = false,
    this.tokenEstimator = 'hybrid_v1',
    this.tokenizerMode = 'auto',
    this.modelProvider,
    this.modelName,
    Map<String, dynamic>? extraFields,
  }) : extraFields = extraFields ?? <String, dynamic>{};

  final String date;
  final List<ChatMessage> messages;
  final int messageCount;
  final int totalTokensEstimate;
  final bool summaryGenerated;
  final String tokenEstimator;
  final String tokenizerMode;
  final String? modelProvider;
  final String? modelName;
  final Map<String, dynamic> extraFields;

  factory DaySession.fromJson(Map<String, dynamic> source) {
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere(
        (key, _) => const {
          'date',
          'messages',
          'message_count',
          'total_tokens_estimate',
          'summary_generated',
          'token_estimator',
          'tokenizer_mode',
          'model_provider',
          'model_name',
        }.contains(key),
      );
    final messages = (source['messages'] as List? ?? const [])
        .map((item) => ChatMessage.fromJson(jsonMap(item)))
        .toList();
    return DaySession(
      date: (source['date'] ?? '').toString(),
      messages: messages,
      messageCount: jsonInt(source['message_count'], messages.length),
      totalTokensEstimate: jsonInt(source['total_tokens_estimate']),
      summaryGenerated: source['summary_generated'] == true,
      tokenEstimator: (source['token_estimator'] ?? 'hybrid_v1').toString(),
      tokenizerMode: (source['tokenizer_mode'] ?? 'auto').toString(),
      modelProvider: source['model_provider']?.toString(),
      modelName: source['model_name']?.toString(),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'date': date,
    'messages': messages.map((message) => message.toJson()).toList(),
    'message_count': messageCount,
    'total_tokens_estimate': totalTokensEstimate,
    'summary_generated': summaryGenerated,
    'token_estimator': tokenEstimator,
    'tokenizer_mode': tokenizerMode,
    'model_provider': modelProvider,
    'model_name': modelName,
  };
}

class UiSettings {
  const UiSettings({
    this.isDark = false,
    this.tokenQuality = 50,
    this.modelProvider = 'minimax',
    this.modelName = 'MiniMax-M2.5',
    this.apiKey = '',
    this.userName = '用户',
    this.userAvatarPath,
    this.extraFields = const <String, dynamic>{},
  });

  final bool isDark;
  final int tokenQuality;
  final String modelProvider;
  final String modelName;
  final String apiKey;
  final String userName;
  final String? userAvatarPath;
  final Map<String, dynamic> extraFields;

  UiSettings copyWith({
    bool? isDark,
    int? tokenQuality,
    String? modelProvider,
    String? modelName,
    String? apiKey,
    String? userName,
    String? userAvatarPath,
  }) => UiSettings(
    isDark: isDark ?? this.isDark,
    tokenQuality: tokenQuality ?? this.tokenQuality,
    modelProvider: modelProvider ?? this.modelProvider,
    modelName: modelName ?? this.modelName,
    apiKey: apiKey ?? this.apiKey,
    userName: userName ?? this.userName,
    userAvatarPath: userAvatarPath ?? this.userAvatarPath,
    extraFields: extraFields,
  );
}

class ModelConfig {
  const ModelConfig({
    required this.provider,
    required this.model,
    required this.apiKey,
    required this.baseUrl,
    this.maxTokens = 8192,
    this.temperature = 0.7,
    this.supportsThinking = false,
    this.apiType = 'openai',
    this.headers = const <String, String>{},
  });

  final String provider;
  final String model;
  final String apiKey;
  final String baseUrl;
  final int maxTokens;
  final double temperature;
  final bool supportsThinking;
  final String apiType;
  final Map<String, String> headers;
}

class ChatRequest {
  const ChatRequest({
    required this.model,
    required this.messages,
    this.temperature = 0.7,
    this.maxTokens = 4096,
    this.tools = const <Map<String, dynamic>>[],
    this.reasoningSplit = false,
  });

  final String model;
  final List<Map<String, dynamic>> messages;
  final double temperature;
  final int maxTokens;
  final List<Map<String, dynamic>> tools;
  final bool reasoningSplit;
}

enum ChatStreamEventType { delta, reasoning, toolCalls, usage, done }

class ChatStreamEvent {
  const ChatStreamEvent({
    required this.type,
    this.text = '',
    this.toolCalls = const <Map<String, dynamic>>[],
    this.usage = const <String, dynamic>{},
    this.finishReason,
  });

  final ChatStreamEventType type;
  final String text;
  final List<Map<String, dynamic>> toolCalls;
  final Map<String, dynamic> usage;
  final String? finishReason;
}

class PersonalityState {
  const PersonalityState({
    this.mood = 'neutral',
    this.energy = 0.6,
    this.affinity = 0,
    this.trust = 0,
    this.familiarity = 0,
    this.boundaryComfort = 50,
    this.recentValence = 0,
    this.recentSupport = 0,
    this.recentConflict = 0,
    this.tension = 0,
    this.currentFocus,
    this.lastEmotion = 'neutral',
    this.updatedAt,
    this.extraFields = const <String, dynamic>{},
  });

  final String mood;
  final double energy;
  final double affinity;
  final double trust;
  final double familiarity;
  final double boundaryComfort;
  final double recentValence;
  final double recentSupport;
  final double recentConflict;
  final double tension;
  final String? currentFocus;
  final String lastEmotion;
  final double? updatedAt;
  final Map<String, dynamic> extraFields;

  factory PersonalityState.fromJson(Map<String, dynamic> source) {
    const keys = <String>{
      'mood',
      'energy',
      'affinity',
      'trust',
      'familiarity',
      'boundary_comfort',
      'recent_valence',
      'recent_support',
      'recent_conflict',
      'tension',
      'current_focus',
      'last_emotion',
      'updated_at',
    };
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere((key, _) => keys.contains(key));
    return PersonalityState(
      mood: (source['mood'] ?? 'neutral').toString(),
      energy: jsonDouble(source['energy'], 0.6).clamp(0, 1),
      affinity: jsonDouble(source['affinity']).clamp(0, 100),
      trust: jsonDouble(source['trust']).clamp(0, 100),
      familiarity: jsonDouble(source['familiarity']).clamp(0, 100),
      boundaryComfort: jsonDouble(source['boundary_comfort'], 50).clamp(0, 100),
      recentValence: jsonDouble(source['recent_valence']).clamp(-100, 100),
      recentSupport: jsonDouble(source['recent_support']).clamp(0, 100),
      recentConflict: jsonDouble(source['recent_conflict']).clamp(0, 100),
      tension: jsonDouble(source['tension']).clamp(0, 100),
      currentFocus: source['current_focus']?.toString(),
      lastEmotion: (source['last_emotion'] ?? 'neutral').toString(),
      updatedAt: source['updated_at'] == null
          ? null
          : jsonDouble(source['updated_at']),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'mood': mood,
    'energy': energy.clamp(0, 1),
    'affinity': affinity.clamp(0, 100),
    'trust': trust.clamp(0, 100),
    'familiarity': familiarity.clamp(0, 100),
    'boundary_comfort': boundaryComfort.clamp(0, 100),
    'recent_valence': recentValence.clamp(-100, 100),
    'recent_support': recentSupport.clamp(0, 100),
    'recent_conflict': recentConflict.clamp(0, 100),
    'tension': tension.clamp(0, 100),
    'current_focus': currentFocus,
    'last_emotion': lastEmotion,
    'updated_at': updatedAt,
  };
}

class SpeakingStyle {
  const SpeakingStyle({
    this.vocabularyLevel = 'common',
    this.sentenceLength = 'varied',
    this.exclamationRate = 0.1,
    this.questionRate = 0.15,
    this.ellipsisRate = 0.05,
    this.fillerWords = const <String>[],
    this.emotionWords = const <String, dynamic>{},
    this.emojiUsage = 'none',
    this.parenthesisUsage = 'sparse',
    this.extraFields = const <String, dynamic>{},
  });

  final String vocabularyLevel;
  final String sentenceLength;
  final double exclamationRate;
  final double questionRate;
  final double ellipsisRate;
  final List<String> fillerWords;
  final Map<String, dynamic> emotionWords;
  final String emojiUsage;
  final String parenthesisUsage;
  final Map<String, dynamic> extraFields;

  factory SpeakingStyle.fromJson(Map<String, dynamic> source) {
    const keys = <String>{
      'vocabulary_level',
      'sentence_length',
      'exclamation_rate',
      'question_rate',
      'ellipsis_rate',
      'filler_words',
      'emotion_words',
      'emoji_usage',
      'parenthesis_usage',
    };
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere((key, _) => keys.contains(key));
    return SpeakingStyle(
      vocabularyLevel: (source['vocabulary_level'] ?? 'common').toString(),
      sentenceLength: (source['sentence_length'] ?? 'varied').toString(),
      exclamationRate: jsonDouble(source['exclamation_rate'], 0.1),
      questionRate: jsonDouble(source['question_rate'], 0.15),
      ellipsisRate: jsonDouble(source['ellipsis_rate'], 0.05),
      fillerWords: stringList(source['filler_words']),
      emotionWords: jsonMap(source['emotion_words']),
      emojiUsage: (source['emoji_usage'] ?? 'none').toString(),
      parenthesisUsage: (source['parenthesis_usage'] ?? 'sparse').toString(),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'vocabulary_level': vocabularyLevel,
    'sentence_length': sentenceLength,
    'exclamation_rate': exclamationRate,
    'question_rate': questionRate,
    'ellipsis_rate': ellipsisRate,
    'filler_words': fillerWords,
    'emotion_words': emotionWords,
    'emoji_usage': emojiUsage,
    'parenthesis_usage': parenthesisUsage,
  };
}

class PortraitEdit {
  const PortraitEdit({
    this.sourcePath = '',
    this.processedPath = '',
    this.renderMode = 'cutout',
    this.backgroundColor = const <int>[255, 255, 255],
    this.tolerance = 32,
    this.feather = 0,
    this.cropBox,
    this.scale = 1,
    this.offsetX = 0,
    this.offsetY = 0,
    this.warning = '',
    this.extraFields = const <String, dynamic>{},
  });

  final String sourcePath;
  final String processedPath;
  final String renderMode;
  final List<int> backgroundColor;
  final int tolerance;
  final int feather;
  final List<int>? cropBox;
  final double scale;
  final int offsetX;
  final int offsetY;
  final String warning;
  final Map<String, dynamic> extraFields;

  factory PortraitEdit.fromJson(Map<String, dynamic> source) {
    const keys = <String>{
      'source_path',
      'processed_path',
      'render_mode',
      'background_color',
      'tolerance',
      'feather',
      'crop_box',
      'scale',
      'offset_x',
      'offset_y',
      'warning',
    };
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere((key, _) => keys.contains(key));
    final color = (source['background_color'] as List? ?? const <Object>[])
        .map((value) => jsonInt(value).clamp(0, 255))
        .toList();
    final crop = (source['crop_box'] as List? ?? const <Object>[])
        .map((value) => jsonInt(value))
        .toList();
    return PortraitEdit(
      sourcePath: (source['source_path'] ?? '').toString(),
      processedPath: (source['processed_path'] ?? '').toString(),
      renderMode: (source['render_mode'] ?? 'cutout').toString(),
      backgroundColor: color.length == 3 ? color : const <int>[255, 255, 255],
      tolerance: jsonInt(source['tolerance'], 32),
      feather: jsonInt(source['feather']),
      cropBox: crop.length == 4 ? crop : null,
      scale: jsonDouble(source['scale'], 1),
      offsetX: jsonInt(source['offset_x']),
      offsetY: jsonInt(source['offset_y']),
      warning: (source['warning'] ?? '').toString(),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'source_path': sourcePath,
    'processed_path': processedPath,
    'render_mode': renderMode,
    'background_color': backgroundColor,
    'tolerance': tolerance,
    'feather': feather,
    'crop_box': cropBox,
    'scale': scale,
    'offset_x': offsetX,
    'offset_y': offsetY,
    'warning': warning,
  };
}

class ReplyTag {
  const ReplyTag({
    this.emotion = 'neutral',
    this.expression = 'neutral',
    this.action,
    this.pose = 'standing',
    this.overlays = const <String>[],
    this.intensity = 1,
    this.topics = const <String>[],
  });

  final String emotion;
  final String expression;
  final String? action;
  final String pose;
  final List<String> overlays;
  final double intensity;
  final List<String> topics;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'emotion': emotion,
    'expression': expression,
    'action': action,
    'pose': pose,
    'overlays': overlays,
    'intensity': intensity,
    'topics': topics,
  };
}

class MemoryEntry {
  const MemoryEntry({
    required this.id,
    required this.content,
    required this.memoryType,
    required this.timestamp,
    this.importance = 1,
    this.context = '',
    this.extraFields = const <String, dynamic>{},
  });

  final String id;
  final String content;
  final String memoryType;
  final double timestamp;
  final double importance;
  final String context;
  final Map<String, dynamic> extraFields;

  MemoryEntry copyWith({
    String? id,
    String? content,
    String? memoryType,
    double? timestamp,
    double? importance,
    String? context,
    Map<String, dynamic>? extraFields,
  }) => MemoryEntry(
    id: id ?? this.id,
    content: content ?? this.content,
    memoryType: memoryType ?? this.memoryType,
    timestamp: timestamp ?? this.timestamp,
    importance: importance ?? this.importance,
    context: context ?? this.context,
    extraFields: extraFields ?? this.extraFields,
  );

  factory MemoryEntry.fromJson(Map<String, dynamic> source) {
    final extras = Map<String, dynamic>.from(source)
      ..removeWhere(
        (key, _) => const {
          'id',
          'content',
          'memory_type',
          'timestamp',
          'importance',
          'context',
        }.contains(key),
      );
    return MemoryEntry(
      id: (source['id'] ?? '').toString(),
      content: (source['content'] ?? '').toString(),
      memoryType: (source['memory_type'] ?? 'fact').toString(),
      timestamp: jsonDouble(source['timestamp']),
      importance: jsonDouble(source['importance'], 1),
      context: (source['context'] ?? '').toString(),
      extraFields: extras,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    ...extraFields,
    'id': id,
    'content': content,
    'memory_type': memoryType,
    'timestamp': timestamp,
    'importance': importance,
    'context': context,
  };
}

String prettyJson(Map<String, dynamic> data) =>
    const JsonEncoder.withIndent('  ').convert(data);

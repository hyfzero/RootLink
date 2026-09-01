import 'package:rootlink/domain/models.dart';

CompanionRole fixtureRole({String id = 'luna', String name = '露娜'}) =>
    CompanionRole(
      id: id,
      profile: <String, dynamic>{
        'name': name,
        'age': 24,
        'gender': 'female',
        'personality_traits': <String>['温柔', '好奇'],
        'interests': <String>['音乐'],
        'background': '来自旧版本的数据',
        'future_profile_field': <String, dynamic>{'kept': true},
      },
      state: <String, dynamic>{
        'mood': 'neutral',
        'affinity': 0.5,
        'trust': 0.5,
      },
      memories: <String, dynamic>{
        'episodic_memories': <Object>[],
        'preference_memories': <Object>[],
        'fact_memories': <Object>[],
        'daily_summary_memories': <Object>[],
        'monthly_summary_memories': <Object>[],
      },
      speakingStyle: <String, dynamic>{
        'base_style': <String, dynamic>{
          'vocabulary_level': 'common',
          'sentence_length': 'varied',
        },
      },
      ui: <String, dynamic>{
        'type': 'Custom',
        'tags': <String>['温柔'],
        'intro': '一个安静的数字灵魂',
        'accent_color': '#5578E7',
        'avatar': '',
        'standing_image': '',
        'portraits': <String, dynamic>{},
      },
      config: <String, dynamic>{
        'response': <String, dynamic>{'max_sentences': 5},
      },
      portraitEdits: <String, dynamic>{},
    );

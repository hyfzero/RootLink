# Agent Core Layer Specification

## Overview

A Python-based agent core layer inspired by OpenClaw's prompt generation and memory management mechanisms. This module provides character personality, historical message management with token-aware weighting, reply tagging for UI display, and persistent storage.

## Core Components

### 1. Persona (人格模块)

Defines an agent's character through structured attributes.

**Attributes:**
- `name`: Character name
- `age`: Integer (can be null for non-human characters)
- `gender`: String ("male", "female", "non-binary", "unknown", etc.)
- `personality_traits`: List of personality adjectives
- `background`: Biographical text describing life experiences
- `speaking_style`: How the character speaks (formal, casual, etc.)
- `birthday`: Optional date string
- `interests`: List of interests/hobbies

**Persona Memory:**
- `episodic_memories`: List of significant past events
- `preference_memories`: User preferences learned over time

### 2. Message History System (历史消息系统)

Inspired by OpenClaw's session management and compaction mechanisms.

#### 2.1 Daily Summary System
- Each day has a summary file: `memory/YYYY-MM-DD.md`
- Summary includes: date, most important message, key topics discussed
- Algorithm to determine "most important":
  - Messages with tool calls (higher weight)
  - Messages with explicit user intent
  - Messages triggering emotional responses
  - First message of a new topic thread

#### 2.2 Message Weighting
- Base weight per message type:
  - `user`: 1.0
  - `assistant`: 0.8
  - `system`: 0.3
  - `tool`: 0.5
- Time decay: `weight = base_weight * (1 - (age_hours / max_age_hours))`
- Importance boost: messages flagged as important get 2x multiplier
- Token cost tracking per message for budget management

#### 2.3 Daily Queue Mechanism
- Current day's messages accumulate in a queue
- Queue is NOT automatically added to prompt
- Insertion triggers (choose one or combine):
  - Token budget approach: add messages until X tokens used
  - Round-based: add every N turns
  - Importance threshold: add when cumulative importance exceeds threshold
- Queue resets at midnight (local time)

#### 2.4 Token-Aware Message Selection
- Similar to OpenClaw's `limitHistoryTurns` but weighted
- Keep last N user turns with highest weights
- Always keep first message (establishes context)
- Compaction via summarization when approaching context limit

### 3. Reply Tags (回复标签)

Each reply has tags for UI layer to display character reactions.

**Tag Structure:**
```json
{
  "emotion": "happy|sad|angry|surprised|neutral|thinking|...",
  "expression": "smile|cry|shock|relaxed|...",
  "action": "wave|nod|shake_head|pat|...",
  "pose": "standing|sitting|lying|...",
  "overlay": ["blush", "sweat_drop", "tears", "..."]
}
```

**Auto-tag Generation:**
- Emotion inferred from message sentiment
- Expression derived from emotion
- Action/pose can be explicit in message or inferred

### 4. Persistence (持久化)

Separate files for cross-device synchronization.

**File Structure:**
```
data/
  persona/
    profile.json        # Basic persona data
    memories.json       # Episodic and preference memories
  history/
    daily/
      YYYY-MM-DD.json   # Daily message log
      YYYY-MM-DD.summary.md  # Daily summary
    queue.json          # Current day's pending queue
    weights.json        # Message weight configurations
  tags/
    reply_tags.json     # Recent reply tags cache
    emotion_map.json    # Emotion inference patterns
  config/
    agent_config.json  # Agent settings
```

**Storage Format:**
- JSON for structured data (messages, weights, configs)
- Markdown for summaries (human-readable, easy to edit)
- Each file is standalone for easy sync

## Prompt Building (参考OpenClaw)

The prompt is built from sections in order:

1. **Identity**: "You are {name}..."
2. **Personality**: Traits, speaking style, background
3. **Recent Memories**: Last 3 days' summaries (not full history)
4. **Memory Context**: If memory search enabled, relevant memories
5. **Today's Queue**: If triggered, current day's important messages
6. **Current Conversation**: Recent weighted messages within token budget
7. **Runtime Info**: Time, date, user timezone

## Configuration

```json
{
  "persona": { ... },
  "history": {
    "max_context_tokens": 4000,
    "daily_queue_threshold": 100,
    "importance_threshold": 0.5,
    "retention_days": 30,
    "summary_trigger_messages": 50
  },
  "tags": {
    "auto_generate": true,
    "emotion_model": "keyword"
  },
  "storage": {
    "data_dir": "./data",
    "format": "json"
  }
}
```

## Key Algorithms

### Daily Summary Generation
1. Collect all messages for the day
2. Score each message by: tool_calls * 3 + explicit_intent * 2 + emotional * 1.5 + length_factor
3. Top 3 scored messages form the summary skeleton
4. Generate concise summary using template or LLM

### Token Budget Message Selection
1. Calculate available tokens: `budget = max_tokens - system_prompt_tokens - reserved_tokens`
2. Sort messages by weight descending
3. Greedily add messages until token budget reached
4. Maintain chronological order for added messages

### Message Compaction
When context is near limit:
1. Identify messages to compress
2. For each compressed section, generate summary
3. Replace original messages with summary + "([N] messages compressed)"

## References from OpenClaw

- System prompt building: `src/agents/system-prompt.ts`
- History limiting: `src/agents/pi-embedded-runner/history.ts`
- Memory flush: `src/auto-reply/reply/memory-flush.ts`
- Session compaction: `src/agents/pi-embedded-runner/compact.ts`
- Memory search config: `src/agents/memory-search.ts`

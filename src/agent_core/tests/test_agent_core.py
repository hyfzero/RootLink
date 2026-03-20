"""Test script for agent core module."""

import sys
import os

# Add grandparent (src/) to path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from agent_core.persona import Persona, PersonaProfile, MemoryEntry
from agent_core.history import MessageHistory, MessageRole, calculate_message_weight, estimate_tokens
from agent_core.tags import TagGenerator, TagCache, ReplyTag
from agent_core.config import AgentConfig, HistoryConfig
from agent_core.persistence import AgentStorage
from agent_core.prompt_builder import PromptBuilder, build_full_conversation_prompt


def test_persona():
    """Test persona module."""
    print("Testing Persona...")

    profile = PersonaProfile(
        name="Alice",
        age=20,
        gender="female",
        personality_traits=["cheerful", "curious", "friendly"],
        background="A university student studying computer science. Loves anime and gaming.",
        speaking_style="friendly and casual",
        interests=["programming", "anime", "games"],
    )

    persona = Persona(profile)

    # Add memories
    persona.add_memory(
        content="User prefers dark mode interface",
        memory_type="preference",
        importance=1.5,
        context="UI preferences"
    )
    persona.add_memory(
        content="Had a long conversation about Python programming",
        memory_type="episodic",
        importance=1.0,
        context="programming"
    )
    persona.add_memory(
        content="User's name is Bob",
        memory_type="fact",
        importance=2.0,
        context="user info"
    )

    # Test persona text
    persona_text = persona.build_persona_text()
    print(f"  Persona text: {persona_text[:100]}...")

    # Test recent memories
    recent = persona.get_recent_memories(limit=2)
    print(f"  Recent memories: {len(recent)}")

    # Test memory search
    results = persona.search_memories("Python")
    print(f"  Search 'Python': {len(results)} results")

    # Test serialization
    data = persona.to_dict()
    print(f"  Serialization: {len(data)} keys")

    assert persona.profile.name == "Alice"
    assert len(persona.episodic_memories) == 1
    assert len(persona.preference_memories) == 1
    assert len(persona.fact_memories) == 1

    print("  PASSED\n")
    return persona


def test_history():
    """Test history module."""
    print("Testing MessageHistory...")

    history = MessageHistory(max_context_tokens=4000)

    # Add messages
    history.add_message("Hello, how are you?", MessageRole.USER)
    history.add_message("Hi there! I'm doing great, thanks for asking!", MessageRole.ASSISTANT)
    history.add_message("Can you help me with Python?", MessageRole.USER, is_important=True)
    history.add_message("Of course! What do you need help with?", MessageRole.ASSISTANT)

    print(f"  Messages in queue: {len(history.current_queue.messages)}")

    # Test weight calculation
    weights = [calculate_message_weight(m) for m in history.current_queue.messages]
    print(f"  Message weights: {[round(w, 2) for w in weights]}")

    # Test token estimation
    tokens = estimate_tokens("Hello, how are you?")
    print(f"  Token estimate for 'Hello...': {tokens}")

    # Test queue flush trigger
    should_flush = history.should_trigger_queue_insert()
    print(f"  Should flush queue: {should_flush}")

    # Test context messages
    context = history.get_context_messages(max_tokens=500)
    print(f"  Context messages (500 tokens): {len(context)}")

    # Test serialization
    data = history.to_dict()
    print(f"  Serialization: {len(data)} keys")

    assert len(history.current_queue.messages) == 4
    print("  PASSED\n")
    return history


def test_tags():
    """Test tags module."""
    print("Testing Tags...")

    generator = TagGenerator()

    # Test emotion detection
    test_messages = [
        "Hello! I'm so happy to see you!",
        "I'm a bit confused about this...",
        "I'm really frustrated with this bug!",
        "Hmm, let me think about that...",
    ]

    for msg in test_messages:
        tag = generator.generate_tag("test_1", msg)
        print(f"  '{msg[:30]}...' -> emotion={tag.emotion}, expression={tag.expression}")

    # Test TagCache
    cache = TagCache()
    for i in range(5):
        tag = ReplyTag(
            message_id=f"msg_{i}",
            emotion=["happy", "sad", "neutral"][i % 3],
            expression="smile"
        )
        cache.add(tag)

    recent = cache.get_recent(limit=3)
    print(f"  Recent tags: {len(recent)}")

    print("  PASSED\n")


def test_config():
    """Test config module."""
    print("Testing Config...")

    config = AgentConfig(
        persona={"name": "TestBot", "age": 1, "gender": "unknown"},
        history={"max_context_tokens": 5000, "retention_days": 7},
    )

    print(f"  Max context tokens: {config.history.max_context_tokens}")
    print(f"  Retention days: {config.history.retention_days}")

    # Test serialization
    data = config.to_dict()
    print(f"  Serialization keys: {list(data.keys())}")

    # Test deserialization
    loaded = AgentConfig.from_dict(data)
    assert loaded.history.max_context_tokens == 5000

    print("  PASSED\n")


def test_prompt_builder():
    """Test prompt builder."""
    print("Testing PromptBuilder...")

    profile = PersonaProfile(
        name="Alice",
        age=20,
        gender="female",
        speaking_style="friendly"
    )
    persona = Persona(profile)

    history = MessageHistory()
    history.add_message("Hello!", MessageRole.USER)
    history.add_message("Hi there!", MessageRole.ASSISTANT)

    config = AgentConfig()

    builder = PromptBuilder(persona, history, config)

    # Test sections
    identity = builder.build_identity_section()
    print(f"  Identity section: {identity[:50]}...")

    runtime = builder.build_runtime_section()
    print(f"  Runtime section: {runtime[:50]}...")

    # Test full prompt
    full_prompt = builder.build_system_prompt()
    print(f"  Full prompt length: {len(full_prompt)} chars")

    # Test conversation prompt
    conv_prompt = build_full_conversation_prompt(persona, history, "How are you?", config)
    print(f"  Conversation prompt length: {len(conv_prompt)} chars")

    print("  PASSED\n")


def test_storage():
    """Test storage module."""
    print("Testing Storage...")

    import tempfile
    import shutil

    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    try:
        storage = AgentStorage(temp_dir)

        # Save persona
        profile = PersonaProfile(name="TestBot")
        persona = Persona(profile)
        persona.add_memory("Test memory", "episodic")

        success = storage.save_all_persona(persona)
        print(f"  Persona save: {success}")

        loaded_persona = storage.load_all_persona()
        print(f"  Persona load: {loaded_persona is not None}")

        # Save history
        history = MessageHistory()
        history.add_message("Test", MessageRole.USER)

        success = storage.save_all_history(history)
        print(f"  History save: {success}")

        loaded_history = storage.load_all_history()
        print(f"  History load: {loaded_history is not None}")

        # Save tags
        cache = TagCache()
        cache.add(ReplyTag(message_id="test", emotion="happy"))
        storage.save_all_tags(cache)

        loaded_tags = storage.load_all_tags()
        print(f"  Tags load: {loaded_tags is not None}")

        print("  PASSED\n")

    finally:
        shutil.rmtree(temp_dir)


def main():
    """Run all tests."""
    print("=" * 60)
    print("Agent Core Module Tests")
    print("=" * 60 + "\n")

    persona = test_persona()
    test_history()
    test_tags()
    test_config()
    test_prompt_builder()
    test_storage()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

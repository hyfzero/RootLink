"""
测试脚本 - 验证Agent核心层功能
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_core import (
    Agent,
    create_agent,
    Persona,
    PersonaManager,
    Memory,
    MemoryManager,
    MessageWeight,
    HistoryManager,
    ChatMessage,
    DailySummary,
    MessageQueue,
    ReplyTag,
    ReplyTagType,
    TagManager,
    TaggedReply,
    Storage,
)


def test_persona():
    """测试人格系统"""
    print("\n=== 测试人格系统 ===")

    # 创建人格
    manager = PersonaManager()
    persona = manager.create_persona(
        name="测试少女",
        age=17,
        gender="女",
        personality="害羞但好奇心强",
        background="高中生，热爱科学",
        interests=["科学", "动漫", "游戏"],
        speaking_style="用~结尾表示可爱",
    )

    # 添加人生事件
    manager.add_life_event(2015, "开始接触编程", importance=8)
    manager.add_life_event(2020, "考入重点高中", importance=7)

    print(f"名字: {persona.name}")
    print(f"年龄: {persona.age}")
    print(f"性别: {persona.gender}")
    print(f"性格: {persona.personality}")
    print(f"背景: {persona.background}")
    print(f"兴趣: {persona.interests}")
    print(f"说话风格: {persona.speaking_style}")
    print(f"人生事件数: {len(persona.life_events)}")

    # 测试prompt生成
    prompt = persona.get_prompt_context()
    print(f"\n人格Prompt:\n{prompt}")

    # 测试序列化
    data = persona.to_dict()
    print(f"\n序列化成功: {len(data)} 字段")

    restored = Persona.from_dict(data)
    print(f"反序列化: {restored.name}, {restored.age}岁")

    print("[PASS] 人格系统测试通过")
    return True


def test_memory():
    """测试记忆系统"""
    print("\n=== 测试记忆系统 ===")

    manager = MemoryManager()

    # 添加长期记忆
    mem1 = manager.add_long_term_memory(
        content="用户喜欢讨论AI话题",
        weight=MessageWeight.IMPORTANT,
        tags=["AI", "偏好"],
    )
    mem2 = manager.add_long_term_memory(
        content="用户今天心情不好",
        weight=MessageWeight.CRITICAL,
        tags=["情绪"],
    )

    print(f"长期记忆数: {len(manager.long_term_memories)}")

    # 搜索记忆
    results = manager.search_memories("AI")
    print(f"搜索'AI'结果: {len(results)} 条")

    # 获取重要记忆
    important = manager.get_important_memories()
    print(f"重要记忆: {len(important)} 条")

    # 测试会话记忆
    conv = manager.create_conversation("session_001")
    manager.add_to_conversation(
        "session_001",
        "用户: 你好",
        weight=MessageWeight.NORMAL,
    )
    manager.add_to_conversation(
        "session_001",
        "用户: 什么是机器学习？",
        weight=MessageWeight.IMPORTANT,
        tags=["技术问题"],
    )

    conv = manager.get_conversation("session_001")
    print(f"会话消息数: {len(conv.messages)}")

    print("[PASS] 记忆系统测试通过")
    return True


def test_history():
    """测试历史消息系统"""
    print("\n=== 测试历史消息系统 ===")

    manager = HistoryManager()

    # 添加消息
    msg1 = manager.add_message(
        sender="用户A",
        content="今天天气真好！",
        weight=MessageWeight.NORMAL,
    )
    msg2 = manager.add_message(
        sender="用户B",
        content="你喜欢编程吗？",
        weight=MessageWeight.NORMAL,
    )
    msg3 = manager.add_message(
        sender="用户A",
        content="帮我解释一下深度学习",
        weight=MessageWeight.IMPORTANT,
        tags=["技术"],
    )

    print(f"当天消息数: {len(manager.today_queue.queue)}")

    # 生成每日梗概
    summary = manager.generate_daily_summary()
    print(f"\n每日梗概:")
    print(f"  日期: {summary.date}")
    print(f"  摘要: {summary.summary}")
    print(f"  消息数: {summary.message_count}")
    print(f"  重要事件: {len(summary.important_events)}")

    # 获取prompt上下文
    context = manager.get_prompt_context(max_messages=5, include_days=3)
    print(f"\nPrompt上下文:\n{context[:200]}...")

    # 测试消息队列
    queue_messages = manager.today_queue.get_messages_for_prompt(max_messages=2)
    print(f"\n加入Prompt的消息数: {len(queue_messages)}")

    print("[PASS] 历史消息系统测试通过")
    return True


def test_tags():
    """测试标签系统"""
    print("\n=== 测试标签系统 ===")

    manager = TagManager()

    # 测试关键词分析
    test_contents = [
        "你好呀！今天真开心！",
        "为什么天空是蓝色的？",
        "再见，下次再聊！",
        "这个bug真让人恼火！",
    ]

    for content in test_contents:
        tags = manager.analyze_content_for_tags(content)
        print(f"  '{content[:15]}...' -> {[t.tag_type.value for t in tags]}")

    # 创建带标签的回复
    reply = manager.create_tagged_reply(
        message_id="test_001",
        content="我很高兴能帮助你！",
        metadata={"source": "test"},
    )

    print(f"\n主要标签: {reply.get_primary_tag()}")
    print(f"所有标签: {reply.get_all_tag_types()}")

    # 测试标签显示信息
    from agent_core.tags import get_tag_for_display
    display = get_tag_for_display(reply.tags[0])
    print(f"显示信息: {display}")

    print("[PASS] 标签系统测试通过")
    return True


def test_agent():
    """测试Agent整合"""
    print("\n=== 测试Agent整合 ===")

    storage_path = Path("./test_data")

    # 创建Agent
    agent = create_agent(
        agent_id="test_agent",
        name="小美",
        age=18,
        gender="女",
        personality="活泼开朗",
        background="大学生",
        interests=["编程", "音乐"],
        speaking_style="温柔可爱",
        storage_path=storage_path,
    )

    # 添加消息
    agent.add_message("用户", "你好呀", weight=MessageWeight.NORMAL)
    agent.add_message(
        "用户",
        "能告诉我什么是神经网络吗？",
        weight=MessageWeight.IMPORTANT,
    )

    # 添加回复
    reply = agent.add_reply(
        message_id="reply_001",
        content="神经网络是一种模拟人脑结构的算法模型~",
    )

    # 获取标签
    tags = agent.get_reply_tags("reply_001")
    print(f"回复标签: {tags}")

    # 生成完整prompt
    prompt = agent.generate_prompt()
    print(f"\n完整Prompt长度: {len(prompt)} 字符")

    # 保存
    success = agent.save()
    print(f"保存结果: {success}")

    # 获取状态
    status = agent.get_status()
    print(f"\nAgent状态:")
    for k, v in status.items():
        print(f"  {k}: {v}")

    # 从存储加载
    loaded = Agent.load_from_storage("test_agent", storage_path)
    if loaded:
        print(f"\n加载成功! 名字: {loaded.get_persona().name}")

    print("[PASS] Agent整合测试通过")
    return True


def test_storage():
    """测试存储系统"""
    print("\n=== 测试存储系统 ===")

    storage = Storage(Path("./test_storage"))
    storage.ensure_directories()

    # 保存数据
    test_data = {
        "name": "测试",
        "value": 123,
        "timestamp": datetime.now().isoformat(),
    }

    success = storage.save_agent_data("test_obj", test_data)
    print(f"保存: {success}")

    # 加载数据
    loaded = storage.load_agent_data("test_obj")
    print(f"加载: {loaded is not None}")
    print(f"数据: {loaded}")

    # 列出Agent
    agents = storage.list_agents()
    print(f"Agent列表: {agents}")

    # 删除
    deleted = storage.delete_agent("test_obj")
    print(f"删除: {deleted}")

    print("[PASS] 存储系统测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Agent核心层测试")
    print("=" * 50)

    tests = [
        ("人格系统", test_persona),
        ("记忆系统", test_memory),
        ("历史消息系统", test_history),
        ("标签系统", test_tags),
        ("Agent整合", test_agent),
        ("存储系统", test_storage),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[FAIL] {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    all_passed = True
    for name, result in results:
        status = "[PASS] 通过" if result else "[FAIL] 失败"
        print(f"  {name}: {status}")
        if not result:
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("所有测试通过!")
    else:
        print("有测试失败!")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()

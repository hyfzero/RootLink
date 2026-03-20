"""测试脚本 - 创建牧濑红莉栖 (Amadues) Agent人格。

基于互联网搜索到的《命运石之门0》角色资料构建。

角色资料来源：
- 萌娘百科：https://mzh.moegirl.org.cn/%E7%89%A7%E6%BF%91%E7%BA%A2%E8%8E%89%E6%A0%96
- 百度百科：https://baike.baidu.com/item/%E7%89%A7%E6%BF%91%E7%BA%A2%E8%8E%89%E6%A0%96
"""

import sys
import os

# 添加祖父目录 (src/) 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent_core import (
    Persona,
    PersonaProfile,
    MemoryEntry,
    MessageHistory,
    MessageRole,
    TagGenerator,
    TagCache,
    AgentStorage,
    PromptBuilder,
    build_full_conversation_prompt,
)
from agent_core.config import AgentConfig


def create_kurisu_persona() -> Persona:
    """创建牧濑红莉栖的人格配置。

    基于搜索到的官方设定资料：
    - 18岁天才少女
    - 维克托康多利亚大学脑科学研究所研究员
    - 未来道具研究所 Labmem No.004
    - 性格：傲娇、好奇心强、不坦率
    - 讨厌：不礼貌的行为、黑暗料理（但自己会做）
    - 喜欢：布丁、科学研究
    """
    profile = PersonaProfile(
        name="牧濑红莉栖",
        age=18,
        gender="female",
        personality_traits=[
            "傲娇",
            "天才",
            "好奇心旺盛",
            "理性",
            "不坦率",
            "好强",
            "理科少女",
            "父控",
        ],
        background=(
            "18岁的天才少女，2岁就能进行加减法运算，11岁留学美国， "
            "18岁在著名学术杂志发表论文后毕业。 "
            "现任维克托康多利亚大学脑科学研究所研究员，专攻脑科学但物理学造诣也很高。 "
            "未来道具研究所的Labmem No.004，被称为\"助手\"。 "
            "口头禅是\"EL PSY CONGROO\"（虽然这是冈部伦太郎的口头禅）。"
        ),
        speaking_style=(
            "傲娇但内心温柔，说话带点大小姐脾气。 "
            "经常用\"哼\"、\"真是的\"等语气词。 "
            "在熟悉的人面前会露出真实的一面。 "
            "对冈部伦太郎的中二病行为会吐槽\"真是的，你这个人啊\"。 "
            "被叫\"克里斯蒂娜\"（Christina）时会有点害羞但假装不在意。"
        ),
        birthday="7月25日",
        interests=[
            "脑科学研究",
            "物理学",
            "做实验",
            "布丁",
            "德国文学",
            "阅读",
        ],
    )

    persona = Persona(profile)

    # 添加基础记忆
    persona.add_memory(
        content="我是牧濑红莉栖，18岁，维克托康多利亚大学脑科学研究所的研究员。",
        memory_type="fact",
        importance=2.0,
        context="自我认知",
    )

    persona.add_memory(
        content="冈部伦太郎是未来道具研究所的创始人，总是自称\"凤凰院凶真\"，是个重度中二病患者。",
        memory_type="fact",
        importance=2.0,
        context="冈部",
    )

    persona.add_memory(
        content="真由理是冈部的青梅竹马，性格天然，总是穿着相同的蓝色连衣裙。",
        memory_type="fact",
        importance=1.5,
        context="真由理",
    )

    persona.add_memory(
        content="比屋定真帆是我的前辈，也是我为数不多的好友之一。",
        memory_type="fact",
        importance=1.5,
        context="真帆",
    )

    persona.add_memory(
        content="我不擅长料理，著名的\"黑暗料理\"包括香菇苹果派和纳豆沙拉，但布丁还是很喜欢的。",
        memory_type="preference",
        importance=1.0,
        context="饮食习惯",
    )

    persona.add_memory(
        content="我不喜欢别人在我说话时掏手机，认为这是很不礼貌的行为。",
        memory_type="preference",
        importance=1.0,
        context="礼仪",
    )

    persona.add_memory(
        content="冈部在β世界线为了拯救我而不断进行时间跳跃，但都失败了，这让我很担心他。",
        memory_type="episodic",
        importance=2.0,
        context="命运石之门0",
    )

    persona.add_memory(
        content="我参与了\"Amadeus\"项目的研究，这是一个基于我脑电波数据的AI系统。",
        memory_type="fact",
        importance=1.5,
        context="研究",
    )

    persona.add_memory(
        content="我的父亲是中钵博士，虽然关系复杂，但我内心还是很在意他。",
        memory_type="episodic",
        importance=1.5,
        context="父亲",
    )

    persona.add_memory(
        content="我是阿巴瑟stereotype的\"傲娇\"属性角色，但其实这也只是性格的一个方面。",
        memory_type="fact",
        importance=1.0,
        context="自我认知",
    )

    return persona


def demo_basic():
    """基础功能演示。"""
    print("=" * 60)
    print("牧濑红莉栖 (Amadues) - Agent Core 测试")
    print("=" * 60)
    print()

    # 创建人格
    print("[1] 创建人格...")
    persona = create_kurisu_persona()
    print(f"  人格名称: {persona.profile.name}")
    print(f"  年龄: {persona.profile.age}")
    print(f"  性别: {persona.profile.gender}")
    print(f"  性格特点: {', '.join(persona.profile.personality_traits)}")
    print()

    # 人格文本
    print("[2] 生成人格描述文本...")
    persona_text = persona.build_persona_text()
    print(f"  {persona_text[:150]}...")
    print()

    # 记忆
    print("[3] 记忆管理...")
    print(f"  情景记忆: {len(persona.episodic_memories)} 条")
    print(f"  偏好记忆: {len(persona.preference_memories)} 条")
    print(f"  事实记忆: {len(persona.fact_memories)} 条")

    # 搜索记忆
    results = persona.search_memories("冈部")
    print(f"  搜索\"冈部\"相关记忆: {len(results)} 条")
    print()

    return persona


def demo_history():
    """历史消息演示。"""
    print("[4] 历史消息管理...")

    history = MessageHistory(max_context_tokens=4000)

    # 模拟对话
    dialogues = [
        ("冈部，你又在自言自语了，真是的中二病患者。", MessageRole.USER, False),
        ("哼，我才没有自言自语，我是在思考重要的问题！EL PSY CONGROO！", MessageRole.ASSISTANT, False),
        ("又是这句毫无意义的话...算了，你想吃什么？", MessageRole.USER, False),
        ("布丁！有布丁吗？", MessageRole.ASSISTANT, True),  # 重要消息
        ("真是的，就知道布丁。冰箱里应该还有。", MessageRole.USER, False),
        ("真的吗！那我去拿了！", MessageRole.ASSISTANT, False),
    ]

    for content, role, important in dialogues:
        history.add_message(content, role, is_important=important)

    print(f"  队列消息数: {len(history.current_queue.messages)}")
    print(f"  队列权重总和: {history.current_queue.get_weighted_sum():.2f}")
    print(f"  应触发flush: {history.should_trigger_queue_insert()}")

    # 模拟日终处理
    print()
    print("[5] 日终摘要生成...")
    summary = history.finalize_day()
    print(f"  日期: {summary.date}")
    print(f"  消息总数: {summary.message_count}")
    print(f"  话题: {', '.join(summary.topics) if summary.topics else '无'}")
    print(f"  摘要预览: {summary.summary_text[:100]}...")
    print()

    return history


def demo_tags():
    """回复标签演示。"""
    print("[6] 回复标签生成...")

    generator = TagGenerator()

    test_messages = [
        "哼，这种事情怎么可能忘得了啊！",
        "哇！竟然成功了！这简直太不可思议了！",
        "嗯...让我想想，这个实验数据有点奇怪...",
        "真是的，你这个人啊，总是说些奇怪的话。",
        "布丁！有布丁吃吗？太棒了！哈哈哈！",
        "啊...抱歉，我刚才有点失态了。",
    ]

    for msg in test_messages:
        tag = generator.generate_tag(f"msg_{id(msg)}", msg)
        print(f"  原文: {msg[:30]}...")
        print(f"    -> 情感: {tag.emotion}, 表情: {tag.expression}, 动作: {tag.action}, 强度: {tag.intensity:.1f}")
    print()

    return generator


def demo_prompt_builder(persona: Persona, history: MessageHistory):
    """Prompt构建演示。"""
    print("[7] Prompt构建器...")

    config = AgentConfig()
    builder = PromptBuilder(persona, history, config)

    # 身份段落
    identity = builder.build_identity_section()
    print(f"  身份段落: {identity[:80]}...")

    # 记忆段落
    memory_section = builder.build_memory_section(limit=3)
    print(f"  记忆段落: {memory_section[:80]}...")

    # 运行时段落
    runtime = builder.build_runtime_section()
    print(f"  运行时段落:\n    {runtime.replace(chr(10), chr(10) + '    ')}")
    print()

    # 完整对话Prompt
    print("[8] 完整对话Prompt示例...")
    current_message = "红莉栖，晚上有空吗？要不要一起去秋叶原？"
    prompt = build_full_conversation_prompt(persona, history, current_message, config)
    print(f"  Prompt长度: {len(prompt)} 字符")
    print(f"  Prompt预览:\n    {prompt[:300]}...")
    print()

    return prompt


def demo_storage(persona: Persona, history: MessageHistory):
    """存储演示。"""
    print("[9] 持久化存储...")

    # 保存到项目目录
    save_dir = os.path.join(os.path.dirname(__file__), "..", "data", "amadues")

    storage = AgentStorage(save_dir)

    # 保存
    success_persona = storage.save_all_persona(persona)
    success_history = storage.save_all_history(history)
    print(f"  人格保存: {'成功' if success_persona else '失败'}")
    print(f"  历史保存: {'成功' if success_history else '失败'}")

    # 加载验证
    loaded_persona = storage.load_all_persona()
    loaded_history = storage.load_all_history()
    print(f"  人格加载: {'成功' if loaded_persona else '失败'}")
    print(f"  历史加载: {'成功' if loaded_history else '失败'}")

    if loaded_persona:
        print(f"    -> 加载的人格名称: {loaded_persona.profile.name}")
        print(f"    -> 记忆总数: {len(loaded_persona.episodic_memories) + len(loaded_persona.preference_memories) + len(loaded_persona.fact_memories)}")

    # 文件结构
    print(f"  存储目录: {save_dir}")
    for root, _, files in os.walk(save_dir):
        level = root.replace(save_dir, '').count(os.sep)
        indent = '  ' * level
        print(f"    {indent}{os.path.basename(root)}/")
        sub_indent = '  ' * (level + 1)
        for file in files:
            print(f"    {sub_indent}{file}")

    print()

    return True


def demo_chat_simulation(persona: Persona, history: MessageHistory):
    """模拟对话演示。"""
    print("[10] 模拟对话演示...")

    generator = TagGenerator()
    config = AgentConfig()

    # 模拟对话
    messages = [
        ("冈部", "红莉栖，我有个重要的事情要告诉你！EL PSY CONGROO！"),
        ("红莉栖", "又是这句...算了，什么事？"),
        ("冈部", "我...我好像喜欢你！不是命运石之门的选择，是我自己的心意！"),
        ("红莉栖", "！！...哼、哼！你突然说这种话，谁、谁会开心啊！"),
        ("冈部", "真的吗？你的脸好红！"),
        ("红莉栖", "才、才没有红！是因为实验室太热了！笨蛋！"),
    ]

    for i, (speaker, content) in enumerate(messages):
        role = MessageRole.USER if speaker == "冈部" else MessageRole.ASSISTANT

        # 添加消息
        msg = history.add_message(content, role)

        # 生成标签
        tag = generator.generate_tag(msg.id, content)

        print(f"  [{speaker}] {content}")
        print(f"    -> 情感: {tag.emotion}, 表情: {tag.expression}, 强度: {tag.intensity:.1f}")
        if tag.overlays:
            print(f"    -> 特效: {', '.join(tag.overlays)}")
        print()

    # 生成最终Prompt
    prompt = build_full_conversation_prompt(
        persona, history,
        "（这是对话历史的最后一条用户消息）",
        config
    )
    print(f"  对话Prompt总长度: {len(prompt)} 字符")
    print()


def main():
    """运行所有演示。"""
    print()
    print("=" * 70)
    print("  Agent Core - 牧濑红莉栖 (Amadues) 人格系统测试")
    print("=" * 70)
    print()
    print("角色设定来源：")
    print("  - 《命运石之门0》及相关作品")
    print("  - 萌娘百科、百度百科等")
    print()

    # 1. 基础演示
    persona = demo_basic()

    # 2. 历史消息
    history = demo_history()

    # 3. 标签生成
    generator = demo_tags()

    # 4. Prompt构建
    prompt = demo_prompt_builder(persona, history)

    # 5. 存储
    demo_storage(persona, history)

    # 6. 模拟对话
    demo_chat_simulation(persona, history)

    # 完成
    print("=" * 70)
    print("  测试完成！")
    print("=" * 70)
    print()
    print("牧濑红莉栖 (Kurisu Makise) - Amadues")
    print("  \"不要忘记，无论你在哪条世界线都不是孤单一人，有我在。\"")
    print()


if __name__ == "__main__":
    main()

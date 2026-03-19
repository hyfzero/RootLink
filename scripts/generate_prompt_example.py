"""
生成完整Prompt示例
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_core import (
    Agent,
    create_agent,
    MessageWeight,
)


def main():
    # 创建Agent
    agent = create_agent(
        agent_id="xiao_mei",
        name="小美",
        age=18,
        gender="女",
        personality="活泼开朗，温柔体贴，有时有点害羞但好奇心很强",
        background="某大学计算机系学生，从小对新技术着迷，热爱编程和动漫",
        interests=["编程", "动漫", "音乐", "游戏", "科幻小说"],
        speaking_style="语气温柔可爱，喜欢用~结尾，偶尔会用颜文字表达情绪",
        storage_path=Path("./prompt_example_data"),
    )

    # 添加一些人生事件
    from agent_core.persona import LifeEvent
    agent.persona_manager.add_life_event(2008, "第一次接触电脑，对数字世界产生兴趣", importance=8)
    agent.persona_manager.add_life_event(2015, "开始学习编程，写出第一个Hello World", importance=7)
    agent.persona_manager.add_life_event(2023, "考入理想的大学计算机系", importance=9)
    agent.persona_manager.add_life_event(2024, "加入学校的AI实验室", importance=8)

    # 添加历史消息（模拟多天对话）
    print("添加模拟历史消息...")

    # 第一天的消息
    agent.history_manager.add_message(
        sender="用户A",
        content="你好呀！",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="小美",
        content="你好呀~有什么想聊的吗？",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="用户A",
        content="你在学什么专业呀？",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="小美",
        content="我在学计算机哦~正在学人工智能相关的课程呢！",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="用户A",
        content="哇，好厉害！那你觉得AI未来会怎样发展？",
        weight=MessageWeight.IMPORTANT,
    )
    agent.history_manager.add_message(
        sender="小美",
        content="我觉得AI会越来越懂人类吧~可能会成为我们生活的小助手也说不定呢！",
        weight=MessageWeight.IMPORTANT,
    )

    # 生成第一天的梗概
    agent.history_manager.generate_daily_summary()

    # 模拟新的一天
    import datetime
    agent.history_manager.today_queue.current_date = None
    agent.history_manager.today_queue.queue.clear()

    # 第二天的消息
    agent.history_manager.add_message(
        sender="用户B",
        content="早上好！",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="小美",
        content="早上好呀~今天也要加油呢！",
        weight=MessageWeight.NORMAL,
    )
    agent.history_manager.add_message(
        sender="用户B",
        content="对了，你上次说的那个机器学习，能不能再给我讲讲？",
        weight=MessageWeight.IMPORTANT,
        tags=["技术"],
    )
    agent.history_manager.add_message(
        sender="小美",
        content="当然可以呀~机器学习呢，简单来说就是让电脑自己学习怎么完成任务。就像教小朋友认识猫一样，给它看很多猫的照片，它慢慢就能自己认识猫啦~",
        weight=MessageWeight.IMPORTANT,
    )
    agent.history_manager.add_message(
        sender="用户B",
        content="原来是这样！那深度学习又是什么呢？",
        weight=MessageWeight.IMPORTANT,
    )
    agent.history_manager.add_message(
        sender="小美",
        content="深度学习是机器学习的一个分支哦~它用一种叫神经网络的东西，层数越多就越'深'，能处理更复杂的问题呢！",
        weight=MessageWeight.NORMAL,
    )

    # 生成第二天的梗概
    agent.history_manager.generate_daily_summary()

    # 添加回复并自动标签
    print("添加回复（带标签）...")

    reply1 = agent.add_reply(
        message_id="reply_001",
        content="当然可以呀~机器学习呢，简单来说就是让电脑自己学习怎么完成任务。就像教小朋友认识猫一样，给它看很多猫的照片，它慢慢就能自己认识猫啦~",
    )

    reply2 = agent.add_reply(
        message_id="reply_002",
        content="深度学习是机器学习的一个分支哦~它用一种叫神经网络的东西，层数越多就越'深'，能处理更复杂的问题呢！",
    )

    # 保存数据
    agent.save()

    # 生成完整Prompt
    print("\n" + "=" * 70)
    print("生成的完整Prompt")
    print("=" * 70)

    prompt = agent.generate_prompt(
        max_history_messages=10,
        include_days=7
    )

    print(prompt)

    print("\n" + "=" * 70)
    print("Agent状态")
    print("=" * 70)
    status = agent.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("回复标签（用于立绘显示）")
    print("=" * 70)
    tags1 = agent.get_reply_tags("reply_001")
    tags2 = agent.get_reply_tags("reply_002")
    print(f"回复1: {tags1}")
    print(f"回复2: {tags2}")


if __name__ == "__main__":
    main()

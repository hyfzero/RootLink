"""
使用示例
演示如何使用Agent核心层
"""

from pathlib import Path
from agent_core import Agent, create_agent, MessageWeight, ReplyTagType


def main():
    # 1. 创建Agent
    storage_path = Path("./data")
    agent = create_agent(
        agent_id="assistant_001",
        name="小美",
        age=18,
        gender="女",
        personality="活泼开朗，喜欢帮助人，有时有点害羞",
        background="一名大学生，热爱学习和探索新事物",
        interests=["动漫", "音乐", "编程", "游戏"],
        speaking_style="语气温柔，偶尔用可爱的颜文字",
        storage_path=storage_path,
    )

    # 2. 添加一些消息历史
    agent.add_message(
        sender="用户A",
        content="今天天气真好呀！",
        weight=MessageWeight.NORMAL,
    )
    agent.add_message(
        sender="用户B",
        content="你喜欢什么类型的音乐？",
        weight=MessageWeight.NORMAL,
    )
    agent.add_message(
        sender="用户A",
        content="能不能帮我解释一下什么是机器学习？",
        weight=MessageWeight.IMPORTANT,
        tags=["技术", "学习"],
    )

    # 3. 添加回复（自动生成标签）
    reply = agent.add_reply(
        message_id="msg_123",
        content="机器学习是人工智能的一个分支，简单来说就是让计算机通过数据学习并改进自己的算法。比如你给它看很多猫的照片，它就能学会识别猫~",
        auto_tag=True,
    )

    # 4. 查看回复标签
    tags = agent.get_reply_tags("msg_123")
    print("回复标签:", tags)

    # 5. 生成完整prompt
    prompt = agent.generate_prompt(
        max_history_messages=10,
        include_days=7,
    )
    print("\n=== 生成的Prompt ===")
    print(prompt)

    # 6. 保存数据
    agent.save()
    print("\n数据已保存!")

    # 7. 查看状态
    status = agent.get_status()
    print("\n=== Agent状态 ===")
    for k, v in status.items():
        print(f"  {k}: {v}")


def load_and_continue():
    """从存储加载并继续"""
    storage_path = Path("./data")

    # 加载已有的Agent
    agent = Agent.load_from_storage("assistant_001", storage_path)
    if agent:
        print("成功加载Agent!")
        print(agent.get_status())

        # 继续对话
        agent.add_message(
            sender="用户C",
            content="昨天你说的那个算法还记得吗？",
            weight=MessageWeight.IMPORTANT,
        )


if __name__ == "__main__":
    main()

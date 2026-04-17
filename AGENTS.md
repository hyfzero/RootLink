# 设计原则

在所有代码实现中遵循以下原则：

## 1. KISS (Keep It Simple, Stupid)
- 鼓励编写简单、不复杂的解决方案
- 避免过度设计和不必要的复杂性
- 更具可读性和可维护性的代码

## 2. YAGNI (You Aren't Gonna Need It)
- 防止添加推测性功能
- 专注于仅实现当前需要的内容
- 减少代码膨胀和维护开销

## 3. SOLID Principles
- **单一职责原则 (Single Responsibility Principle)**: 一个类只负责一个功能
- **开闭原则 (Open-Closed Principle)**: 对扩展开放，对修改关闭
- **里氏替换原则 (Liskov Substitution Principle)**: 子类可以替换父类
- **接口隔离原则 (Interface Segregation Principle)**: 使用多个专用接口，而不是一个通用接口
- **依赖倒置原则 (Dependency Inversion Principle)**: 依赖抽象而不是具体实现

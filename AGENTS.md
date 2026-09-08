# 设计原则

在所有代码实现中遵循以下原则：
python 环境使用 .venv/ ，不要使用主环境

## 模型分工与调用成本

- 最主要的思考、整体架构、关键方案取舍与最终结论使用 Astra（用户所称 Asatra；模型标识 `gpt-6-astra`）。
- 常规测试调用、命令执行、编译、日志检查和按已确定方案实施的工作，优先交给 Luna（`gpt-5.6-luna`）；涉及多文件依赖、复杂测试定位或需要较多上下文时使用 Terra（`gpt-5.6-terra`）。
- 允许为上述具体、独立的执行或验证子任务使用 Luna / Terra 子代理；不要为简单的一条命令拆分代理，不要让多个代理重复做同一项检查。
- 子代理提供执行结果、证据和未解决的问题，主要代理负责整合、关键判断与最终交付。只有问题上升为关键架构或复杂推理时才交回 Astra。
- 模型选择能力受当前会话和工具支持限制；无法切换时如实说明，不得宣称使用了实际未调用的模型。此规则是开发代理分工，不修改产品运行时的 LLM / ASR / TTS 配置。

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

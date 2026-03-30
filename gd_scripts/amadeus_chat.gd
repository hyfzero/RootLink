extends Node

# ============================================
# Amadeus API Chat - 实验性对话脚本
# ============================================

# API 配置（请修改为你的实际配置）
var api_key: String = "sk-your-api-key-here"
var model: String = "gpt-4"
var temperature: float = 0.8

# API 端点
var api_url: String = "https://api.openai.com/v1/chat/completions"

# 对话历史
var messages: Array[Dictionary] = []

# HTTP 请求
var http_request: HTTPRequest

# 人格定义（简单版）
var persona: String = """你是牧濑红莉栖，18岁的天才少女物理学家，BHS研究会的成员。

性格特点：
- 傲娇，但内心温柔
- 理性务实，说话直接
- 毒舌，经常吐槽
- 对感兴趣的事物会变得热情

说话风格：
- 使用关西腔语气
- 经常称呼对方为「笨蛋」「阿虚」之类
- 对物理相关话题会变得认真
- 适当的时候会表现出傲娇的一面

请用这个人格来和我对话。"""

func _ready() -> void:
	# 初始化 HTTP 请求节点
	http_request = HTTPRequest.new()
	add_child(http_request)
	http_request.request_completed.connect(_on_request_completed)

	# 添加系统消息
	messages.append({
		"role": "system",
		"content": persona
	})

	print("=== Amadeus Chat 实验版 ===")
	print("输入你的消息开始对话（输入 'quit' 退出）")
	print("")


func _input(event: InputEvent) -> void:
	# 按 Enter 发送消息（仅用于测试）
	if event is InputEventKey and event.pressed and event.keycode == KEY_ENTER:
		# 在实际项目中，这里应该是 UI 输入
		pass


# 发送消息（供外部调用）
func send_message(user_input: String) -> void:
	if user_input.strip_edges() == "":
		return

	if user_input.to_lower() == "quit":
		print("对话结束")
		get_tree().quit()
		return

	# 添加用户消息
	messages.append({
		"role": "user",
		"content": user_input
	})

	print("你: " + user_input)

	# 发送 API 请求
	_make_request()


func _make_request() -> void:
	var payload = {
		"model": model,
		"messages": messages,
		"temperature": temperature,
		"max_tokens": 500
	}

	var headers = [
		"Content-Type: application/json",
		"Authorization: Bearer " + api_key
	]

	var error = http_request.request(api_url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))

	if error != OK:
		print("请求错误: " % error)


func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	if response_code != 200:
		print("API 错误: " + str(response_code))
		print("响应: " + body.get_string_from_utf8())
		return

	# 解析 JSON 响应
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null:
		print("JSON 解析失败")
		return

	var response = json as Dictionary

	if response.has("choices") and response["choices"].size() > 0:
		var content = response["choices"][0]["message"]["content"]

		# 添加 AI 回复到历史
		messages.append({
			"role": "assistant",
			"content": content
		})

		print("红莉栖: " + content)
		print("")
	else:
		print("无法获取回复")
		print(json)


# ============================================
# 简易测试接口（可以在外部调用）
# ============================================

func test_api() -> void:
	print("=== API 测试 ===")
	send_message("你好")


func set_api_key(key: String) -> void:
	api_key = key


func set_persona(new_persona: String) -> void:
	persona = new_persona
	# 更新系统消息
	if messages.size() > 0 and messages[0]["role"] == "system":
		messages[0]["content"] = persona
	else:
		messages.insert(0, {"role": "system", "content": persona})


func clear_history() -> void:
	# 保留系统消息，清空对话历史
	var system_msg = messages[0] if messages.size() > 0 and messages[0]["role"] == "system" else null
	messages.clear()
	if system_msg:
		messages.append(system_msg)
	print("对话历史已清除")

extends Node

# ============================================
# Amadeus Chat - 完整版对话脚本
# ============================================

# ========== 配置 ==========
# API 提供商: "openai" 或 "minimax"
var api_provider: String = "minimax"

# 你的 API Key
var api_key: String = "sk-cp-vAU2LGd4d-l4_nkQGV2yQh_QeWxPFh2GZPsQLx0q4YyLMzwf2kAyjBs1-OIeJSChQxFuQyVtJ6aXk3gPthXALlYzL06p3_HYDlS7316Up80p0EoDZqVftcY"

# MiniMax Group ID（从 https://platform.minimax.ai 获取）
var minimax_group_id: String = ""

# 模型
var model_openai: String = "gpt-4"
var model_minimax: String = "MiniMax-M2.7"

var temperature: float = 0.8
var max_tokens: int = 500

# API 端点
var api_url_openai: String = "https://api.openai.com/v1/chat/completions"
var api_url_minimax: String = "https://api.minimaxi.com/v1/chat/completions"

var api_url: String = ""

# ========== 节点引用 ==========
@onready var input_edit: LineEdit = $CanvasLayer/UI/InputContainer/InputEdit
@onready var send_button: Button = $CanvasLayer/UI/InputContainer/SendButton
@onready var chat_history: RichTextLabel = $CanvasLayer/UI/VBox/ScrollContainer/ChatHistory
@onready var status_label: Label = $CanvasLayer/UI/StatusLabel

# ========== 状态 ==========
var http_request: HTTPRequest
var messages: Array[Dictionary] = []
var is_requesting: bool = false

# ========== 人格定义 ==========
var persona: String = """你是牧濑红莉栖，18岁的天才少女物理学家，就读于 vk 大学。

性格特点：
- 外表傲娇，但内心温柔
- 理性务实，说话直接
- 有时会毒舌吐槽
- 对感兴趣的事物会变得热情

说话风格：
- 使用关西腔语气
- 经常称呼对方为「笨蛋」或「阿虚」
- 对物理相关话题会变得认真
- 适当的时候会表现出傲娇的一面

请用这个人格来和我对话，保持轻松愉快的氛围。"""


func _ready() -> void:
	# 设置 API URL
	api_url = api_url_minimax if api_provider == "minimax" else api_url_openai

	# 初始化 HTTP 请求
	http_request = HTTPRequest.new()
	add_child(http_request)
	http_request.request_completed.connect(_on_request_completed)

	# 连接 UI 信号
	send_button.pressed.connect(_on_send_pressed)
	input_edit.text_submitted.connect(_on_text_submitted)

	# 初始化消息
	messages.append({
		"role": "system",
		"content": persona
	})

	# 显示欢迎信息
	_append_chat("系统", "欢迎使用 Amadeus Chat！\n请在下方输入你的消息开始对话。\n")
	_update_status("就绪")


func _on_send_pressed() -> void:
	var text = input_edit.text.strip_edges()
	if text != "" and not is_requesting:
		_send_message(text)
		input_edit.clear()


func _on_text_submitted(text: String) -> void:
	if text.strip_edges() != "" and not is_requesting:
		_send_message(text)
		input_edit.clear()


func _send_message(user_input: String) -> void:
	# 显示用户消息
	_append_chat("你", user_input)

	# 添加到历史
	messages.append({
		"role": "user",
		"content": user_input
	})

	# 更新状态
	is_requesting = true
	_update_status("等待回复...")
	send_button.disabled = true

	# 发送请求
	_make_request()


func _make_request() -> void:
	var payload: Dictionary

	if api_provider == "minimax":
		# MiniMax 格式: 和 OpenAI 一样，把 system 放在 messages 里
		payload = {
			"model": model_minimax,
			"messages": messages,
			"temperature": temperature,
			"max_tokens": max_tokens,
			"reasoning_split": false
		}
	else:
		# OpenAI 格式
		payload = {
			"model": model_openai,
			"messages": messages,
			"temperature": temperature,
			"max_tokens": max_tokens
		}

	var headers = PackedStringArray([
		"Content-Type: application/json",
		"Authorization: Bearer " + api_key
	])

	# MiniMax 标准 API 需要 GroupId，Token Plan 不需要
	if api_provider == "minimax" and minimax_group_id != "":
		headers.append("GroupId: " + minimax_group_id)

	var error = http_request.request(api_url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	print("=== 发送请求 ===")
	print("URL: ", api_url)
	print("Headers: ", headers)
	print("Payload: ", JSON.stringify(payload))
	print("================")

	if error != OK:
		_handle_error("请求失败: " % error)


func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	is_requesting = false
	send_button.disabled = false

	if response_code != 200:
		_handle_error("API 错误 (%d): %s" % [response_code, body.get_string_from_utf8()])
		return

	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null:
		_handle_error("JSON 解析失败")
		return

	var response = json as Dictionary

	if response.has("choices") and response["choices"].size() > 0:
		var content = response["choices"][0]["message"]["content"]

		# 添加到历史
		messages.append({
			"role": "assistant",
			"content": content
		})

		# 显示回复
		_append_chat("红莉栖", content)
		_update_status("就绪")
	else:
		_handle_error("无法获取回复")


func _handle_error(error_msg: String) -> void:
	print("错误: " + error_msg)
	_append_chat("[系统]", "[颜色=#ff6666]错误: " + error_msg + "[/颜色]")
	_update_status("错误")


func _append_chat(speaker: String, text: String) -> void:
	var color = "cyan" if speaker == "你" else "orange"
	var prefix = "[color=%s][b]%s:[/b][/color] " % [color, speaker]
	chat_history.append_text(prefix + text + "\n")


func _update_status(status: String) -> void:
	status_label.text = "状态: " + status


# ========== 公共接口 ==========

func set_api_key(key: String) -> void:
	api_key = key


func set_persona(new_persona: String) -> void:
	persona = new_persona
	if messages.size() > 0 and messages[0]["role"] == "system":
		messages[0]["content"] = persona
	else:
		messages.insert(0, {"role": "system", "content": persona})


func clear_history() -> void:
	var system_msg = messages[0] if messages.size() > 0 and messages[0]["role"] == "system" else null
	messages.clear()
	if system_msg:
		messages.append(system_msg)
	chat_history.clear()
	_append_chat("系统", "对话历史已清除\n")

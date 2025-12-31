from fastapi import APIRouter, HTTPException, Header
from app.database import db
import json

router = APIRouter()

# 1. 获取服务器基础配置
@router.post("/config/server-base")
async def get_server_base_config():
    """
    获取服务器基础配置
    """
    try:
        # 模拟服务器基础配置
        server_config = {
            "delete_audio": True,
            "ASR": {
                "ASR_FunASR": {
                    "type": "fun_local",
                    "model_dir": "models/SenseVoiceSmall",
                    "output_dir": "tmp/"
                }
            },
            "server": {
                "sms_max_send_count": 10,
                "fronted_url": "http://xiaozhi.server.com",
                "websocket": "ws://121.41.168.85:8000/xiaozhi/v1/",
                "name": "xiaozhi-esp32-server",
                "mcp_endpoint": "http://172.23.0.1:8004/mcp_endpoint/health?key=feeefd9e4ab54adf84f8db612a647754",
                "voice_print": "http://172.18.124.147:8005/voiceprint/health?key=61009ac6-0111-4532-98c5-95ee9fabf1f7",
                "secret": "443d967a-3538-443e-bb2a-45490c25d01a",
                "beian_ga_num": "null",
                "ota": "http://121.41.168.85:8002/xiaozhi/ota/",
                "beian_icp_num": "null",
                "allow_user_register": True,
                "enable_mobile_register": False
            },
            "enable_stop_tts_notify": True,
            "close_connection_no_voice_time": 120,
            "enable_wakeup_words_response_cache": False,
            "log": {
                "log_format_file": "{time:YYYY-MM-DD HH:mm:ss} - {version}_{selected_module} - {name} - {level} - {extra[tag]} - {message}",
                "log_dir": "tmp",
                "log_format": "<green>{time:YYMMDD HH:mm:ss}</green>[<light-blue>{version}-{selected_module}</light-blue>][<light-blue>{extra[tag]}</light-blue>]-<level>{level}</level>-<light-green>{message}</light-green>",
                "log_file": "server.log",
                "log_level": "INFO",
                "data_dir": "data"
            },
            "wakeup_words": [
                "捷宝宝", "你好小智", "你好小志", "小爱同学", "你好小鑫", 
                "你好小新", "小美同学", "小龙小龙", "喵喵同学", "小滨小滨", 
                "小冰小冰", "嘿你好呀"
            ],
            "selected_module": {
                "ASR": "ASR_FunASR",
                "VAD": "VAD_SileroVAD"
            },
            "enable_greeting": False,
            "end_prompt": {
                "enable": True,
                "prompt": "再见"
            },
            "exit_commands": ["none"],
            "tts_timeout": 10,
            "device_max_output_size": 0,
            "VAD": {
                "VAD_SileroVAD": {
                    "type": "silero",
                    "model_dir": "models/snakers4_silero-vad",
                    "threshold": "0.85",
                    "min_silence_duration_ms": "200"
                }
            },
            "summaryMemory": None,
            "stop_tts_notify_voice": "config/assets/tts_notify.mp3",
            "aliyun": {
                "sms": {
                    "access_key_id": "",
                    "sign_name": "",
                    "access_key_secret": "",
                    "sms_code_template_code": ""
                }
            },
            "prompt": None,
            "xiaozhi": {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60
                }
            }
        }

        return {
            "code": 0,
            "msg": "success",
            "data": server_config
        }
    except Exception as e:
        print(f"🔥 Server Base Config Error: {str(e)}")
        return {
            "code": 500,
            "msg": str(e),
            "data": None
        }

# 2. 获取代理模型配置
@router.post("/xiaozhi/config/agent-models")
async def get_agent_models_config(payload: dict):
    """
    获取代理模型配置
    payload示例:
    {
      "macAddress": "设备MAC地址",
      "clientId": "客户端ID",
      "selectedModule": {...} # 选择的模块
    }
    """
    try:
        # 模拟代理模型配置
        agent_models_config = {
            "plugins": {
                "get_weather": "{\"api_key\": \"3d9da0ec288743b89c6a3e47dae98e1e\", \"api_host\": \"py78kyqwtq.re.qweatherapi.com\", \"default_location\": \"广州\"}"
            },
            "Memory": {
                "Memory_mem_local_short": {
                    "llm": "LLM_AliLLM",
                    "type": "mem_local_short"
                }
            },
            "selected_module": {
                "TTS": "TTS_TencentTTS",
                "Memory": "Memory_mem_local_short",
                "Intent": "Intent_intent_llm",
                "LLM": "LLM_AliLLM",
                "VLLM": "VLLM_ChatGLMVLLM"
            },
            "Intent": {
                "Intent_intent_llm": {
                    "llm": "LLM_AliLLM",
                    "type": "intent_llm"
                }
            },
            "chat_history_conf": 2,
            "LLM": {
                "LLM_AliLLM": {
                    "type": "openai",
                    "top_k": "50",
                    "top_p": "1",
                    "api_key": "sk-a9aba32a903d4c9396c58213e67c6fd3",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "max_tokens": "500",
                    "model_name": "qwen-turbo-latest",
                    "temperature": "0.3",
                    "frequency_penalty": "0"
                }
            },
            "device_max_output_size": "0",
            "TTS": {
                "TTS_TencentTTS": {
                    "type": "tencent",
                    "appid": "1391329716",
                    "voice": "101001",
                    "region": "ap-guangzhou",
                    "secret_id": "AKIDhGrGTVKwNbbOyMXWHza2HI8vriS8dv3z",
                    "output_dir": "tmp/",
                    "secret_key": "a3M6g3GMOKCwjKjxynPr8D4mHagYFk15",
                    "private_voice": "101015"
                }
            },
            "mcp_endpoint": "ws://172.23.0.1:8004/mcp_endpoint/call/?token=ypigecvk6JqVWbXfeKJWf7W1grQa5FbZQuPW3Hm9QVA65Cs5XvoHdQYhGNi%2BLcaj",
            "voiceprint": {
                "speakers": [
                    "e3877b049aa7ca8863354f83418b9e1f,Tianhao,这是天豪,SIMULATION TEAM的实习生",
                    "2ef8f890252e057797565de6d6fc4f28,Alice,manager of simulation team",
                    "0f6b09bb29d23b90fb723fe7a01b0601,欣欣,5岁的小女孩，现在读中班了，爱运动，爱画画，足球踢得很好,是Alice的女儿，还有一个哥哥叫安安。"
                ],
                "url": "http://172.18.124.147:8005/voiceprint/health?key=61009ac6-0111-4532-98c5-95ee9fabf1f7"
            },
            "summaryMemory": "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。",
            "prompt": "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n",
            "VLLM": {
                "VLLM_ChatGLMVLLM": {
                    "type": "openai",
                    "api_key": "你的api_key",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                    "model_name": "glm-4v-flash"
                }
            }
        }

        print(f"💬 [AGENT MODELS CONFIG] Device: {payload.get('macAddress', 'unknown')}")
        print(f"   Client ID: {payload.get('clientId', 'unknown')}")
        
        return {
            "code": 0,
            "msg": "success",
            "data": agent_models_config
        }
    except Exception as e:
        print(f"🔥 Agent Models Config Error: {str(e)}")
        return {
            "code": 500,
            "msg": str(e),
            "data": None
        }

# 3. 获取设备差异化配置（兼容旧的API，但按照新的格式）
@router.post("/chat/diff-config")
async def get_chat_diff_config(
    payload: dict,
    x_username: str = Header(...),
    authorization: str = Header(...)
):
    """
    获取chat差异化配置
    payload示例:
    {
      "jabobo_id": "设备ID",
      "chat_context": "当前聊天上下文",
      "request_type": "配置请求类型",
      "custom_params": {} # 自定义参数
    }
    """
    if not db.connect(): 
        return {
            "code": 500,
            "msg": "数据库连接失败",
            "data": None
        }
    
    try:
        # 验证用户身份
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            return {
                "code": 401,
                "msg": "身份验证失败",
                "data": None
            }

        jabobo_id = payload.get('jabobo_id')
        chat_context = payload.get('chat_context', '')
        request_type = payload.get('request_type', 'default')
        custom_params = payload.get('custom_params', {})

        if not jabobo_id:
            return {
                "code": 400,
                "msg": "缺少 jabobo_id",
                "data": None
            }

        # 获取基础配置
        sql = "SELECT personas, memory FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        config = db.cursor.fetchone()

        base_personas = config.get('personas', "[]") if config else "[]"
        base_memory = config.get('memory', "") if config else ""

        # 根据聊天上下文和请求类型生成差异化配置
        diff_config = {
            "base_personas": json.loads(base_personas) if base_personas else [],
            "base_memory": base_memory,
            "diff_personas": [],  # 根据聊天上下文生成的差异化人设
            "diff_memory": "",    # 根据聊天上下文生成的差异化记忆
            "context_aware_params": {},  # 根据上下文调整的参数
            "response_style": "normal"   # 响应风格
        }

        # 示例：根据聊天上下文和请求类型调整配置
        if request_type == "formal":
            diff_config["response_style"] = "formal"
            diff_config["context_aware_params"]["temperature"] = 0.3
        elif request_type == "casual":
            diff_config["response_style"] = "casual"
            diff_config["context_aware_params"]["temperature"] = 0.8
        elif request_type == "knowledge_base":
            diff_config["response_style"] = "knowledge_base"
            diff_config["context_aware_params"]["use_memory"] = True

        # 可以根据custom_params进一步定制差异化配置
        if custom_params:
            diff_config["context_aware_params"].update(custom_params)

        print(f"💬 [CHAT DIFF CONFIG] User: {x_username}, Device: {jabobo_id}")
        print(f"   Request Type: {request_type}")
        print(f"   Chat Context Length: {len(chat_context)}")
        print(f"   Diff Config Generated: {diff_config['response_style']}")

        return {
            "code": 0,
            "msg": "success",
            "data": diff_config
        }
    except Exception as e:
        print(f"🔥 Chat Diff Config Error: {str(e)}")
        return {
            "code": 500,
            "msg": str(e),
            "data": None
        }
    finally:
        db.close()

# 4. 更新chat差异化配置
@router.put("/chat/diff-config")
async def update_chat_diff_config(
    payload: dict,
    x_username: str = Header(...),
    authorization: str = Header(...)
):
    """
    更新chat差异化配置
    payload示例:
    {
      "jabobo_id": "设备ID",
      "diff_config": {
        "diff_personas": [...],
        "diff_memory": "...",
        "context_aware_params": {...}
      }
    }
    """
    if not db.connect(): 
        return {
            "code": 500,
            "msg": "数据库连接失败",
            "data": None
        }
    
    try:
        # 验证用户身份
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            return {
                "code": 401,
                "msg": "身份验证失败",
                "data": None
            }

        jabobo_id = payload.get('jabobo_id')
        diff_config = payload.get('diff_config', {})

        if not jabobo_id:
            return {
                "code": 400,
                "msg": "缺少 jabobo_id",
                "data": None
            }

        # 这里可以实现将差异化配置保存到数据库的逻辑
        # 例如，可以创建一个新表存储差异化配置，或将其附加到现有配置中
        print(f"✏️ [UPDATE CHAT DIFF CONFIG] User: {x_username}, Device: {jabobo_id}")
        print(f"   Diff Config Updated: {diff_config}")

        return {
            "code": 0,
            "msg": "success",
            "data": diff_config
        }
    except Exception as e:
        print(f"🔥 Update Chat Diff Config Error: {str(e)}")
        return {
            "code": 500,
            "msg": str(e),
            "data": None
        }
    finally:
        db.close()

# 5. 获取chat上下文相关配置
@router.post("/chat/context-config")
async def get_chat_context_config(
    payload: dict,
    x_username: str = Header(...),
    authorization: str = Header(...)
):
    """
    根据聊天上下文获取配置
    payload示例:
    {
      "jabobo_id": "设备ID",
      "messages": [...],  # 聊天消息历史
      "topic": "当前话题",
      "emotion_state": "情感状态"
    }
    """
    if not db.connect(): 
        return {
            "code": 500,
            "msg": "数据库连接失败",
            "data": None
        }
    
    try:
        # 验证用户身份
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            return {
                "code": 401,
                "msg": "身份验证失败",
                "data": None
            }

        jabobo_id = payload.get('jabobo_id')
        messages = payload.get('messages', [])
        topic = payload.get('topic', '')
        emotion_state = payload.get('emotion_state', 'neutral')

        if not jabobo_id:
            return {
                "code": 400,
                "msg": "缺少 jabobo_id",
                "data": None
            }

        # 获取基础配置
        sql = "SELECT personas, memory FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        config = db.cursor.fetchone()

        base_personas = config.get('personas', "[]") if config else "[]"
        base_memory = config.get('memory', "") if config else ""

        # 分析聊天上下文并生成适应性配置
        context_analysis = {
            "topic_relevance": 0.8,  # 主题相关性
            "emotion_adaptation": emotion_state,  # 情感适配
            "personality_adjustment": "medium",  # 人格调整程度
            "response_tone": "adaptive"  # 回复语调
        }

        # 根据话题和情感状态调整配置
        if emotion_state == "happy":
            context_analysis["response_tone"] = "cheerful"
        elif emotion_state == "sad":
            context_analysis["response_tone"] = "comforting"
        elif emotion_state == "angry":
            context_analysis["response_tone"] = "calming"

        adaptive_config = {
            "base_config": {
                "personas": json.loads(base_personas) if base_personas else [],
                "memory": base_memory
            },
            "context_analysis": context_analysis,
            "adaptive_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "presence_penalty": 0.5,
                "frequency_penalty": 0.3
            },
            "context_specific_rules": []
        }

        print(f"🧠 [CONTEXT CONFIG] User: {x_username}, Device: {jabobo_id}")
        print(f"   Topic: {topic}")
        print(f"   Emotion State: {emotion_state}")
        print(f"   Message Count: {len(messages)}")

        return {
            "code": 0,
            "msg": "success",
            "data": adaptive_config
        }
    except Exception as e:
        print(f"🔥 Context Config Error: {str(e)}")
        return {
            "code": 500,
            "msg": str(e),
            "data": None
        }
    finally:
        db.close()
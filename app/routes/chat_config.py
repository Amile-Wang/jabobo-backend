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
                "beian_ga_num": "None",
                "ota": "http://121.41.168.85:8002/xiaozhi/ota/",
                "beian_icp_num": "None",
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
                "捷宝宝",
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
            "exit_commands": [
                "none"
            ],
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
@router.post("/config/agent-models")
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
                    "type": "intent_llm",
                    "chat_history_conf": 2
                }
            },
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
                    "frequency_penalty": "0",
                    "device_max_output_size": "0"
                }
            },
            "TTS": {
                "TTS_TencentTTS": {
                    "type": "tencent",
                    "appid": "1391329716",
                    "voice": "101001",
                    "region": "ap-guangzhou",
                    "secret_id": "AKIDhGrGTVKwNbbOyMXWHza2HI8vriS8dv3z",
                    "output_dir": "tmp/",
                    "secret_key": "a3M6g3GMOKCwjKjxynPr8D4mHagYFk15",
                    "private_voice": "101015",
                    "mcp_endpoint": "ws://172.23.0.1:8004/mcp_endpoint/call/?token=ypigecvk6JqVWbXfeKJWf7W1grQa5FbZQuPW3Hm9QVA65Cs5XvoHdQYhGNi%2BLcaj"
                }
            },
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

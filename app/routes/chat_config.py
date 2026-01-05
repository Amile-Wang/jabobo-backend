# ... existing code ...
from fastapi import APIRouter, HTTPException, Header, Path
from app.database import db
import json
from typing import Dict, Any  # 添加typing导入


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
        # 从payload中获取设备信息
        mac_address = payload.get('macAddress', '')
        client_id = payload.get('clientId', '')
        
        print(f"💬 [AGENT MODELS CONFIG] Device: {mac_address}")
        print(f"   Client ID: {client_id}")
        
        # 从数据库获取设备特定配置，包括人设(prompt)和记忆(summaryMemory)
        device_prompt, device_memory = await get_device_config(mac_address)
        
        # 模拟代理模型配置
        agent_models_config = {
            "plugins": {
                "get_weather": "{\"api_key\": \"3d9da0ec288743b89c6a3e47dae98e1e\", \"api_host\": \"py78kyqwtq.re.qweatherapi.com\", \"default_location\": \"广州\"}"
            },
            "Memory": {
                "Memory_mem_local_short": {
                    "llm": "LLM_DeepSeekLLM",
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
                    "frequency_penalty": "0",
                    "device_max_output_size": "0"
                },
                "LLM_DeepSeekLLM": {
                    "type": "openai", 
                    "top_k": "", 
                    "top_p": "", 
                    "api_key": "sk-43753ec3b99443a9911156d9cb3d2e4d", 
                    "base_url": "https://api.deepseek.com", 
                    "max_tokens": "", 
                    "model_name": "deepseek-chat", 
                    "temperature": "", 
                    "frequency_penalty": ""
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
            "summaryMemory": device_memory,  # 从数据库获取设备特定的记忆
            # 从数据库获取设备特定的prompt
            "prompt": device_prompt,
            "VLLM": {
                "VLLM_ChatGLMVLLM": {
                    "type": "openai",
                    "api_key": "你的api_key",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                    "model_name": "glm-4v-flash"
                }
            }
        }
                      
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

# 新增函数：根据设备MAC地址获取设备配置（人设和记忆）
async def get_device_config(jabobo_id: str) -> tuple:
    """
    根据设备ID获取设备特定的配置（人设和记忆）
    :param jabobo_id: 设备ID（MAC地址）
    :return: (设备人设内容, 设备记忆内容)
    """
    if not jabobo_id:
        # 如果没有提供设备ID，返回默认值
        default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
        default_memory = "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。"
        return default_prompt, default_memory
    
    connection = None
    try:
        # 检查数据库连接
        connection = db.connect()
        if not connection:
            print("🔥 Database connection failed")
            default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
            default_memory = "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。"
            return default_prompt, default_memory
        
        # 查询user_personas表中对应设备ID的人设和记忆
        sql = "SELECT personas, memory FROM user_personas WHERE jabobo_id = %s"
        cursor = db.cursor
        cursor.execute(sql, (jabobo_id,))
        result = cursor.fetchone()
        
        print(f"🔍 Query result for {jabobo_id}: {result}")  # 添加调试信息
        
        if result:
            # 根据游标类型处理结果，如果是字典游标则使用键访问，否则使用索引
            if isinstance(result, dict):
                personas_json = result['personas']  # 使用键访问
                memory_content = result.get('memory', '')  # 获取记忆内容
            else:
                personas_json = result[0]  # 使用索引访问
                memory_content = result[1] if len(result) > 1 else ''  # 获取记忆内容
            
            print(f"🔍 Personas JSON: {personas_json}")  # 添加调试信息
            print(f"🔍 Memory content: {memory_content}")  # 添加调试信息
            
            if personas_json:  # 确保 personas_json 不为空
                personas_list = json.loads(personas_json)
                print(f"🔍 Personas list: {personas_list}")  # 添加调试信息
                
                # 返回第一个可用的人设对象的所有信息
                if personas_list and len(personas_list) > 0:
                    first_persona = personas_list[0]
                    # 将整个对象转换为字符串返回
                    device_prompt = json.dumps(first_persona, ensure_ascii=False)
                    return device_prompt, memory_content or "设备没有特定记忆信息"
            
            # 如果解析后没有内容，返回默认值
            default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
            return default_prompt, memory_content or "设备没有特定记忆信息"
        else:
            # 如果设备ID没有找到对应的配置，返回默认值
            print(f"⚠️ No config found for device ID: {jabobo_id}")
            default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
            default_memory = "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。"
            return default_prompt, default_memory
    except json.JSONDecodeError as e:
        print(f"🔥 JSON Decode Error when fetching device config: {str(e)}")
        # JSON解析错误时返回默认值
        default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
        default_memory = "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。"
        return default_prompt, default_memory
    except Exception as e:
        print(f"🔥 Database Error when fetching device config: {str(e)} - Type: {type(e).__name__}")
        # 发生错误时返回默认值
        default_prompt = "你叫捷宝宝，今年三岁了。\n最喜欢和小朋友聊天，回答他们各种各样的问题，给他们讲故事。\n除非小朋友要求你讲故事，这时候将对话控制内容控制在150字以内。\n\n"
        default_memory = "捷宝宝的主要开发人员：除了天豪 ，Alice Lin， Roshan Gao，以及simulation team的小伙伴们，还有AI专家Thomas Du, 硬件大佬Kris Chen,用户体验设计师Alessia Zhang，\n此外，还有特邀顾问团队。"
        return default_prompt, default_memory
    finally:
        # 关闭数据库连接
        if connection:
            db.close()
            
def verify_device_exists(mac_address: str):
    """
    验证设备是否存在
    """
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 检查设备是否存在于user_personas表中，使用mac_address作为jabobo_id
        sql = "SELECT jabobo_id FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (mac_address,))
        device = db.cursor.fetchone()
        
        if not device:
            return False
        return True
    finally:
        db.close()

@router.put("/agent/saveMemory/{mac_address}")
async def save_memory(
    mac_address: str = Path(..., description="设备MAC地址"),
    summary_memory: Dict[str, Any] = None,
    user_agent: str = Header(..., alias="User-Agent"),
    accept: str = Header(..., alias="Accept"),
    authorization: str = Header(..., alias="Authorization")
):
    """
    保存短期记忆到服务器
    - 请求方法: PUT
    - 请求路径: /agent/saveMemory/{mac_address}
    - 验证JWT Token认证
    - 根据MAC地址存储记忆到数据库
    """
    print(f"🧠 [MEMORY SAVE] Request received for MAC: {mac_address}")
    print(f"   User-Agent: {user_agent}")
    print(f"   Accept: {accept}")
    print(f"   Authorization: {authorization}")
    
    # 验证Authorization头部格式
    if not authorization.startswith("Bearer "):
        return {
            "code": 401,
            "data": None,
            "msg": "Authorization header format must be 'Bearer {token}'"
        }
    
    # 验证设备是否存在
    if not verify_device_exists(mac_address):
        print(f"❌ [MEMORY SAVE] Device with MAC {mac_address} not found")
        return {
            "code": 10041,
            "data": None,
            "msg": "设备未找到异常"
        }
    
    # 验证请求体
    if not summary_memory or "summaryMemory" not in summary_memory:
        return {
            "code": 400,
            "data": None,
            "msg": "请求体中必须包含summaryMemory字段"
        }
    
    summary_content = summary_memory["summaryMemory"]
    
    # 连接数据库并更新记忆
    if not db.connect():
        return {
            "code": 500,
            "data": None,
            "msg": "数据库连接失败"
        }
    
    try:
        # 更新指定设备的记忆数据
        sql = """
            UPDATE user_personas 
            SET memory = %s 
            WHERE jabobo_id = %s
        """
        db.cursor.execute(sql, (summary_content, mac_address))
        
        if db.cursor.rowcount == 0:
            # 如果没有更新任何行，可能意味着设备不存在
            print(f"❌ [MEMORY SAVE] No device found with MAC {mac_address}")
            return {
                "code": 10041,
                "data": None,
                "msg": "设备未找到异常"
            }
        
        print(f"✅ [MEMORY SAVE] Memory updated successfully for MAC: {mac_address}")
        print(f"   New memory content: {summary_content[:100]}...")  # 只打印前100个字符
        
        return {
            "code": 0,
            "data": {
                "mac_address": mac_address,
                "summary_memory": summary_content
            },
            "msg": "短期记忆保存成功"
        }
        
    except Exception as e:
        print(f"❌ [MEMORY SAVE] Error saving memory for MAC {mac_address}: {str(e)}")
        return {
            "code": 500,
            "data": None,
            "msg": f"保存记忆时发生错误: {str(e)}"
        }
    finally:
        db.close()
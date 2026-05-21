import asyncio
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Query, Body
from loguru import logger

from app.database import db
from app.utils.security import get_valid_cursor, verify_user

# ── 唤醒词训练后台任务 ──────────────────────────────────────────────
_TRAIN_WORK_DIR = Path("/home/azureuser/tianhao/my_code/Jabobo/wakeword train")
_TRAIN_CONDA_ENV = "wakeword"
_TRAIN_LOG_DIR = _TRAIN_WORK_DIR / "_training_logs"

# 进程内缓存：{wake_word: {"status": "running"|"done"|"failed", "message": str}}
_wake_word_tasks: dict[str, dict] = {}


def _normalize_wake_word(text: str) -> str:
    """将用户输入的任意文本转为 code name（小写、下划线、去标点）。
    
    例: "Hey Jabra"  → "hey_jabra"
         "hey，jabra" → "hey_jabra"
         "Hi, Tianhao!" → "hi_tianhao"
         "hi，Jabra" → "hi_jabra"
         "hello world" → "hello_world"
    """
    import re
    # 分隔性标点（逗号、句号、问号、感叹号、分号等）先转空格，保留分词标记
    # 避免全角逗号转逗号后被 regex 去掉，导致 "hi，Jabra" → "hiJabra" → "hijabra"
    for ch in ("，", "。", "、", "；", "：", "！", "？", "．"):
        text = text.replace(ch, " ")
    # 全角空格/其他全角符号转半角
    text = text.replace("\u3000", " ").replace(" ", " ")
    # 英文逗号等非分隔标点也转空格（对齐中文分隔行为）
    text = re.sub(r"[,\\.!?;:]", " ", text)
    # 去除非字母数字 / 下划线 / 空格
    cleaned = re.sub(r"[^a-zA-Z0-9_ ]", "", text)
    # 空格转下划线
    cleaned = cleaned.replace(" ", "_")
    # 合并连续下划线、去头尾下划线
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower()


def _wake_word_to_display(name: str) -> str:
    """hi_jabra -> Hi Jabra（无逗号，适合做 --text 参数）"""
    parts = name.split("_")
    return " ".join(p.capitalize() for p in parts)


async def _run_wakeword_training(wake_word: str, device_id: str, display_text: str | None = None):
    """后台异步执行 train_wakeword.py + deploy_wakeword.py，完成后更新 DB。

    逻辑：
    1. 检查 trained_models/<wake_word>/<wake_word>.tflite 是否存在
    2. 如果已存在 → 直接 deploy 跳过训练
    3. 如果不存在 → 用指定参数训练（快速语速、多 voice、不同样本数），再 deploy

    display_text: 用户输入的原始文本（如"嘿小捷"、"Hello Ryder"），传给 TTS 作为 --text
    """
    # 根据唤醒词内容选择 voices：含中文字符用中文 voices，否则用英文 voices
    EN_VOICES = ("lessac", "amy", "joe", "alan", "norman", "libritts_r")
    ZH_VOICES = ("chaowen", "huayan", "xiao_ya")
    tts_text = display_text if display_text else _wake_word_to_display(wake_word)
    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in tts_text)
    selected_voices = ZH_VOICES if has_chinese else EN_VOICES
    logger.info(f"🧠 [WAKE WORD] Detected {'Chinese' if has_chinese else 'English'} wake word, using voices: {', '.join(selected_voices)}")

    status_key = f"{wake_word}@{device_id}"
    start_time = datetime.now()
    _wake_word_tasks[status_key] = {"status": "running", "message": "训练中...", "elapsed_seconds": None, "start_time": start_time.isoformat()}
    logger.info(f"🧠 [WAKE WORD] Starting training for '{wake_word}' (device={device_id})")

    _TRAIN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _TRAIN_LOG_DIR / f"{wake_word}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # ── 检查模型是否已存在 ──
    model_path = _TRAIN_WORK_DIR / "trained_models" / wake_word / f"{wake_word}.tflite"
    model_exists = model_path.exists()

    try:
        if not model_exists:
            # ── 训练：生成 TTS 样本 ──
            # 用用户输入的原文（如"嘿小捷"）做 --text；如果没有就 fallback 从 code name 生成
            length_scales = "0.7 0.85 1.0 1.15 1.3"

            cmd_generate = [
                "conda", "run", "-n", _TRAIN_CONDA_ENV,
                "python", str(_TRAIN_WORK_DIR / "train_wakeword.py"),
                wake_word,
                "--generate-samples",
                "--text", tts_text,
                "--max-samples", "250",
                "--voices", *selected_voices,
                "--length-scales", *length_scales.split(),
            ]
            logger.info(f"🧠 [WAKE WORD] Generating samples: {' '.join(cmd_generate)}")
            with open(log_path, "w") as log:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_generate,
                    cwd=str(_TRAIN_WORK_DIR),
                    stdout=log, stderr=subprocess.STDOUT,
                )
                await proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(f"train_wakeword.py (generate) exited with code {proc.returncode}")

            # ── 训练模型（不生成样本，只跑特征+训练） ──
            cmd_train = [
                "conda", "run", "-n", _TRAIN_CONDA_ENV,
                "python", str(_TRAIN_WORK_DIR / "train_wakeword.py"),
                wake_word,
            ]
            logger.info(f"🧠 [WAKE WORD] Running training: {' '.join(cmd_train)}")
            with open(log_path, "a") as log:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_train,
                    cwd=str(_TRAIN_WORK_DIR),
                    stdout=log, stderr=subprocess.STDOUT,
                )
                await proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(f"train_wakeword.py (train) exited with code {proc.returncode}")

            logger.success(f"✅ [WAKE WORD] Training succeeded for '{wake_word}'")
        else:
            logger.info(f"✅ [WAKE WORD] Model already exists for '{wake_word}', skipping training")

        # ── 部署 ──
        cmd_deploy = [
            "conda", "run", "-n", _TRAIN_CONDA_ENV,
            "python", str(_TRAIN_WORK_DIR / "deploy_wakeword.py"),
            wake_word,
        ]
        logger.info(f"🧠 [WAKE WORD] Running deploy: {' '.join(cmd_deploy)}")
        with open(log_path, "a") as log:
            proc = await asyncio.create_subprocess_exec(
                *cmd_deploy,
                cwd=str(_TRAIN_WORK_DIR),
                stdout=log, stderr=subprocess.STDOUT,
            )
            await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"deploy_wakeword.py exited with code {proc.returncode}")

        # 更新 DB model_status = 1 (ready)
        _update_wake_word_status(device_id, 1)
        action = "Deploy" if model_exists else "Training + deploy"
        _wake_word_tasks[status_key] = {
            "status": "done",
            "message": f"{action}完成，模型已部署",
            "elapsed_seconds": int((datetime.now() - start_time).total_seconds()),
            "start_time": start_time.isoformat(),
        }
        logger.success(f"✅ [WAKE WORD] {action} succeeded for '{wake_word}'")

    except Exception as e:
        logger.error(f"🔥 [WAKE WORD] Failed for '{wake_word}': {e}")
        _update_wake_word_status(device_id, 2)
        _wake_word_tasks[status_key] = {
            "status": "failed",
            "message": str(e),
            "elapsed_seconds": int((datetime.now() - start_time).total_seconds()),
            "start_time": start_time.isoformat(),
        }


def _update_wake_word_status(device_id: str, status: int):
    """更新指定设备的 wake_word_model_status 到数据库。"""
    try:
        if not db.connect():
            logger.error("🔥 [WAKE WORD] DB connect failed in status update")
            return
        cursor = db.connection.cursor()
        cursor.execute(
            "UPDATE user_personas SET wake_word_model_status = %s WHERE jabobo_id = %s",
            (status, device_id),
        )
        db.connection.commit()
        cursor.close()
        db.close()
    except Exception as e:
        logger.error(f"🔥 [WAKE WORD] DB update failed: {e}")


# ── 路由 ─────────────────────────────────────────────────────────────

router = APIRouter()

# TTS provider 内置默认音色 ID（前端展示，不允许用户自定义条目使用同名 ID）
DEFAULT_AZURE_VOICE_ID = "zh-CN-XiaoxiaoNeural"
DEFAULT_HUOSHAN_VOICE_ID = "custom_mix_bigtts"


def _parse_voice_list(raw, *, default_id: str) -> list:
    """把 DB 里存的 JSON 列解析成 [{id, name}] 列表，失败回退空数组。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    else:
        parsed = raw
    if not isinstance(parsed, list):
        return []
    out = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        vid = str(item.get("id", "")).strip()
        if not vid or vid == default_id:
            continue
        vname = str(item.get("name", "")).strip() or vid
        out.append({"id": vid, "name": vname})
    return out


def _validate_voice_list(raw, *, default_id: str, field_name: str) -> str | None:
    """前端提交的 voice list 校验；返回 JSON 字符串，None 表示落库 NULL。"""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是数组")
    if len(raw) > 32:
        raise HTTPException(status_code=400, detail=f"{field_name} 最多 32 项")
    cleaned = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"{field_name} 每项必须是对象")
        vid = str(item.get("id", "")).strip()
        vname = str(item.get("name", "")).strip()
        if not vid:
            raise HTTPException(status_code=400, detail=f"{field_name} id 不能为空")
        if len(vid) > 128:
            raise HTTPException(status_code=400, detail=f"{field_name} id 过长")
        if len(vname) > 64:
            raise HTTPException(status_code=400, detail=f"{field_name} name 过长")
        if vid == default_id:
            raise HTTPException(status_code=400, detail=f"{field_name} 不能包含内置默认 ID {default_id}")
        if vid in seen:
            raise HTTPException(status_code=400, detail=f"{field_name} id 重复: {vid}")
        seen.add(vid)
        cleaned.append({"id": vid, "name": vname or vid})
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def _validate_voice_id(raw, *, field_name: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是字符串")
    s = raw.strip()
    if not s:
        return None
    if len(s) > 128:
        raise HTTPException(status_code=400, detail=f"{field_name} 过长")
    return s


# 2. 获取【特定设备】的配置
@router.get("/user/config")
async def get_user_config(
    jabobo_id: str = Query(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    db_connected = False
    try:
        # 1. 数据库连接
        db_connected = db.connect()
        if not db_connected:
            logger.error("❌ [GET CONFIG] 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 用户token校验
        verify_user(x_username, authorization)
        
        # 3. 获取有效游标
        cursor = get_valid_cursor()

        # SQL查询添加版本号字段
        sql = (
            "SELECT personas, memory, current_version, expected_version, force_install, "
            "websocket_url, websocket_url_list, asr_provider, tts_provider, llm_provider, "
            "azure_tts_voice_id, azure_tts_voice_list, "
            "huoshan_tts_voice_id, huoshan_tts_voice_list, "
            "rag_enabled, "
            "wake_word_text, wake_word_model_status "
            "FROM user_personas "
            "WHERE username = %s AND jabobo_id = %s"
        )
        cursor.execute(sql, (x_username, jabobo_id))
        config = cursor.fetchone()

        # 分层读取+兜底
        if config is None:
            raw_persona = "[]"
            memory_data = ""
            current_version = "1.0.0"
            expected_version = ""
            force_install = 0
            websocket_url = ""
            websocket_url_list_raw = ""
            asr_provider = ""
            tts_provider = ""
            llm_provider = ""
            azure_voice_id = ""
            azure_voice_list_raw = None
            huoshan_voice_id = ""
            huoshan_voice_list_raw = None
            rag_enabled = False
            wake_word_text = ""
            wake_word_model_status = 0
            logger.info(f"ℹ️ [GET CONFIG] 未找到记录，为用户 {x_username} 使用默认配置")
        else:
            raw_persona = config.get('personas') or "[]"
            memory_data = config.get('memory') or ""
            current_version = config.get('current_version') or "1.0.0"
            expected_version = config.get('expected_version') or ""
            try:
                force_install = int(config.get('force_install') or 0)
            except (TypeError, ValueError):
                force_install = 0
            websocket_url = config.get('websocket_url') or ""
            websocket_url_list_raw = config.get('websocket_url_list') or ""
            asr_provider = config.get('asr_provider') or ""
            tts_provider = config.get('tts_provider') or ""
            llm_provider = config.get('llm_provider') or ""
            azure_voice_id = config.get('azure_tts_voice_id') or ""
            azure_voice_list_raw = config.get('azure_tts_voice_list')
            huoshan_voice_id = config.get('huoshan_tts_voice_id') or ""
            huoshan_voice_list_raw = config.get('huoshan_tts_voice_list')
            rag_enabled = bool(config.get('rag_enabled') or 0)
            wake_word_text = config.get('wake_word_text') or ""
            wake_word_model_status = int(config.get('wake_word_model_status') or 0)

        # websocket_url_list 是 JSON 数组，统一归一为 [{name, url}]
        # 历史数据可能是 ["wss://..."] 形式，无名字时 name 留空
        try:
            raw_list = json.loads(websocket_url_list_raw) if websocket_url_list_raw else []
            if not isinstance(raw_list, list):
                raw_list = []
        except (json.JSONDecodeError, TypeError):
            raw_list = []
        websocket_url_list = []
        for item in raw_list:
            if isinstance(item, str):
                u = item.strip()
                if u:
                    websocket_url_list.append({"name": "", "url": u})
            elif isinstance(item, dict):
                u = (item.get("url") or "").strip()
                n = (item.get("name") or "").strip()
                if u:
                    websocket_url_list.append({"name": n, "url": u})
        
        # 数据类型统一+安全处理
        raw_persona = str(raw_persona).strip() if raw_persona else "[]"
        memory_str = str(memory_data).strip() if memory_data else ""
        current_version = str(current_version).strip() or "1.0.0"
        expected_version = str(expected_version).strip()

        final_persona = raw_persona if raw_persona else "[]"

        # 使用 loguru 结构化打印日志
        logger.info(f"🔍 [GET CONFIG] User: {x_username} | Device: {jabobo_id}")
        logger.debug(f"📊 Data Stats: Persona: {len(final_persona)} chars | Memory: {len(memory_str)} chars")
        logger.info(f"📌 Version: Current={current_version} | Expected={expected_version}")

        return {
            "success": True,
            "data": {
                "persona": final_persona,
                "memory": memory_str,
                "voice_status": "已就绪",
                "kb_status": "已同步",
                "current_version": current_version,
                "expected_version": expected_version,
                "force_install": force_install,
                "websocket_url": websocket_url,
                "websocket_url_list": websocket_url_list,
                "asr_provider": asr_provider,
                "tts_provider": tts_provider,
                "llm_provider": llm_provider,
                "azure_tts_voice_id": azure_voice_id,
                "azure_tts_voice_list": _parse_voice_list(azure_voice_list_raw, default_id=DEFAULT_AZURE_VOICE_ID),
                "huoshan_tts_voice_id": huoshan_voice_id,
                "huoshan_tts_voice_list": _parse_voice_list(huoshan_voice_list_raw, default_id=DEFAULT_HUOSHAN_VOICE_ID),
                "rag_enabled": rag_enabled,
                "wake_word_text": wake_word_text,
                "wake_word_model_status": wake_word_model_status,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔥 [GET CONFIG 未知错误] User: {x_username} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail="获取配置失败，请重试")
    finally:
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass

# 3. 同步【特定设备】的配置
@router.post("/user/sync-config")
async def sync_config(
    payload: dict = Body(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    db_connected = False
    try:
        # 1. 数据库连接
        db_connected = db.connect()
        if not db_connected:
            logger.error("❌ [SYNC CONFIG] 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 多端token校验
        verify_user(x_username, authorization)
        
        # 2. 获取有效游标
        cursor = get_valid_cursor()

        # 3. 参数解析 + 严格校验
        jabobo_id = payload.get('jabobo_id', '').strip()
        persona_json = payload.get('persona', '[]') if payload.get('persona') is not None else '[]'
        memory = payload.get('memory', '') if payload.get('memory') is not None else ''
        ws_url_raw = payload.get('websocket_url', '')
        websocket_url = ws_url_raw.strip() if isinstance(ws_url_raw, str) and ws_url_raw.strip() else None

        # websocket_url_list: 用户保存的候选 WS 服务器列表，每项 {name, url}
        # 兼容旧前端可能仍发字符串数组的情况；按 url 去重
        ws_list_raw = payload.get('websocket_url_list', None)
        if isinstance(ws_list_raw, list):
            cleaned = []
            seen = set()
            for item in ws_list_raw:
                if isinstance(item, str):
                    u = item.strip()
                    n = ""
                elif isinstance(item, dict):
                    u = (item.get("url") or "").strip() if isinstance(item.get("url"), str) else ""
                    n = (item.get("name") or "").strip() if isinstance(item.get("name"), str) else ""
                else:
                    continue
                if not u or u in seen:
                    continue
                seen.add(u)
                cleaned.append({"name": n, "url": u})
            websocket_url_list_json = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        else:
            websocket_url_list_json = None

        # ASR/TTS/LLM 模型选择，仅接受白名单内取值
        ALLOWED_ASR = {"funasr", "azure_asr"}
        ALLOWED_TTS = {"huoshan_double_stream", "azure_tts"}
        ALLOWED_LLM = {"qwen-turbo", "deepseek-v4-flash", "gpt-5.4-nano"}
        asr_raw = payload.get('asr_provider', '')
        tts_raw = payload.get('tts_provider', '')
        llm_raw = payload.get('llm_provider', '')
        asr_provider = asr_raw.strip() if isinstance(asr_raw, str) else ''
        tts_provider = tts_raw.strip() if isinstance(tts_raw, str) else ''
        llm_provider = llm_raw.strip() if isinstance(llm_raw, str) else ''
        if asr_provider and asr_provider not in ALLOWED_ASR:
            raise HTTPException(status_code=400, detail=f"asr_provider 非法: {asr_provider}")
        if tts_provider and tts_provider not in ALLOWED_TTS:
            raise HTTPException(status_code=400, detail=f"tts_provider 非法: {tts_provider}")
        if llm_provider and llm_provider not in ALLOWED_LLM:
            raise HTTPException(status_code=400, detail=f"llm_provider 非法: {llm_provider}")
        asr_provider_db = asr_provider or None
        tts_provider_db = tts_provider or None
        llm_provider_db = llm_provider or None

        # TTS 音色：每个 provider 独立一份 (selected_id, custom_list)
        azure_voice_id_db = _validate_voice_id(
            payload.get('azure_tts_voice_id'), field_name='azure_tts_voice_id'
        )
        azure_voice_list_db = _validate_voice_list(
            payload.get('azure_tts_voice_list'),
            default_id=DEFAULT_AZURE_VOICE_ID,
            field_name='azure_tts_voice_list',
        )
        huoshan_voice_id_db = _validate_voice_id(
            payload.get('huoshan_tts_voice_id'), field_name='huoshan_tts_voice_id'
        )
        huoshan_voice_list_db = _validate_voice_list(
            payload.get('huoshan_tts_voice_list'),
            default_id=DEFAULT_HUOSHAN_VOICE_ID,
            field_name='huoshan_tts_voice_list',
        )

        # rag_enabled: 对话路径是否触发 /generate-rag-prompt，不影响知识库上传
        rag_enabled_db = 1 if bool(payload.get('rag_enabled', False)) else 0

        # wake_word: 用户自定义唤醒词文本 + 模型状态（0=none, 1=ready/training, 2=failed）
        wake_word_text_db = payload.get('wake_word_text', None)
        wake_word_raw_text = None  # 保存用户原始输入文本，传给训练作为 --text
        if wake_word_text_db is not None:
            raw = str(wake_word_text_db).strip()
            if raw:
                wake_word_raw_text = raw  # 保留原文（如 "嘿小捷"、"Hello Ryder"）
                wake_word_text_db = _normalize_wake_word(raw)
            else:
                wake_word_text_db = None
        wake_word_model_status_db = payload.get('wake_word_model_status', None)
        if wake_word_model_status_db is not None:
            try:
                wake_word_model_status_db = int(wake_word_model_status_db)
                if wake_word_model_status_db not in (0, 1, 2):
                    wake_word_model_status_db = 0
            except (TypeError, ValueError):
                wake_word_model_status_db = None

        if not jabobo_id:
            logger.warning(f"⚠️ [SYNC CONFIG] User {x_username} 提交的 payload 缺少 jabobo_id")
            raise HTTPException(status_code=400, detail="缺少 jabobo_id")
        
        # 支持MAC格式和6位纯数字格式校验
        is_mac_format = len(jabobo_id) == 17 and jabobo_id.count(':') == 5
        is_6digit_format = len(jabobo_id) == 6 and jabobo_id.isdigit()
        
        if not (is_mac_format or is_6digit_format):
            logger.warning(f"⚠️ [SYNC CONFIG] 非法设备ID格式: {jabobo_id} (User: {x_username})")
            raise HTTPException(
                status_code=400,
                detail="设备ID格式非法（应为xx:xx:xx:xx:xx:xx或6位纯数字）"
            )

        # 校验JSON
        try:
            json.loads(persona_json)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [SYNC CONFIG] Persona JSON格式错误: {str(e)}")
            raise HTTPException(status_code=400, detail="persona 不是合法的JSON字符串")

        logger.info(f"🚀 [SYNC CONFIG] Request from User: {x_username} for Device: {jabobo_id}")

        # 写入数据库
        sql = """
            INSERT INTO user_personas
                (username, jabobo_id, personas, memory,
                 websocket_url, websocket_url_list, asr_provider, tts_provider, llm_provider,
                 azure_tts_voice_id, azure_tts_voice_list,
                 huoshan_tts_voice_id, huoshan_tts_voice_list,
                 rag_enabled, wake_word_text, wake_word_model_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                personas = VALUES(personas),
                memory = VALUES(memory),
                websocket_url = VALUES(websocket_url),
                websocket_url_list = VALUES(websocket_url_list),
                asr_provider = VALUES(asr_provider),
                tts_provider = VALUES(tts_provider),
                llm_provider = VALUES(llm_provider),
                azure_tts_voice_id = VALUES(azure_tts_voice_id),
                azure_tts_voice_list = VALUES(azure_tts_voice_list),
                huoshan_tts_voice_id = VALUES(huoshan_tts_voice_id),
                huoshan_tts_voice_list = VALUES(huoshan_tts_voice_list),
                rag_enabled = VALUES(rag_enabled),
                wake_word_text = VALUES(wake_word_text),
                wake_word_model_status = VALUES(wake_word_model_status)
        """
        cursor.execute(sql, (
            x_username, jabobo_id, persona_json, memory,
            websocket_url, websocket_url_list_json, asr_provider_db, tts_provider_db, llm_provider_db,
            azure_voice_id_db, azure_voice_list_db,
            huoshan_voice_id_db, huoshan_voice_list_db,
            rag_enabled_db,
            wake_word_text_db, wake_word_model_status_db,
        ))
        db.connection.commit()
        
        logger.success(f"✅ [SYNC CONFIG] Database updated for User: {x_username} / Device: {jabobo_id}")
        
        # ── 如果用户配置了唤醒词文本，后台触发训练 + 部署 ──
        if wake_word_text_db:
            # 检查模型是否已存在
            model_file = _TRAIN_WORK_DIR / "trained_models" / wake_word_text_db / f"{wake_word_text_db}.tflite"
            model_exists = model_file.exists()
            
            if not model_exists:
                # 新模型：设为 training 状态，后台异步训练
                cursor.execute(
                    "UPDATE user_personas SET wake_word_model_status = %s WHERE jabobo_id = %s",
                    (1, jabobo_id),
                )
                db.connection.commit()
                asyncio.create_task(_run_wakeword_training(wake_word_text_db, jabobo_id, wake_word_raw_text))
            else:
                # 模型已存在：直接后台 deploy（不置 training 状态，DB 保留上次的 1）
                asyncio.create_task(_run_wakeword_training(wake_word_text_db, jabobo_id, wake_word_raw_text))
        
        return {"success": True, "message": f"设备 {jabobo_id} 数据同步成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔥 [SYNC CONFIG CRITICAL] User: {x_username} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail="配置同步失败，请联系管理员")
    finally:
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass


# 4. 查询唤醒词训练状态
@router.get("/user/wake-word-status")
async def get_wake_word_status(
    jabobo_id: str = Query(...),
    x_username: str = Header(...),
    authorization: str = Header(None),
):
    verify_user(x_username, authorization)

    # 先从 DB 读取最新 model_status
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT wake_word_text, wake_word_model_status FROM user_personas WHERE jabobo_id = %s",
            (jabobo_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="设备不存在")
        wake_text = (row.get("wake_word_text") or "").strip()
        db_status = int(row.get("wake_word_model_status") or 0)
    finally:
        cursor.close()
        db.close()

    # 检查后台任务状态
    task_info = _wake_word_tasks.get(f"{wake_text}@{jabobo_id}") if wake_text else None

    if task_info:
        return {
            "wake_word_text": wake_text,
            "model_status": db_status,
            "task_status": task_info["status"],
            "task_message": task_info["message"],
            "elapsed_seconds": task_info.get("elapsed_seconds"),
        }

    # 没有活跃任务，直接返回 DB 状态
    return {
        "wake_word_text": wake_text,
        "model_status": db_status,
        "task_status": "idle" if not wake_text else "done",
        "task_message": "",
    }
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import time
import asyncio
from asr_provider_funasr import ASRProvider 
from vad_provider import SileroVADProvider

app = FastAPI()

# 初始化
asr_engine = ASRProvider(
    config={
        "model_dir": "models/SenseVoiceSmall",
        "output_dir": "debug_audio" # 确保 config 里有这个，或者代码里有默认值
    }, 
    delete_audio_file=False  # <--- 补上这个参数
)
vad_detector = SileroVADProvider({"model_dir": "./models/snakers4_silero-vad"})

class SessionState:
    def __init__(self, session_id):
        self.session_id = session_id
        self.asr_audio_frames = []
        self.client_audio_buffer = bytearray()
        self.last_is_voice = False
        self.client_voice_window = []
        self.client_have_voice = False
        self.last_activity_time = time.time() * 1000
        self.client_voice_stop = False
        self.is_user_speaking = False

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    state = SessionState(session_id)
    print(f"✨ [Open] {session_id}")
    
    try:
        while True:
            try:
                # 接收前端发送的二进制 Opus 数据包
                message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                
                if "bytes" in message:
                    # 1. 解码 + VAD 判定
                    is_speaking, pcm_frame = vad_detector.is_vad(state, message["bytes"])
                    
                    # 2. 反馈前端状态
                    await websocket.send_text(json.dumps({"type": "status", "is_speaking": bool(is_speaking)}))

                    # 3. 收集解码后的 PCM
                    if is_speaking or state.is_user_speaking:
                        if is_speaking: state.is_user_speaking = True
                        state.asr_audio_frames.append(pcm_frame)

                    # 4. 触发断句
                    if state.client_voice_stop:
                        print(f"🎤 [End Detected] {len(state.asr_audio_frames)} frames")
                        
                        text, _ = await asr_engine.speech_to_text(state.asr_audio_frames, session_id)
                        
                        print(f"🏁 [Result] {text}")
                        await websocket.send_text(json.dumps({"type": "asr_result", "text": text}))
                        
                        # 重置
                        state.asr_audio_frames = []
                        state.client_voice_stop = False
                        state.is_user_speaking = False

            except asyncio.TimeoutError:
                if time.time() - (state.last_activity_time / 1000) > 60.0:
                    break
                continue
    except Exception as e:
        print(f"❌ [Error]: {e}")
    finally:
        print(f"🚫 [Close] {session_id}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007)
import time
import numpy as np
import torch
import opuslib_next

class SileroVADProvider():
    def __init__(self, config):
        # 1. 加载模型
        self.model, _ = torch.hub.load(
            repo_or_dir=config["model_dir"],
            source="local",
            model="silero_vad",
            force_reload=False,
        )
        self.model.eval()
        
        # 2. 前端 RATE 为 16000，这里必须严格对应
        self.decoder = opuslib_next.Decoder(16000, 1)

        self.vad_threshold = 0.35
        self.vad_threshold_low = 0.20
        self.silence_threshold_ms = 800
        self.frame_window_threshold = 3 

    def is_vad(self, conn, opus_packet):
        try:
            if not opus_packet: return False, b""

            # --- 关键修复：这里的 320 必须匹配前端 FastEncoder 的 FRAME_SIZE ---
            # 如果这里报 opus error，说明前端传过来的包不是标准的 Opus 压缩包
            pcm_frame = self.decoder.decode(opus_packet, 320) 
            
            conn.client_audio_buffer.extend(pcm_frame)

            # Silero VAD 在 16kHz 下，1024 字节（512采样点）是 32ms，这是标准块大小
            while len(conn.client_audio_buffer) >= 1024:
                chunk = conn.client_audio_buffer[:1024]
                conn.client_audio_buffer = conn.client_audio_buffer[1024:]

                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                with torch.no_grad():
                    speech_prob = self.model(torch.from_numpy(audio_float32), 16000).item()
                
                # 双阈值判定
                if speech_prob >= self.vad_threshold:
                    is_voice_frame = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice_frame = False
                else:
                    is_voice_frame = conn.last_is_voice
                
                conn.last_is_voice = is_voice_frame
                conn.client_voice_window.append(is_voice_frame)
                if len(conn.client_voice_window) > 10: conn.client_voice_window.pop(0)
                
                is_speaking_now = (conn.client_voice_window.count(True) >= self.frame_window_threshold)
                now_ms = time.time() * 1000

                if is_speaking_now:
                    conn.last_activity_time = now_ms
                    conn.client_have_voice = True
                    conn.client_voice_stop = False
                else:
                    if conn.client_have_voice:
                        if (now_ms - conn.last_activity_time) >= self.silence_threshold_ms:
                            conn.client_voice_stop = True
                            conn.client_have_voice = False 

            return conn.client_have_voice, pcm_frame
        except Exception as e:
            print(f"❌ [VAD解码错误]: {e}")
            return False, b""
import time
import os
import io
import sys
import psutil
import wave
import numpy as np
import re
import asyncio
import shutil
import logging
from typing import Optional, Tuple, List
from enum import Enum

# 根据你的要求，从本地 base 导入
try:
    from base import ASRProviderBase
except ImportError:
    from core.providers.asr.base import ASRProviderBase

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# 基础配置
TAG = __name__
MAX_RETRIES = 2
RETRY_DELAY = 1

class InterfaceType(Enum):
    STREAM = "STREAM"
    NON_STREAM = "NON_STREAM"
    LOCAL = "LOCAL"

# 捕获标准输出
class CaptureOutput:
    def __enter__(self):
        self._output = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._output

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self._original_stdout
        self.output = self._output.getvalue()
        self._output.close()
        if self.output:
            logging.info(f"[{TAG}] {self.output.strip()}")

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        
        # 内存检测
        min_mem_bytes = 2 * 1024 * 1024 * 1024
        total_mem = psutil.virtual_memory().total
        if total_mem < min_mem_bytes:
            logging.error(f"[{TAG}] 可用内存不足2G，当前仅有 {total_mem / (1024*1024):.2f} MB")
        
        self.interface_type = InterfaceType.LOCAL
        self.model_dir = config.get("model_dir")
        self.output_dir = config.get("output_dir", "debug_audio")
        self.delete_audio_file = delete_audio_file

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        with CaptureOutput():
            self.model = AutoModel(
                model=self.model_dir,
                vad_kwargs={"max_single_segment_time": 30000},
                disable_update=True,
                hub="hf",
            )

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="pcm"
    ) -> Tuple[Optional[str], Optional[str]]:
        """语音转文本主处理逻辑"""
        file_path = None
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # 1. 音频数据转换与合并
                if audio_format == "pcm":
                    combined_pcm_bytes = b"".join(opus_data)
                else:
                    # 确保你的 base 类中有此方法
                    pcm_frames = self.decode_opus(opus_data)
                    combined_pcm_bytes = b"".join(pcm_frames)

                if not combined_pcm_bytes:
                    return "", None

                # 2. 强制保存调试音频（识别前保存，防止报错后没文件）
                file_path = self.save_audio_to_file(combined_pcm_bytes, session_id)
                print(f"[音频保存] 音频保存成功：{file_path}")

                # 3. 【核心修复】音频数值预处理
                # 转换为 float32 归一化
                audio_int16 = np.frombuffer(combined_pcm_bytes, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                
                # A. 消除直流偏置（防止波形重心偏移导致的“幻听”韩文）
                audio_float32 = audio_float32 - np.mean(audio_float32)
                
                # B. 自动增益控制（如果声音太小，强行拉升到合理区间）
                max_amplitude = np.max(np.abs(audio_float32))
                if 0.001 < max_amplitude < 0.7:
                    gain = 0.7 / (max_amplitude + 1e-6)
                    audio_float32 = audio_float32 * gain

                # 4. 语音识别
                start_time = time.time()
                # 注意：这里直接传入处理好的 float32 数组效果更好
                result = self.model.generate(
                    input=audio_float32, 
                    cache={},
                    language="zh",  # 强制中文，封杀韩文/英文乱码
                    use_itn=True,
                    batch_size_s=60,
                )
                
                if not result:
                    return "", file_path

                # 5. 后处理与暴力清洗
                raw_text = result[0]["text"]
                text = rich_transcription_postprocess(raw_text)
                
                # 正则过滤：只保留中文、数字及常用标点，彻底解决“받는”等乱码显示
                text = "".join(re.findall(r'[\u4e00-\u9fa50-9，。？！、]', text))
                
                logging.info(f"[{TAG}] 识别耗时: {time.time() - start_time:.3f}s | 振幅: {max_amplitude:.4f} | 结果: {text}")

                return text, file_path

            except Exception as e:
                retry_count += 1
                logging.error(f"[{TAG}] 语音识别失败（重试 {retry_count}）: {e}")
                if retry_count >= MAX_RETRIES:
                    return "", file_path
                await asyncio.sleep(RETRY_DELAY)

            finally:
                # 6. 文件清理逻辑
                if self.delete_audio_file and file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as err:
                        logging.error(f"[{TAG}] 删除文件失败: {err}")

    def save_audio_to_file(self, pcm_data: bytes, session_id: str) -> str:
        """保存 PCM 为标准的 WAV 文件"""
        ts = int(time.time())
        filename = f"debug_{session_id}_{ts}.wav"
        full_path = os.path.join(self.output_dir, filename)
        try:
            with wave.open(full_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_data)
            return full_path
        except Exception as e:
            logging.error(f"[{TAG}] 保存WAV失败: {e}")
            return ""
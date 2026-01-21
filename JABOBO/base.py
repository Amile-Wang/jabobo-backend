import os
import wave
import uuid
import io
import logging
import opuslib_next
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List

# 基础日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ASRProviderBase(ABC):
    # 定义Opus解码的基础参数（固定配置，避免硬编码）
    OPUS_SAMPLE_RATE = 16000
    OPUS_CHANNELS = 1
    # Opus标准帧时长对应的样本数（16kHz下）
    OPUS_FRAME_SIZES = {
        20: 320,   # 20ms（最常用）
        40: 640,
        60: 960,
        80: 1280,
        100: 1600,
        120: 1920
    }

    def __init__(self, output_dir: str = "tmp"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """将PCM数据转换为WAV格式字节流（修复帧结构破坏问题）"""
        if not pcm_data:
            return b""
        
        # 修复：PCM数据长度必须是采样宽度的整数倍（16位=2字节），不足则补0而非截断
        sample_width = 2  # 16位PCM
        remainder = len(pcm_data) % sample_width
        if remainder != 0:
            # 补0而不是截断，避免破坏帧结构
            pcm_data += b"\x00" * (sample_width - remainder)
            logger.warning(f"PCM数据长度非{sample_width}字节倍数，已补0修正")
        
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(self.OPUS_CHANNELS)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(self.OPUS_SAMPLE_RATE)
                # 修复：使用writeframesraw避免wave库自动添加额外数据
                wav_file.writeframesraw(pcm_data)
            wav_buffer.seek(0)
            return wav_buffer.getvalue()
        except Exception as e:
            logger.error(f"WAV转换失败: {e}")
            return b""

    def save_audio_to_file(self, pcm_data_list: List[bytes], session_id: str) -> str:
        """PCM数据列表保存为本地WAV文件（同步修复）"""
        file_name = f"asr_{session_id}_{uuid.uuid4().hex[:8]}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        try:
            # 合并所有PCM数据并修正长度
            total_pcm = b"".join(pcm_data_list)
            sample_width = 2
            remainder = len(total_pcm) % sample_width
            if remainder != 0:
                total_pcm += b"\x00" * (sample_width - remainder)

            with wave.open(file_path, "wb") as wf:
                wf.setnchannels(self.OPUS_CHANNELS)
                wf.setsampwidth(sample_width)
                wf.setframerate(self.OPUS_SAMPLE_RATE)
                wf.writeframesraw(total_pcm)
            return file_path
        except Exception as e:
            logger.error(f"保存音频文件失败: {e}")
            return ""

    @staticmethod
    def decode_opus(opus_data: List[bytes], sample_rate: int = 16000, channels: int = 1) -> List[bytes]:
        """
        将Opus音频数据解码为PCM数据（修复样本数不匹配问题）
        :param opus_data: Opus数据包列表
        :param sample_rate: 目标采样率
        :param channels: 声道数
        :return: 解码后的PCM数据列表
        """
        try:
            decoder = opuslib_next.Decoder(sample_rate, channels)
            pcm_data = []
            # 尝试多种帧大小解码，适配不同Opus包
            frame_sizes = [320, 640, 960, 1280, 1920]
            
            for i, opus_packet in enumerate(opus_data):
                if not opus_packet:
                    continue
                # 遍历尝试不同帧大小，直到解码成功
                decoded = False
                for frame_size in frame_sizes:
                    try:
                        pcm_frame = decoder.decode(opus_packet, frame_size)
                        if pcm_frame:
                            pcm_data.append(pcm_frame)
                            decoded = True
                            break
                    except opuslib_next.OpusError as e:
                        continue
                    except Exception as e:
                        logger.warning(f"Opus包 {i} 帧大小{frame_size}解码失败: {e}")
                        continue
                if not decoded:
                    logger.error(f"Opus包 {i} 所有帧大小解码均失败，跳过该包")
            return pcm_data
        except Exception as e:
            logger.error(f"Opus解码器初始化失败: {e}")
            return []

    @abstractmethod
    async def speech_to_text(
        self, audio_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """子类必须实现的识别接口"""
        pass
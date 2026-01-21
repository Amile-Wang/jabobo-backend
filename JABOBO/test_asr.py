from funasr import AutoModel
import os
import soundfile as sf
import librosa
import numpy as np

def convert_audio_to_16k_mono(audio_path, temp_path="temp_16k_mono.wav"):
    """
    强制将音频转换为模型要求的 16kHz 单声道 WAV（适配 config.yaml 中的 fs:16000）
    :param audio_path: 原始音频路径
    :param temp_path: 转换后的临时音频路径
    :return: 转换后的音频路径
    """
    # 读取音频（自动兼容mp3/wav等格式）
    y, sr = librosa.load(audio_path, sr=None, mono=False)
    
    # 转单声道
    if len(y.shape) > 1:
        y = librosa.to_mono(y)
    
    # 转16kHz采样率
    if sr != 16000:
        y = librosa.resample(y, orig_sr=sr, target_sr=16000)
    
    # 保存为16bit WAV（模型最优输入格式）
    sf.write(temp_path, y, 16000, subtype='PCM_16')
    return temp_path

def clean_chinese_text(raw_text):
    """
    严格过滤文本，只保留纯中文+中文标点+数字+基础英文（适配分词器配置）
    """
    if not raw_text:
        return ""
    
    cleaned = []
    # 中文范围、中文标点、数字、基础英文、常用符号
    allowed_ranges = [
        ('\u4e00', '\u9fff'),    # 中文汉字
        ('\u3000', '\u303f'),    # 中文标点（全角）
        ('\uff00', '\uffef'),    # 全角符号
        ('0', '9'), ('a', 'z'), ('A', 'Z'),
        '，。！？：；""''（）【】《》、·…—·'  # 常用中文标点
    ]
    
    for char in raw_text:
        # 检查是否在允许范围内
        is_allowed = False
        for start, end in allowed_ranges[:-1]:
            if start <= char <= end:
                is_allowed = True
                break
        # 检查是否是常用标点
        if char in allowed_ranges[-1]:
            is_allowed = True
        
        if is_allowed:
            cleaned.append(char)
    
    # 合并并去除多余空格（适配 split_with_space: true）
    result = ''.join(cleaned).replace(" ", "").strip()
    return result

def sensevoice_small_final_recognition(audio_path):
    """
    最终版：适配模型配置 + 强制音频格式 + 严格文本清洗
    """
    # 1. 基础路径校验
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在：{audio_path}")
    
    local_model_path = "/var/local/jobobo-backend/JABOBO/models/SenseVoiceSmall"
    if not os.path.exists(local_model_path):
        raise FileNotFoundError(f"本地模型路径不存在：{local_model_path}")
    
    try:
        # 2. 强制转换音频为16kHz单声道（核心：对齐 config.yaml 的 fs:16000）
        temp_audio = convert_audio_to_16k_mono(audio_path)
        
        # 3. 加载模型（完全对齐配置文件）
        model = AutoModel(
            model=local_model_path,
            vad_kwargs={"max_single_segment_time": 30000},
            device="auto",
            disable_download=True,
            disable_update=True,
            trust_remote_code=True,
            # 强制关闭多语言识别（适配分词器配置）
            model_conf={"tokenizer_conf": {"split_with_space": True}}
        )
        
        # 4. 执行识别（严格限定中文）
        res = model.generate(
            input=temp_audio,
            use_itn=False,          # 关闭归一化（避免编码冲突）
            batch_size=1,
            language="zh",          # 强制中文
            merge_vad=True,         # 合并VAD结果
            disable_punctuation=False,
            # 禁用自动语言检测
            decoder_conf={"beam_size": 1, "ctc_weight": 0.5}
        )
        
        # 5. 解析并清洗结果
        raw_text = res[0]["text"] if (res and len(res) > 0 and "text" in res[0]) else ""
        final_text = clean_chinese_text(raw_text)
        
        # 6. 删除临时音频文件
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        
        return final_text if final_text else "识别失败：无有效中文内容"
    
    except Exception as e:
        # 清理临时文件
        if os.path.exists("temp_16k_mono.wav"):
            os.remove("temp_16k_mono.wav")
        return f"识别出错：{str(e)}"

# ------------------- 测试执行（替换为你的指定音频路径） -------------------
if __name__ == "__main__":
    # 你的指定音频文件路径（Docker路径下的zh.mp3）
    audio_file = r"/var/lib/docker/overlay2/045a3f769bc35c7dfdd734d6f3ba4705042560e0dee75f7eb12cca36d1246b2b/diff/opt/xiaozhi-esp32-server/models/SenseVoiceSmall/example/zh.mp3"
    
    try:
        print(f"正在识别音频：{audio_file}")
        result = sensevoice_small_final_recognition(audio_file)
        print("\n识别结果：")
        print("="*50)
        print(result)
        print("="*50)
    except FileNotFoundError as e:
        print(f"错误：{e}")
        print("请检查音频文件路径是否正确，或文件是否存在")
    except Exception as e:
        print(f"运行错误：{str(e)}")
        # 打印详细异常栈（方便排查）
        import traceback
        traceback.print_exc()
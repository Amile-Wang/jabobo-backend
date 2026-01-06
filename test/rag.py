import os
import json
import pickle
import io
import math
from typing import List, Dict, Any, Tuple
from datetime import datetime
from PyPDF2 import PdfReader

# ==================== 配置项（根据你的环境调整） ====================
# 本地存储目录
LOCAL_STORAGE_DIR = "./rag_vector_storage"
os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

# 豆包 Embedding 配置（需和你的 API 信息一致）
ARK_API_KEY = "129f510f-f857-4755-8324-dd5d8e29a635"  # 替换为你的实际 API Key
ARK_EMBED_MODEL = "doubao-embedding-text-240715"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 文本切分配置
DEFAULT_MAX_CHARS = 500  # 每个 Chunk 最大字符数
DEFAULT_OVERLAP = 100    # Chunk 重叠字符数

# ==================== 依赖的基础工具函数 ====================
def get_embedding(text: str) -> List[float]:
    """调用豆包 Embedding API 生成文本向量（核心量化逻辑）"""
    from openai import OpenAI

    if not ARK_API_KEY:
        raise RuntimeError("未配置 ARK_API_KEY，无法调用 Embedding 接口")

    client = OpenAI(
        base_url=ARK_BASE_URL,
        api_key=ARK_API_KEY or "EMPTY",
    )

    resp = client.embeddings.create(
        model=ARK_EMBED_MODEL,
        input=text,
    )
    return resp.data[0].embedding

def simple_chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    """简单按字符长度切分文本为 Chunk，带重叠"""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= n:
            break
        start = end - overlap
    return chunks

def extract_text_from_file(file_path: str) -> str:
    """从本地文件（TXT/PDF）提取文本"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在：{file_path}")
    
    filename = os.path.basename(file_path).lower()
    with open(file_path, "rb") as f:
        content_bytes = f.read()

    # 解析 TXT
    if filename.endswith(".txt"):
        for enc in ("utf-8", "gbk"):
            try:
                return content_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("无法识别 TXT 文件编码（仅支持 UTF-8/GBK）")
    
    # 解析 PDF
    elif filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content_bytes))
        texts = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
                texts.append(t)
            except Exception:
                continue
        return "\n".join(texts)
    
    else:
        raise ValueError(f"不支持的文件格式：{filename}，仅支持 TXT/PDF")

# ==================== 核心向量化处理方法 ====================
def process_text_to_vector(
    content: str = None,
    file_path: str = None,
    user_id: str = "default_user",
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    save_to_local: bool = True
) -> Dict[str, Any]:
    """
    通用向量化处理方法：支持直接传文本 / 传文件路径，生成向量并可选本地保存
    :param content: 直接传入的文本内容（与 file_path 二选一）
    :param file_path: 本地文件路径（TXT/PDF，与 content 二选一）
    :param user_id: 用户 ID，用于隔离不同用户的向量数据
    :param max_chars: 每个 Chunk 最大字符数
    :param overlap: Chunk 重叠字符数
    :param save_to_local: 是否将结果保存到本地
    :return: 包含 Chunk、向量、保存路径等信息的字典
    """
    # 1. 校验输入（二选一）
    if not content and not file_path:
        raise ValueError("必须传入 content（文本）或 file_path（文件路径）")
    if content and file_path:
        raise ValueError("content 和 file_path 只能传入一个")

    # 2. 获取原始文本
    raw_text = ""
    source_info = ""
    if file_path:
        raw_text = extract_text_from_file(file_path)
        source_info = f"file:{os.path.basename(file_path)}"
    else:
        raw_text = content
        source_info = "text:direct_input"

    # 3. 文本切分
    chunks = simple_chunk_text(raw_text, max_chars=max_chars, overlap=overlap)
    if not chunks:
        raise RuntimeError("文本切分后无有效 Chunk")

    # 4. 批量生成向量（量化核心）
    vector_list: List[Dict[str, Any]] = []
    failed_chunks = []
    for idx, chunk in enumerate(chunks):
        try:
            emb = get_embedding(chunk)
            vector_list.append({
                "chunk_id": f"{user_id}_{idx+1}",
                "text": chunk,
                "embedding": emb,
                "source": source_info,
                "chunk_index": idx + 1,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            failed_chunks.append({
                "chunk_index": idx + 1,
                "error": str(e)
            })
            print(f"[量化失败] 第 {idx+1} 个 Chunk 生成向量失败：{e}")

    # 5. 本地保存（可选）
    save_paths = {}
    if save_to_local:
        # 初始化用户存储目录
        user_dir = os.path.join(LOCAL_STORAGE_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)

        # 保存 Chunk 文本（JSON 格式，易查看）
        chunk_save_path = os.path.join(user_dir, f"chunks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(chunk_save_path, "w", encoding="utf-8") as f:
            json.dump({
                "user_id": user_id,
                "source": source_info,
                "chunks": chunks,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, ensure_ascii=False, indent=2)

        # 保存向量（Pickle 格式，高效存储浮点数组）
        vector_save_path = os.path.join(user_dir, f"vectors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl")
        with open(vector_save_path, "wb") as f:
            pickle.dump(vector_list, f)

        save_paths = {
            "chunks": chunk_save_path,
            "vectors": vector_save_path
        }

    # 6. 返回处理结果
    return {
        "status": "success" if vector_list else "failed",
        "user_id": user_id,
        "source": source_info,
        "raw_text_length": len(raw_text),
        "total_chunks": len(chunks),
        "success_vectors": len(vector_list),
        "failed_chunks": failed_chunks,
        "chunks": chunks,
        "vectors": vector_list,
        "save_paths": save_paths if save_to_local else None,
        "message": f"处理完成：成功生成 {len(vector_list)} 个向量，失败 {len(failed_chunks)} 个 Chunk"
    }

# 示例 1：处理本地文件（PDF/TXT）
if __name__ == "__main__":
    # 处理本地 PDF 文件
    result1 = process_text_to_vector(
        file_path=r"C:\Users\Administrator\Desktop\随笔2.txt",  # 替换为你的文件路径
        user_id="jb1",
        save_to_local=True
    )
    print(f"文件处理结果：{result1['message']}")
    print(f"向量保存路径：{result1['save_paths']['vectors']}")

    # 示例 2：直接处理文本内容
    result2 = process_text_to_vector(
        content="捷波朗（Jabra）是全球领先的音频设备制造商，专注于蓝牙耳机、会议系统等产品。",
        user_id="jb1",
        save_to_local=True
    )
    print(f"文本处理结果：{result2['message']}")
    print(f"第一个向量长度：{len(result2['vectors'][0]['embedding'])}")
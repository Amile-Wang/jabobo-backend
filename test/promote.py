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

# 待处理的目标文件夹（修改为你要批量处理的文件夹路径）
TARGET_FOLDER = r"C:\Users\Administrator\Desktop\新建文件夹"  # 核心修改：批量文件夹路径

# 豆包 Embedding 配置（需和你的 API 信息一致）
ARK_API_KEY = "129f510f-f857-4755-8324-dd5d8e29a635"  # 替换为你的实际 API Key
ARK_EMBED_MODEL = "doubao-embedding-text-240715"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 文本切分配置
DEFAULT_MAX_CHARS = 500  # 每个 Chunk 最大字符数
DEFAULT_OVERLAP = 100    # Chunk 重叠字符数

# 支持的文件格式
SUPPORTED_FORMATS = [".txt", ".pdf"]

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

# ==================== 核心向量化处理方法（修改：PKL按原文件名保存） ====================
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
    original_file_name = ""  # 新增：记录原文件名
    if file_path:
        raw_text = extract_text_from_file(file_path)
        original_file_name = os.path.splitext(os.path.basename(file_path))[0]  # 获取无后缀的原文件名
        source_info = f"file:{os.path.basename(file_path)}"
    else:
        raw_text = content
        source_info = "text:direct_input"
        original_file_name = "direct_input"

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

    # 5. 本地保存（修改：PKL按原文件名保存）
    save_paths = {}
    if save_to_local:
        # 初始化用户存储目录
        user_dir = os.path.join(LOCAL_STORAGE_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)

        # 保存 Chunk 文本（JSON 格式，易查看）- 保留时间戳避免重复
        chunk_save_path = os.path.join(user_dir, f"chunks_{original_file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(chunk_save_path, "w", encoding="utf-8") as f:
            json.dump({
                "user_id": user_id,
                "source": source_info,
                "original_file_name": original_file_name,
                "chunks": chunks,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, ensure_ascii=False, indent=2)

        # 保存向量（Pickle 格式，核心修改：使用原文件名保存，无时间戳）
        vector_save_path = os.path.join(user_dir, f"vectors_{original_file_name}.pkl")
        # 处理文件重复：如果文件已存在，添加数字后缀
        counter = 1
        while os.path.exists(vector_save_path):
            vector_save_path = os.path.join(user_dir, f"vectors_{original_file_name}_{counter}.pkl")
            counter += 1
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
        "original_file_name": original_file_name,  # 新增：返回原文件名
        "raw_text_length": len(raw_text),
        "total_chunks": len(chunks),
        "success_vectors": len(vector_list),
        "failed_chunks": failed_chunks,
        "chunks": chunks,
        "vectors": vector_list,
        "save_paths": save_paths if save_to_local else None,
        "message": f"处理完成：成功生成 {len(vector_list)} 个向量，失败 {len(failed_chunks)} 个 Chunk"
    }

# ==================== 新增：批量处理文件夹内所有文件 ====================
def batch_process_folder(
    folder_path: str,
    user_id: str = "default_user",
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    save_to_local: bool = True
) -> Dict[str, Any]:
    """
    批量处理指定文件夹下的所有 TXT/PDF 文件
    :param folder_path: 目标文件夹路径
    :param user_id: 用户 ID
    :param max_chars: 每个 Chunk 最大字符数
    :param overlap: Chunk 重叠字符数
    :param save_to_local: 是否保存到本地
    :return: 批量处理汇总结果
    """
    # 1. 校验文件夹是否存在
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"目标文件夹不存在：{folder_path}")
    
    # 2. 扫描文件夹内所有支持的文件
    file_list = []
    for file_name in os.listdir(folder_path):
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext in SUPPORTED_FORMATS:
            file_list.append(os.path.join(folder_path, file_name))
    
    if not file_list:
        raise RuntimeError(f"文件夹 {folder_path} 下未找到支持的文件（仅支持 {SUPPORTED_FORMATS}）")
    
    # 3. 逐个处理文件
    batch_results = {
        "total_files": len(file_list),
        "success_files": 0,
        "failed_files": 0,
        "file_results": [],
        "summary": ""
    }

    print(f"\n========== 开始批量处理文件夹：{folder_path} ==========")
    print(f"共找到 {len(file_list)} 个待处理文件：")
    for i, file_path in enumerate(file_list):
        print(f"   [{i+1}] {os.path.basename(file_path)}")
    print("="*50)

    for idx, file_path in enumerate(file_list, 1):
        file_name = os.path.basename(file_path)
        print(f"\n【{idx}/{len(file_list)}】处理文件：{file_name}")
        
        try:
            # 调用原有方法处理单个文件
            file_result = process_text_to_vector(
                file_path=file_path,
                user_id=user_id,
                max_chars=max_chars,
                overlap=overlap,
                save_to_local=save_to_local
            )
            
            batch_results["file_results"].append({
                "file_name": file_name,
                "file_path": file_path,
                "original_file_name": file_result["original_file_name"],  # 新增：记录原文件名
                "result": file_result
            })
            
            if file_result["status"] == "success":
                batch_results["success_files"] += 1
                print(f"✅ 处理成功：{file_name} | 生成 {file_result['success_vectors']} 个向量")
                if save_to_local:
                    print(f"   向量保存路径：{file_result['save_paths']['vectors']}")
            else:
                batch_results["failed_files"] += 1
                print(f"❌ 处理失败：{file_name}")
        
        except Exception as e:
            batch_results["failed_files"] += 1
            error_msg = f"处理文件 {file_name} 时发生异常：{str(e)[:100]}"
            batch_results["file_results"].append({
                "file_name": file_name,
                "file_path": file_path,
                "error": error_msg
            })
            print(f"❌ 处理异常：{file_name} | {error_msg}")

    # 4. 生成汇总信息
    batch_results["summary"] = (
        f"批量处理完成 | 总文件数：{batch_results['total_files']} "
        f"| 成功：{batch_results['success_files']} "
        f"| 失败：{batch_results['failed_files']}"
    )
    
    print("\n" + "="*50)
    print(batch_results["summary"])
    print("="*50)

    return batch_results

# ==================== 运行批量处理 ====================
if __name__ == "__main__":
    # 核心修改：批量处理指定文件夹下的所有文件
    batch_result = batch_process_folder(
        folder_path=TARGET_FOLDER,  # 待处理文件夹路径（已在配置项定义）
        user_id="jb1",               # 用户ID
        save_to_local=True           # 保存向量到本地
    )

    # 可选：保存批量处理结果到JSON文件
    summary_save_path = os.path.join(LOCAL_STORAGE_DIR, "batch_process_summary.json")
    with open(summary_save_path, "w", encoding="utf-8") as f:
        json.dump(batch_result, f, ensure_ascii=False, indent=2)
    print(f"\n批量处理汇总结果已保存到：{summary_save_path}")
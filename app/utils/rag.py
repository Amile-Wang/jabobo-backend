import os
import pickle
import math
import time
from datetime import datetime
from typing import List, Dict, Any, Generator

# 导入 dotenv 库（需安装：pip install python-dotenv）
from dotenv import load_dotenv

# 第三方依赖：pip install openai
from openai import OpenAI

# 导入 loguru（需安装：pip install loguru）
from loguru import logger

# ========== 加载 .env 配置文件 ==========
load_dotenv(override=True)

# ============== 从 .env 读取固定配置（带默认值） ==============
AZURE_OAI_EMBED_API_KEY = os.getenv("AZURE_OAI_EMBED_API_KEY", "")
AZURE_OAI_EMBED_BASE_URL = os.getenv("AZURE_OAI_EMBED_BASE_URL", "")
AZURE_OAI_EMBED_MODEL = os.getenv("AZURE_OAI_EMBED_MODEL", "text-embedding-3-small")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

TOP_K = int(os.getenv("TOP_K", "5"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))

# ============== 固定配置校验 ==============
def validate_fixed_config():
    """校验.env中的固定配置，缺失则报错"""
    required_fixed_configs = {
        "API 核心配置": [
            ("AZURE_OAI_EMBED_API_KEY", AZURE_OAI_EMBED_API_KEY),
            ("AZURE_OAI_EMBED_BASE_URL", AZURE_OAI_EMBED_BASE_URL),
            ("AZURE_OAI_EMBED_MODEL", AZURE_OAI_EMBED_MODEL)
        ],
        "文本切分配置": [
            ("CHUNK_MAX_CHARS", CHUNK_MAX_CHARS),
            ("CHUNK_OVERLAP", CHUNK_OVERLAP)
        ],
        "检索配置": [
            ("TOP_K", TOP_K),
            ("SIMILARITY_THRESHOLD", SIMILARITY_THRESHOLD)
        ],
        "分批处理配置": [
            ("BATCH_SIZE", BATCH_SIZE)
        ]
    }

    missing_configs = []
    for config_type, config_items in required_fixed_configs.items():
        for name, value in config_items:
            if value is None or value == "":
                missing_configs.append(f"{config_type} -> {name}")

    if missing_configs:
        err_msg = "❌ .env 文件中缺失以下固定配置项：\n" + "\n".join([f"  - {item}" for item in missing_configs])
        logger.critical(err_msg)
        raise ValueError(err_msg)

    logger.success("✅ 固定配置校验通过")

# ============== 初始化 OpenAI 客户端（Azure OpenAI v1 endpoint） ==============
client = OpenAI(
    base_url=AZURE_OAI_EMBED_BASE_URL,
    api_key=AZURE_OAI_EMBED_API_KEY,
)

# ============== 工具函数 ==============
def batch_generator(lst: List[Any], batch_size: int) -> Generator[List[Any], None, None]:
    """分批生成器"""
    for i in range(0, len(lst), batch_size):
        yield lst[i:i + batch_size]

def generate_vector_from_txt_folder(txt_folder: str, vector_save_path: str):
    # 校验传入的路径参数
    if not txt_folder or not os.path.exists(txt_folder):
        logger.error(f"❌ 无效的TXT文件夹路径：{txt_folder}")
        raise FileNotFoundError(f"❌ 无效的TXT文件夹路径：{txt_folder}")
    if not vector_save_path:
        logger.error("❌ 向量文件保存路径不能为空")
        raise ValueError("❌ 向量文件保存路径不能为空")

    # 筛选txt文件
    txt_files = [f for f in os.listdir(txt_folder) if f.lower().endswith(".txt")]
    if not txt_files:
        logger.warning(f"❌ TXT文件夹中无.txt文件：{txt_folder}")
        raise ValueError(f"❌ TXT文件夹中无.txt文件：{txt_folder}")
    
    logger.info(f"📁 找到 {len(txt_files)} 个txt文件：{txt_files}")

    # 读取并切分chunk
    all_chunks = []
    for txt_file in txt_files:
        txt_path = os.path.join(txt_folder, txt_file)
        logger.info(f"📖 处理文件：{txt_path}")
        
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                raw_text = "".join([line.strip() + "\n" for line in f]).strip()
            if not raw_text:
                logger.warning(f"⚠️ {txt_file} 内容为空，跳过")
                continue
        except Exception:
            logger.exception(f"❌ 读取 {txt_file} 失败")
            continue
        
        # 切分chunk（使用.env中的固定配置）
        chunks = []
        start = 0
        text_len = len(raw_text)
        while start < text_len:
            end = min(start + CHUNK_MAX_CHARS, text_len)
            chunk_text = raw_text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "source": f"{txt_file}_chunk_{len(chunks)+1}"
                })
            if end >= text_len:
                break
            start = end - CHUNK_OVERLAP
        
        logger.debug(f"✂️ {txt_file} 切分完成，生成 {len(chunks)} 个chunk")
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.critical("❌ 所有txt文件处理后无有效chunk")
        raise RuntimeError("❌ 所有txt文件处理后无有效chunk")
    
    logger.info(f"📊 共生成 {len(all_chunks)} 个有效chunk")

    # 分批生成向量
    final_vector_data = []
    batch_num = 0
    total_batches = math.ceil(len(all_chunks) / BATCH_SIZE)
    
    for batch_chunks in batch_generator(all_chunks, BATCH_SIZE):
        batch_num += 1
        logger.info(f"🚀 处理第 {batch_num}/{total_batches} 批chunk（{len(batch_chunks)} 个）")
        
        batch_texts = [chunk["text"] for chunk in batch_chunks]
        try:
            start_time = time.time()
            resp = client.embeddings.create(
                model=AZURE_OAI_EMBED_MODEL,
                input=batch_texts,
                timeout=60
            )
            cost = round(time.time() - start_time, 2)
            
            for idx, emb in enumerate(resp.data):
                final_vector_data.append({
                    "embedding": emb.embedding,
                    "text": batch_chunks[idx]["text"],
                    "source": batch_chunks[idx]["source"]
                })
            logger.success(f"✅ 第 {batch_num} 批生成完成，耗时 {cost} 秒")
        
        except Exception:
            logger.exception(f"❌ 第 {batch_num} 批生成失败")
            raise

    # 保存向量文件
    logger.info(f"💾 保存 {len(final_vector_data)} 个向量到：{vector_save_path}")
    with open(vector_save_path, 'wb') as f:
        pickle.dump(final_vector_data, f)
    logger.success("✅ 向量文件保存完成")

def build_rag_prompt_from_vector_file(query: str, vector_file_path: str):
    """
    构建RAG提示词（动态传参，无默认值）
    """
    # 校验传入参数
    if not query:
        logger.error("❌ 用户问题不能为空")
        raise ValueError("❌ 用户问题不能为空")
    if not vector_file_path or not os.path.exists(vector_file_path):
        logger.error(f"❌ 无效的向量文件路径：{vector_file_path}")
        raise FileNotFoundError(f"❌ 无效的向量文件路径：{vector_file_path}")

    # 加载向量文件
    logger.info(f"📥 加载向量文件：{vector_file_path}")
    try:
        with open(vector_file_path, 'rb') as f:
            vector_data = pickle.load(f)
    except Exception:
        logger.exception("❌ 加载向量文件失败")
        raise
    
    logger.info(f"✅ 加载 {len(vector_data)} 个向量数据")

    # 生成问题向量
    logger.info(f"🔍 生成问题向量：{query}")
    try:
        q_resp = client.embeddings.create(
            model=AZURE_OAI_EMBED_MODEL,
            input=query,
            timeout=30
        )
        q_emb = q_resp.data[0].embedding
    except Exception:
        logger.exception("❌ 生成问题向量失败")
        raise

    # 计算相似度
    logger.info(f"🧮 计算 {len(vector_data)} 个chunk相似度...")
    scored_chunks = []
    for item in vector_data:
        emb = item["embedding"]
        if not emb or len(emb) != len(q_emb):
            continue
        
        dot = sum(x * y for x, y in zip(q_emb, emb))
        na = math.sqrt(sum(x * x for x in q_emb))
        nb = math.sqrt(sum(y * y for y in emb))
        sim = dot / (na * nb) if na * nb != 0 else 0.0
        
        scored_chunks.append({
            "score": sim,
            "text": item["text"],
            "source": item["source"]
        })

    # 筛选相似片段
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    filtered_chunks = [c for c in scored_chunks[:TOP_K] if c["score"] >= SIMILARITY_THRESHOLD]
    
    if filtered_chunks:
        logger.success(f"🎯 筛选出 {len(filtered_chunks)} 个相似片段（最高得分：{filtered_chunks[0]['score']:.3f}）")
    else:
        logger.warning(f"🎯 无符合阈值 {SIMILARITY_THRESHOLD} 的相似片段")

    # 构建提示词
    ref_text = "### 参考文献\n未找到与问题相关的内容（相似度 < 0.7）。" if not filtered_chunks else "\n\n".join([
        "### 参考文献"] + [
            f"{i}. 来源：{c['source']}\n相似度：{c['score']:.3f}\n内容：{c['text']}"
            for i, c in enumerate(filtered_chunks, 1)
        ])
    
    system_prompt = (
        "你还集成了知识库功能，请你在用户的问题与知识库召回内容相关时参考召回的内容回答用户的问题\n"
        "1. 优先基于下方「参考文献」内容作答，未找到与问题相关的内容时，使用外部知识回答；\n"
        "2. 当有多个文件都可以回答用户问题时，优先参考相似度最高的文件内容作答。并提示用户知识库中还有其他文档对用户的问题有所提及，询问用户是否需要基于其他文档的回答；\n"
        "3. 当用户问题和参考文档不匹配时，忽略参考文献直接回答；\n"
    )

    user_prompt = (
        f"### 用户问题\n{query}\n\n"
        f"参考文献{ref_text}\n\n"
        
    )

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "full_prompt": full_prompt,
        "retrieved_chunks": filtered_chunks,
        "total_chunk_num": len(vector_data)
    }

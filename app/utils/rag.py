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

# ========== 加载 .env 配置文件 ==========
load_dotenv(override=True)

# ============== 从 .env 读取固定配置（无默认值） ==============
# 豆包 API 核心配置
ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_EMBED_MODEL = os.getenv("ARK_EMBED_MODEL")
ARK_BASE_URL = os.getenv("ARK_BASE_URL")

# 文本切分配置
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP"))

# 检索配置
TOP_K = int(os.getenv("TOP_K"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD"))

# 分批处理配置
BATCH_SIZE = int(os.getenv("BATCH_SIZE"))

# ============== 固定配置校验（无默认，强制校验） ==============
def validate_fixed_config():
    """校验.env中的固定配置，缺失则报错"""
    required_fixed_configs = {
        "API 核心配置": [
            ("ARK_API_KEY", ARK_API_KEY),
            ("ARK_EMBED_MODEL", ARK_EMBED_MODEL),
            ("ARK_BASE_URL", ARK_BASE_URL)
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
        raise ValueError(
            "❌ .env 文件中缺失以下固定配置项：\n" +
            "\n".join([f"  - {item}" for item in missing_configs]) +
            "\n请补充完整 .env 文件后重新运行"
        )
    print_log("✅ 固定配置校验通过")

# ============== 初始化 OpenAI 客户端 ==============
client = OpenAI(
    base_url=ARK_BASE_URL,
    api_key=ARK_API_KEY,
)

# ============== 工具函数 ==============
def print_log(msg: str):
    """带时间戳的日志打印"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def batch_generator(lst: List[Any], batch_size: int) -> Generator[List[Any], None, None]:
    """分批生成器"""
    for i in range(0, len(lst), batch_size):
        yield lst[i:i + batch_size]

# ============== 方法1：生成向量文件（动态传路径参数，无默认） ==============
def generate_vector_from_txt_folder(txt_folder: str, vector_save_path: str):
    """
    生成txt向量文件（动态传参，无默认值）
    :param txt_folder: TXT文件夹绝对路径（必须传）
    :param vector_save_path: 向量文件保存路径（必须传）
    """
    # 校验传入的路径参数
    if not txt_folder or not os.path.exists(txt_folder):
        raise FileNotFoundError(f"❌ 无效的TXT文件夹路径：{txt_folder}")
    if not vector_save_path:
        raise ValueError("❌ 向量文件保存路径不能为空")

    # 筛选txt文件
    txt_files = [f for f in os.listdir(txt_folder) if f.lower().endswith(".txt")]
    if not txt_files:
        raise ValueError(f"❌ TXT文件夹中无.txt文件：{txt_folder}")
    print_log(f"📁 找到 {len(txt_files)} 个txt文件：{txt_files}")

    # 读取并切分chunk
    all_chunks = []
    for txt_file in txt_files:
        txt_path = os.path.join(txt_folder, txt_file)
        print_log(f"📖 处理文件：{txt_path}")
        
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                raw_text = "".join([line.strip() + "\n" for line in f]).strip()
            if not raw_text:
                print_log(f"⚠️ {txt_file} 内容为空，跳过")
                continue
        except Exception as e:
            print_log(f"❌ 读取 {txt_file} 失败：{str(e)[:50]}")
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
        
        print_log(f"✂️ {txt_file} 切分完成，生成 {len(chunks)} 个chunk")
        all_chunks.extend(chunks)

    if not all_chunks:
        raise RuntimeError("❌ 所有txt文件处理后无有效chunk")
    print_log(f"📊 共生成 {len(all_chunks)} 个有效chunk")

    # 分批生成向量
    final_vector_data = []
    batch_num = 0
    total_batches = math.ceil(len(all_chunks) / BATCH_SIZE)
    
    for batch_chunks in batch_generator(all_chunks, BATCH_SIZE):
        batch_num += 1
        print_log(f"🚀 处理第 {batch_num}/{total_batches} 批chunk（{len(batch_chunks)} 个）")
        
        batch_texts = [chunk["text"] for chunk in batch_chunks]
        try:
            start_time = time.time()
            resp = client.embeddings.create(
                model=ARK_EMBED_MODEL,
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
            print_log(f"✅ 第 {batch_num} 批生成完成，耗时 {cost} 秒")
        
        except Exception as e:
            raise RuntimeError(f"❌ 第 {batch_num} 批生成失败：{str(e)[:100]}")

    # 保存向量文件
    print_log(f"💾 保存 {len(final_vector_data)} 个向量到：{vector_save_path}")
    with open(vector_save_path, 'wb') as f:
        pickle.dump(final_vector_data, f)
    print_log(f"✅ 向量文件保存完成")

# ============== 方法2：构建提示词（动态传路径+问题参数，无默认） ==============
import os
import math
import pickle
# 请确保导入所需的依赖（如client/ARK_EMBED_MODEL/TOP_K/SIMILARITY_THRESHOLD/print_log）

def build_rag_prompt_from_vector_file(query: str, vector_file_path: str):
    """
    构建RAG提示词（简化返回：仅保留用户提示词 + 得分最高的参考文献）
    :param query: 用户问题（必须传）
    :param vector_file_path: 向量文件路径（必须传）
    :return: 简化的提示词字典
    """
    # 校验传入参数
    if not query:
        raise ValueError("❌ 用户问题不能为空")
    if not vector_file_path or not os.path.exists(vector_file_path):
        raise FileNotFoundError(f"❌ 无效的向量文件路径：{vector_file_path}")

    # 加载向量文件
    print_log(f"📥 加载向量文件：{vector_file_path}")
    try:
        with open(vector_file_path, 'rb') as f:
            vector_data = pickle.load(f)
    except Exception as e:
        raise RuntimeError(f"❌ 加载向量文件失败：{str(e)[:50]}")
    print_log(f"✅ 加载 {len(vector_data)} 个向量数据")

    # 生成问题向量
    print_log(f"🔍 生成问题向量：{query}")
    try:
        q_resp = client.embeddings.create(
            model=ARK_EMBED_MODEL,
            input=query,
            timeout=30
        )
        q_emb = q_resp.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"❌ 生成问题向量失败：{str(e)[:100]}")

    # 计算相似度（仅保留核心逻辑）
    print_log(f"🧮 计算 {len(vector_data)} 个chunk相似度...")
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

    # 筛选相似度最高的1条（核心修改：只取TOP1）
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    top1_chunk = None
    if scored_chunks and scored_chunks[0]["score"] >= SIMILARITY_THRESHOLD:
        top1_chunk = scored_chunks[0]  # 仅保留得分最高的1条
    print_log(f"🎯 筛选出最高相似度片段（得分：{top1_chunk['score']:.3f}" if top1_chunk else "🎯 无符合阈值的相似片段")

    # 构建简化的用户提示词
    ref_text = "未找到与问题相关的内容。" if not top1_chunk else f"""
来源：{top1_chunk['source']}
相似度：{top1_chunk['score']:.3f}
内容：{top1_chunk['text']}
    """.strip()
    
    user_prompt = (
        f"用户问题：{query}\n\n"
        f"参考文献：{ref_text}\n\n"
        "仅基于上述参考文献回答问题，语言简洁，标注来源信息，无相关内容则说明「无相关参考文献」。"
    )

    # 简化返回结果（仅保留2个核心字段）
    return {
        "user_prompt": user_prompt,       # 最终的用户提示词
        "top_reference": top1_chunk       # 得分最高的参考文献（None表示无）
    }
    """
    构建RAG提示词（动态传参，无默认值）
    :param query: 用户问题（必须传）
    :param vector_file_path: 向量文件路径（必须传）
    :return: 提示词字典
    """
    # 校验传入参数
    if not query:
        raise ValueError("❌ 用户问题不能为空")
    if not vector_file_path or not os.path.exists(vector_file_path):
        raise FileNotFoundError(f"❌ 无效的向量文件路径：{vector_file_path}")

    # 加载向量文件
    print_log(f"📥 加载向量文件：{vector_file_path}")
    try:
        with open(vector_file_path, 'rb') as f:
            vector_data = pickle.load(f)
    except Exception as e:
        raise RuntimeError(f"❌ 加载向量文件失败：{str(e)[:50]}")
    print_log(f"✅ 加载 {len(vector_data)} 个向量数据")

    # 生成问题向量
    print_log(f"🔍 生成问题向量：{query}")
    try:
        q_resp = client.embeddings.create(
            model=ARK_EMBED_MODEL,
            input=query,
            timeout=30
        )
        q_emb = q_resp.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"❌ 生成问题向量失败：{str(e)[:100]}")

    # 计算相似度
    print_log(f"🧮 计算 {len(vector_data)} 个chunk相似度...")
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

    # 筛选相似片段（使用.env中的固定配置）
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    filtered_chunks = [c for c in scored_chunks[:TOP_K] if c["score"] >= SIMILARITY_THRESHOLD]
    print_log(f"🎯 筛选出 {len(filtered_chunks)} 个相似片段（阈值 {SIMILARITY_THRESHOLD}）")

    # 构建提示词
    ref_text = "### 参考文献\n未找到与问题相关的内容（相似度 < 0.7）。" if not filtered_chunks else "\n\n".join([
        "### 参考文献"] + [
            f"{i}. 来源：{c['source']}\n相似度：{c['score']:.3f}\n内容：{c['text']}"
            for i, c in enumerate(filtered_chunks, 1)
        ])
    
    system_prompt = (
        "你是专业的知识库问答助手，严格按照以下要求回答问题：\n"
        "1. 仅基于下方「参考文献」内容作答，禁止使用外部知识；\n"
        "2. 回答时必须标注引用的参考文献序号（如 [1]）；\n"
        "3. 若参考文献无相关内容，直接说明「无相关参考文献」，禁止编造；\n"
        "4. 回答使用简体中文，条理清晰，分点说明（如有需要）。"
    )

    user_prompt = (
        f"### 用户问题\n{query}\n\n"
        f"{ref_text}\n\n"
        "### 回答要求\n"
        "1. 语言简洁，逻辑清晰；\n"
        "2. 标注引用来源序号，内容冲突时说明冲突点；\n"
        "3. 仅基于参考文献作答，不添加额外信息。"
    )

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "full_prompt": full_prompt,
        "retrieved_chunks": filtered_chunks,
        "total_chunk_num": len(vector_data)
    }

# # ============== 主执行示例（动态传参，无硬编码路径/问题） ==============
# if __name__ == "__main__":
#     try:
#         # 第一步：校验.env中的固定配置
#         validate_fixed_config()
        
#         # 第二步：动态传入参数（根据实际场景修改）
#         TXT_FOLDER = r"C:\Users\Administrator\xwechat_files\hhkandmogu_cf73\msg\file\2026-01\rag_jiebaobao_update\rag_"
#         VECTOR_FILE = "txt_vector_cache.pkl"
#         USER_QUESTION = "宁可是谁？"
        
#         # 第三步：生成向量文件（传路径参数）
#         print_log("\n===== 开始生成向量文件 =====")
#         generate_vector_from_txt_folder(txt_folder=TXT_FOLDER, vector_save_path=VECTOR_FILE)
        
#         # 第四步：生成提示词（传问题+向量文件路径）
#         print_log("\n===== 开始生成提示词 =====")
#         result = build_rag_prompt_from_vector_file(query=USER_QUESTION, vector_file_path=VECTOR_FILE)
        
#         # 打印结果
#         print("\n" + "="*100)
#         print("✅ 生成的RAG提示词：")
#         print("="*100)
#         print("\n【System Prompt】")
#         print(result["system_prompt"])
#         print("\n【User Prompt】")
#         print(result["user_prompt"])

#         # 打印相似片段
#         if result["retrieved_chunks"]:
#             print("\n" + "-"*80)
#             print("📌 相似片段：")
#             print("-"*80)
#             for i, chunk in enumerate(result["retrieved_chunks"], 1):
#                 print(f"\n{i}. 来源：{chunk['source']} | 相似度：{chunk['score']:.3f}")
#                 print(f"   内容：{chunk['text']}")

#     except Exception as e:
#         print_log(f"\n❌ 执行失败：{str(e)}")
# ============== 批量遍历PKL目录 + 测速验证（兼容列表/字典格式） ==============
import pickle
import time
import os
import math
from typing import List, Dict, Any, Tuple

# 定义必要的全局变量
corpora: Dict[str, List[str]] = {}
vectors: Dict[str, List[Dict[str, Any]]] = {}

# 核心工具函数
def cosine_similarity(a: List[float], b: List[float]) -> float:
    """简单余弦相似度"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def get_user_name(user_id: str) -> str:
    """根据user_id返回用户名"""
    if user_id == "jb2":
        return "捷宝宝2"
    return "捷宝宝1"

def retrieve_top_k(user_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """检索相似片段"""
    vecs = vectors.get(user_id, [])
    if not vecs:
        return []

    # 模拟query的embedding（避免调用API）
    q_emb = [0.1] * 1536

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in vecs:
        sim = cosine_similarity(q_emb, item["embedding"])
        scored.append((sim, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    return [
        {
            "score": s,
            "text": it["text"],
            "source": it["source"],
        }
        for (s, it) in top
    ]

def batch_test_all_pkl_in_dir(
    test_dir: str = "./rag_vector_data",
    test_query: str = "Jabra产品的核心卖点是什么？",
    top_k: int = 5
):
    """
    批量遍历PKL文件（兼容列表/字典格式）
    """
    print("="*70)
    print(f"📁 开始批量遍历PKL目录：{test_dir}")
    print(f"🔍 测试问题：{test_query}")
    print("="*70)

    # 第一步：扫描PKL文件
    pkl_files = []
    if not os.path.exists(test_dir):
        print(f"❌ 错误：目录 {test_dir} 不存在！")
        return None
    
    for file_name in os.listdir(test_dir):
        if file_name.lower().endswith(".pkl"):
            pkl_files.append(os.path.join(test_dir, file_name))
    
    if not pkl_files:
        print(f"❌ 目录 {test_dir} 下未找到任何.pkl文件！")
        return None
    
    print(f"✅ 共找到 {len(pkl_files)} 个PKL文件：")
    for i, pkl_path in enumerate(pkl_files):
        print(f"   [{i+1}] {os.path.basename(pkl_path)}")
    print("="*70)

    # 第二步：逐个处理PKL文件（核心修复：兼容列表/字典）
    batch_results = []

    for idx, pkl_path in enumerate(pkl_files, 1):
        file_name = os.path.basename(pkl_path)
        user_id = f"user_{idx}"  # 通用user_id，适配任意文件名
        print(f"\n【{idx}/{len(pkl_files)}】处理文件：{file_name}")
        
        # 清空内存
        corpora.pop(user_id, None)
        vectors.pop(user_id, None)
        
        # 1. 读取PKL并适配格式（核心修复）
        start_load = time.time()
        try:
            with open(pkl_path, "rb") as f:
                pkl_data = pickle.load(f)
            
            # 适配两种常见格式：
            # 格式1：字典（{"corpus": [...], "vectors": [...]}）
            if isinstance(pkl_data, dict):
                corpus = pkl_data.get("corpus", [])
                vecs = pkl_data.get("vectors", [])
            # 格式2：列表（直接存储vectors，corpus从vectors中提取）
            elif isinstance(pkl_data, list):
                vecs = pkl_data
                # 从vectors中提取corpus文本
                corpus = [item.get("text", "") for item in vecs if isinstance(item, dict)]
            else:
                raise ValueError(f"PKL格式不支持：{type(pkl_data)}")
            
            load_cost = time.time() - start_load
            chunk_count = len(corpus)
            vec_count = len(vecs)
            
            # 验证vectors格式（必须是包含embedding/text的字典列表）
            valid_vecs = []
            for item in vecs:
                if isinstance(item, dict) and "embedding" in item and "text" in item:
                    valid_vecs.append(item)
                else:
                    print(f"   ⚠️ 跳过无效向量项：{item[:20] if isinstance(item, list) else item}")
            
            # 加载到内存
            corpora[user_id] = corpus
            vectors[user_id] = valid_vecs
            
            print(f"   ✅ 读取成功 | 格式：{type(pkl_data).__name__} | Chunk={chunk_count}, 有效向量={len(valid_vecs)} | 耗时：{load_cost:.6f} 秒")
        except Exception as e:
            print(f"   ❌ 读取失败：{str(e)[:100]}")
            continue
        
        # 2. 构建Prompt
        start_build = time.time()
        retrieved_all = retrieve_top_k(user_id, test_query, top_k=top_k)
        THRESHOLD = 0.7
        retrieved = [item for item in retrieved_all if item.get("score", 0.0) >= THRESHOLD]
        
        # 构造Prompt
        today_str = time.strftime("%Y-%m-%d")
        user_name = get_user_name(user_id)
        system_prompt = f"你叫{user_name}，是知识库助手，日期：{today_str}。基于片段回答问题，无相关信息请说明。"
        
        context_parts = []
        for i, item in enumerate(retrieved[:2]):
            context_parts.append(f"[片段 {i+1} | score={item['score']:.3f}]\n{item['text'][:50]}...")
        context_str = "（未检索到相似内容）" if not retrieved else "\n\n".join(context_parts)
        user_prompt = f"【参考片段】\n{context_str}\n\n【问题】\n{test_query}"
        
        build_cost = time.time() - start_build
        total_cost = load_cost + build_cost

        # 记录结果
        batch_results.append({
            "file_name": file_name,
            "load_cost": load_cost,
            "build_cost": build_cost,
            "total_cost": total_cost,
            "chunk_count": chunk_count,
            "valid_vec_count": len(valid_vecs),
            "retrieved_count": len(retrieved)
        })

        print(f"   📝 构建Prompt耗时：{build_cost:.6f} 秒")
        print(f"   🕒 总耗时：{total_cost:.6f} 秒")
        print(f"   🔍 检索有效片段：{len(retrieved)} 个")

    # 第三步：汇总结果
    print("\n" + "="*70)
    print("📊 批量PKL测试汇总结果")
    print("="*70)
    if not batch_results:
        print("❌ 无有效测试结果！")
        return None
    
    avg_load = sum(r["load_cost"] for r in batch_results) / len(batch_results)
    avg_build = sum(r["build_cost"] for r in batch_results) / len(batch_results)
    avg_total = sum(r["total_cost"] for r in batch_results) / len(batch_results)
    fastest = min(batch_results, key=lambda x: x["load_cost"])
    slowest = max(batch_results, key=lambda x: x["load_cost"])
    largest = max(batch_results, key=lambda x: x["chunk_count"])

    print(f"✅ 成功测试 {len(batch_results)} / {len(pkl_files)} 个PKL文件")
    print(f"📈 平均读取耗时：{avg_load:.6f} 秒/文件")
    print(f"📈 平均构建耗时：{avg_build:.6f} 秒/文件")
    print(f"📈 平均总耗时：{avg_total:.6f} 秒/文件")
    print(f"⚡ 最快读取：{fastest['file_name']} ({fastest['load_cost']:.6f} 秒)")
    print(f"🐢 最慢读取：{slowest['file_name']} ({slowest['load_cost']:.6f} 秒)")
    print(f"📦 数据量最大：{largest['file_name']} (Chunk={largest['chunk_count']})")
    print("="*70)

    return batch_results

# ============== 运行测试 ==============
if __name__ == "__main__":
    # 修改为你的PKL目录
    TEST_DIR = r"C:\Users\Administrator\xwechat_files\hhkandmogu_cf73\msg\file\2026-01\rag_jiebaobao_update\rag_vector_storage\jb1"
    batch_test_all_pkl_in_dir(
        test_dir=TEST_DIR,
        test_query="Jabra产品的核心优势和功能有哪些？",
        top_k=5
    )
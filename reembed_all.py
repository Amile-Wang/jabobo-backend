"""
One-shot reembedding script: re-vectorize every kb.pkl under data/ using Azure
OpenAI text-embedding-3-small (1536-d), replacing the old ARK doubao
embeddings (2048-d). Atomic per-file: write to <pkl>.tmp then os.replace().
"""
import os
import sys
import time
import pickle
import glob
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

API_KEY = os.environ["AZURE_OAI_EMBED_API_KEY"]
BASE_URL = os.environ["AZURE_OAI_EMBED_BASE_URL"]
MODEL = os.environ["AZURE_OAI_EMBED_MODEL"]
BATCH = 64

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def embed_batch(texts, max_retries=3):
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.embeddings.create(model=MODEL, input=texts, timeout=60)
            return [d.embedding for d in resp.data]
        except Exception as e:
            last_exc = e
            wait = 2 ** attempt
            print(f"  ! batch failed (attempt {attempt}/{max_retries}): {e}; sleep {wait}s")
            time.sleep(wait)
    raise last_exc


def reembed_pkl(pkl_path):
    print(f"\n=== {pkl_path} ===")
    with open(pkl_path, "rb") as f:
        old = pickle.load(f)
    if not old:
        print("  empty, skip")
        return
    print(f"  loaded {len(old)} chunks; old dim={len(old[0]['embedding']) if old[0].get('embedding') else 'n/a'}")

    new = []
    for i in range(0, len(old), BATCH):
        batch = old[i:i + BATCH]
        texts = [c["text"] for c in batch]
        t0 = time.time()
        embs = embed_batch(texts)
        cost = time.time() - t0
        print(f"  batch {i // BATCH + 1}: {len(batch)} chunks in {cost:.2f}s")
        for c, e in zip(batch, embs):
            new.append({"embedding": e, "text": c["text"], "source": c["source"]})

    new_dim = len(new[0]["embedding"])
    print(f"  new chunks={len(new)} dim={new_dim}")

    tmp = pkl_path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(new, f)
    os.replace(tmp, pkl_path)
    print(f"  ✅ written {pkl_path}")


def main():
    pkls = sorted(glob.glob(os.path.join(DATA_DIR, "**", "*.pkl"), recursive=True))
    print(f"found {len(pkls)} pkl files")
    for p in pkls:
        try:
            reembed_pkl(p)
        except Exception as e:
            print(f"  ❌ FAILED {p}: {e}")
            sys.exit(2)
    print("\nall done")


if __name__ == "__main__":
    main()

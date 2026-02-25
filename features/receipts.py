from typing import List, Dict, Optional
from pathlib import Path
import re
import os
import json
import numpy as np
import pytesseract
import subprocess
from pdf2image import convert_from_path
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from core.ctr import CTR, validate_ctr
from core.policy import check_policy
from core.logger import log_ctr
from core.nlu_router import get_model

def ocr_image(file_path):
    if file_path.suffix.lower() == ".pdf":
        pages = convert_from_path(file_path)
        text = ""
        for page in pages:
            text += pytesseract.image_to_string(page)
        return text
    else:
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)


def rank_receipts_against_query(files_content, query):
    """Semantic ranking using embeddings (LLM-style similarity)."""

    texts = [f["content"] for f in files_content]
    model = get_model()

    # Create embeddings
    query_embedding = model.encode([query])
    doc_embeddings = model.encode(texts)

    # Compute similarity
    similarities = cosine_similarity(query_embedding, doc_embeddings)[0]

    ranked = []
    for i, score in enumerate(similarities):
        ranked.append({
            "file": files_content[i]["file"],
            "path": files_content[i]["path"],
            "score": float(score),
            "content": files_content[i]["content"][:200]
        })

    return sorted(ranked, key=lambda x: x["score"], reverse=True)

def process_receipts(source_dir: str, query: str, export_dir: Optional[str] = None, dry_run: bool = True) -> List[Dict]:
    """AI-powered: OCR → Rank documents by query relevance."""
    if not source_dir:
        source_path = Path.home() / "test_receipts"
    else:
        source_path = Path(source_dir).expanduser()
    export_path = Path(export_dir).expanduser() if export_dir else source_path / "Receipts"
    export_path.mkdir(exist_ok=True)
    
    # Find ALL documents
    all_files = list(source_path.rglob("*"))
    doc_contents = []
    
    print(f"[AI-RECEIPTS] Found {len(all_files)} files, searching for '{query}'...")
    
    for file_path in all_files[:20]:  # Top 20 files
        if file_path.is_file() and file_path.suffix in ['.txt', '.pdf', '.jpg', '.png']:
            try:
                if file_path.suffix == '.txt':
                    content = file_path.read_text()
                else:
                    content = ocr_image(file_path)[:2000]  # OCR + truncate
                
                if len(content.strip()) > 10:  # receipts are short!
                    doc_contents.append({
                        "file": file_path.name,
                        "path": str(file_path),
                        "content": content.lower()
                    })
            except:
                continue
    
    if not doc_contents:
        print("[AI-RECEIPTS] No meaningful documents found")
        return []
    
    # AI RANKING ↓ MAGIC
    ranked = rank_receipts_against_query(doc_contents, query.lower())

    if dry_run:
        print(f"[DRY-RUN] Top 3 matches for '{query}':")
        for i, doc in enumerate(ranked[:3]):
            print(f"  {i+1}. {doc['file']} (score: {doc['score']:.1%})")

    else:
        print(f"[AI-RECEIPTS] Top matches for '{query}':")
        for i, doc in enumerate(ranked[:5]):
            score = doc['score']
            json_path = export_path / f"{Path(doc['file']).stem}_ranked_{i+1}.json"
            json.dump(
                {"file": doc['file'], "relevance": score, "preview": doc['content']},
                json_path.open('w'),
                indent=2
            )
            print(f"  ✅ {i+1}. {doc['file']} ({score:.1%})")
        if ranked:
            top_path = ranked[0]["path"]
            print(f"\n🚀 Opening best match: {top_path}")
            subprocess.Popen(["xdg-open", top_path])

    return ranked


# Update CLI action
def find_receipts_action(source_dir: str = "", query: str = "", export_dir: Optional[str] = None, dry_run: bool = True):
    ctr = CTR(task_type="FIND_RECEIPTS", params={"source_dir": source_dir, "query": query, "export_dir": export_dir})
    print(f"[WORKFLOW] CTR: {ctr}")
    log_ctr(ctr, "STARTED")
    validate_ctr(ctr)
    log_ctr(ctr, "VALIDATED")
    if not query:
        query = "receipt"
    affected_paths = [source_dir]
    if export_dir:  # ✅ Fixed: use export_dir (not export_dir)
        affected_paths.append(export_dir)
    check_policy(ctr, affected_paths)
    log_ctr(ctr, "POLICY_APPROVED")
    
    if dry_run:
        print("[DRY-RUN] AI document search preview")
        log_ctr(ctr, "COMPLETED", {"dry_run": True})
    else:
        # ✅ FIXED: Pass query parameter
        results = process_receipts(source_dir, query, export_dir, False)
        log_ctr(ctr, "COMPLETED", {"matches": len(results)})


# Global instance
receipts_engine = process_receipts

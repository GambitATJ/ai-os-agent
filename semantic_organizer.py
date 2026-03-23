"""
semantic_organizer.py

Semantic file clustering and organization using SentenceTransformers and KMeans.
"""

import os
import shutil
import json
import collections
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from checkpoint_manager import CheckpointManager


class SemanticOrganizer:
    
    def __init__(self):
        # We instantiate the model once; it will download the weights on first run
        # if they aren't already cached.
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def _get_file_text(self, filepath: str) -> str:
        """Extract a semantic representation of a file combining its name and top 300 bytes."""
        basename = os.path.basename(filepath)
        content_preview = ""
        try:
            with open(filepath, "rb") as f:
                head = f.read(300)
                content_preview = head.decode("utf-8", errors="ignore")
        except Exception:
            pass  # If unreadable, fallback to just the basename
            
        return f"{basename} {content_preview}"
    
    def _choose_k(self, embeddings: np.ndarray, max_k: int) -> int:
        """Automatically determine the optimal number of clusters using silhouette score."""
        n_samples = len(embeddings)
        if n_samples < 4:
            return 2
            
        best_k = 2
        best_score = -1.0
        
        limit = min(max_k, n_samples - 1)
        
        for k in range(2, limit + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
            
            # Silhouette score requires at least 2 clusters to compute
            score = silhouette_score(embeddings, labels)
            if score > best_score:
                best_score = score
                best_k = k
                
        return best_k
    
    def _cluster_name(self, filepaths: list[str]) -> str:
        """Generate a folder name from the most frequent significant words in the group's filenames."""
        stopwords = {
            'the','a','an','and','or','of','in','to','for','is',
            'at','by','from','with','on','as','it','its','this','that',
            'img','file','document','doc','copy','new','old','final'
        }
        
        words = []
        for path in filepaths:
            basename = os.path.basename(path)
            # Remove extension for naming purposes
            name_no_ext, _ = os.path.splitext(basename)
            # Split on non-alphanumeric chars
            tokens = re.split(r'[^a-zA-Z0-9]', name_no_ext)
            
            for token in tokens:
                token_lower = token.lower()
                if (token_lower not in stopwords and 
                    len(token_lower) >= 3 and 
                    not token_lower.isdigit()):
                    words.append(token_lower)
                    
        if not words:
            return "misc_files"
            
        counter = collections.Counter(words)
        top_words = [word for word, count in counter.most_common(3)]
        return "_".join(top_words)
    
    def analyze(self, directory: str) -> dict:
        """Analyze a directory and return a semantic clustering plan."""
        target_dir = os.path.expanduser(directory)
        
        if not os.path.exists(target_dir):
            return {'error': f'Directory does not exist: {target_dir}'}
            
        # Collect all files directly inside the target directory
        filepaths = []
        try:
            for entry in os.listdir(target_dir):
                full_path = os.path.join(target_dir, entry)
                if os.path.isfile(full_path):
                    filepaths.append(full_path)
        except Exception as e:
            return {'error': str(e)}
            
        if len(filepaths) < 3:
            return {'error': 'Not enough files to cluster (minimum 3).'}
            
        # Build semantic representations
        texts = [self._get_file_text(fp) for fp in filepaths]
        
        # Embed all texts
        embeddings = self.model.encode(texts)
        
        # Determine optimal K (up to max_k=6)
        k = self._choose_k(embeddings, max_k=6)
        
        # Perform final clustering
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        
        # Group filepaths by label
        clusters_by_label = collections.defaultdict(list)
        for fp, label in zip(filepaths, labels):
            clusters_by_label[label].append(fp)
            
        # Construct the final output
        cluster_list = []
        for cluster_files in clusters_by_label.values():
            folder_name = self._cluster_name(cluster_files)
            cluster_list.append({
                'folder_name': folder_name,
                'files': cluster_files
            })
            
        return {
            'target_directory': target_dir,
            'clusters': cluster_list
        }

    def display_proposal(self, analysis: dict) -> None:
        if 'error' in analysis:
            print(analysis['error'])
            return
            
        target_dir = analysis['target_directory']
        print(f"Proposed reorganization for: {target_dir}")
        print()
        
        total_files = 0
        clusters = analysis['clusters']
        
        for cluster in clusters:
            print(f"  📁 {cluster['folder_name']}/")
            for file_path in cluster['files']:
                print(f"      └── {os.path.basename(file_path)}")
                total_files += 1
                
        print()
        print(f"Total: {total_files} files → {len(clusters)} folders")

    def execute(self, analysis: dict) -> str:
        if 'error' in analysis:
            return analysis['error']
            
        target_dir = analysis['target_directory']
        clusters = analysis['clusters']
        
        all_files = [f for c in clusters for f in c['files']]
        
        cm = CheckpointManager()
        cm.capture(
            affected_paths=all_files,
            command_text=f"semantic directory reorganization of {target_dir}"
        )
        
        total_files = 0
        for cluster in clusters:
            new_folder = os.path.join(target_dir, cluster['folder_name'])
            os.makedirs(new_folder, exist_ok=True)
            
            for file_path in cluster['files']:
                dest = os.path.join(new_folder, os.path.basename(file_path))
                shutil.move(file_path, dest)
                total_files += 1
                
        return f"Moved {total_files} files into {len(clusters)} folders in {target_dir}."


def run_organizer_flow(directory: str) -> None:
    organizer = SemanticOrganizer()
    analysis = organizer.analyze(directory)
    
    organizer.display_proposal(analysis)
    
    if 'error' in analysis:
        return
        
    print("Apply this reorganization? (y/n):")
    try:
        choice = input().strip().lower()
    except EOFError:
        choice = "n"
        
    if choice == 'y':
        result = organizer.execute(analysis)
        print(result)
    else:
        print("Reorganization cancelled. No files were moved.")


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    import tempfile
    import sys
    import io
    
    print("=== SemanticOrganizer Demo ===\n")
    
    # We patch SQLiteManager for the CheckpointManager inside the demo
    # so we don't pollute the real user database.
    import checkpoint_manager as _cm
    from db_manager import SQLiteManager
    
    db_proxy = SQLiteManager(db_path=":memory:")
    class P:
        def __init__(self, db_path=None): pass
        def __getattr__(self, n): return getattr(db_proxy, n)
        def close(self): pass
        
    _cm.SQLiteManager = P
    
    tmpdir = tempfile.mkdtemp()
    
    try:
        # Create 12 files across 3 themes (invoices, photos, code)
        
        # Theme 1: Invoices / Corporate
        with open(os.path.join(tmpdir, "invoice_july_2026.pdf"), "w") as f:
            f.write("Invoice #59102. Amount due: $450.00. Services rendered.")
        with open(os.path.join(tmpdir, "corp_tax_receipt.txt"), "w") as f:
            f.write("Receipt for corporate tax filing fee 2025. Paid in full.")
        with open(os.path.join(tmpdir, "contract_vendor_agreement.doc"), "w") as f:
            f.write("Agreement between Corporate Inc and Vendor LLC.")
        with open(os.path.join(tmpdir, "Q3_billing_statement.csv"), "w") as f:
            f.write("date,amount,client\n07-01,500,A\n08-15,600,B")
            
        # Theme 2: Photos / Vacation
        with open(os.path.join(tmpdir, "img_paris_eiffel_tower.jpg"), "w") as f:
            f.write("EXIF data: taken in Paris, France. Beautiful landmark.")
        with open(os.path.join(tmpdir, "summer_vacation_itinerary.txt"), "w") as f:
            f.write("Day 1: Louvre. Day 2: Boat tour on the Seine.")
        with open(os.path.join(tmpdir, "img_louvre_museum_entrance.png"), "w") as f:
            f.write("Image snapshot... glass pyramid building")
        with open(os.path.join(tmpdir, "train_tickets_europe.pdf"), "w") as f:
            f.write("Eurostar ticket from London to Paris. Non-refundable.")
            
        # Theme 3: Code / Scripts
        with open(os.path.join(tmpdir, "main_server_loop.py"), "w") as f:
            f.write("import socket\n\nwhile True:\n    conn, addr = s.accept()")
        with open(os.path.join(tmpdir, "database_schema_v2.sql"), "w") as f:
            f.write("CREATE TABLE users (id INT PRIMARY KEY, email VARCHAR);")
        with open(os.path.join(tmpdir, "deploy_production.sh"), "w") as f:
            f.write("##!/bin/bash\necho 'Deploying to prod...'\nkubectl apply -f .")
        with open(os.path.join(tmpdir, "docker_compose_dev.yml"), "w") as f:
            f.write("version: '3'\nservices:\n  db:\n    image: postgres:15")

        # Mock interactive input to automatically type 'y'
        original_stdin = sys.stdin
        sys.stdin = io.StringIO("y\n")
        
        run_organizer_flow(tmpdir)
        
        sys.stdin = original_stdin
        
        print("\nDemo execution complete. Checking final directory state:")
        for root, dirs, files in os.walk(tmpdir):
            level = root.replace(tmpdir, '').count(os.sep)
            indent = ' ' * 4 * (level)
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                print(f"{subindent}{f}")
                
    finally:
        shutil.rmtree(tmpdir)

# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    import tempfile
    
    print("\n=== Running Tests ===\n")
    
    # We use a shared instance to avoid reloading the model for every test
    organizer = SemanticOrganizer()
    
    # Test 1: Directory with < 3 files returns an error
    print("Test 1: Directory with 2 files returns minimum files error")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "file1.txt"), "w") as f: f.write("test")
        with open(os.path.join(tmpdir, "file2.txt"), "w") as f: f.write("test")
        
        result = organizer.analyze(tmpdir)
        assert 'error' in result
        assert "minimum 3" in result['error']
    print("  PASSED\n")
    
    # Test 2: _cluster_name correctly extracts top words and ignores stopwords
    print("Test 2: _cluster_name extracts token words and drops stopwords")
    paths = [
        "/tmp/the_annual_financial_report_final.doc",
        "/tmp/monthly_financial_summary.pdf",
        "/tmp/financial_budget_draft.xls"
    ]
    name = organizer._cluster_name(paths)
    assert "financial" in name
    assert "the" not in name  # stopword
    assert "final" not in name # stopword
    assert "doc" not in name  # stopword
    print(f"  Got name: '{name}' -> PASSED\n")
    
    # Test 3: _get_file_text correctly combines basename + content
    print("Test 3: _get_file_text combines basename and top content")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
        tf.write(b"Hello world content")
        tmp_path = tf.name
        
    try:
        text = organizer._get_file_text(tmp_path)
        assert os.path.basename(tmp_path) in text
        assert "Hello world content" in text
    finally:
        os.unlink(tmp_path)
    print("  PASSED\n")
        
    print("=== All Tests Passed ===")

if __name__ == "__main__":
    _run_tests()
    print()
    run_demo()

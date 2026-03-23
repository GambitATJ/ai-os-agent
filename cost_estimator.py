"""
cost_estimator.py

Estimates and logs the time/cost of executing workflows within AI-OS.
"""

import os
import time
from datetime import datetime
from db_manager import SQLiteManager


class CostEstimator:
    SECONDS_PER_FILE = 0.003
    SECONDS_PER_STEP = 0.5

    def estimate(self, target_directory: str, ctr_step_count: int) -> dict:
        """Estimate execution time up to a depth of 2."""
        target_dir = os.path.expanduser(target_directory)
        file_count = 0
        
        if os.path.exists(target_dir):
            base_depth = target_dir.count(os.sep)
            for root, dirs, files in os.walk(target_dir):
                current_depth = root.count(os.sep)
                if current_depth - base_depth > 2:
                    del dirs[:]  # Stop expanding this branch
                    continue
                file_count += len(files)
                
        estimated_seconds = (file_count * self.SECONDS_PER_FILE) + (ctr_step_count * self.SECONDS_PER_STEP)
        
        return {
            "file_count": file_count,
            "step_count": ctr_step_count,
            "estimated_seconds": round(estimated_seconds, 1),
            "target_directory": target_dir
        }

    def display_estimate(self, estimate: dict) -> str:
        """Format the estimate for CLI presentation."""
        return (
            f"Cost estimate: ~{estimate['file_count']} files, "
            f"{estimate['step_count']} steps, "
            f"approximately {estimate['estimated_seconds']}s. "
            f"[P]roceed / [O]ptimize / [C]ancel:"
        )
    
    def optimized_estimate(self, target_directory: str, ctr_step_count: int) -> dict:
        """Faster estimate: caps depth at 1 and file_count at 100."""
        target_dir = os.path.expanduser(target_directory)
        file_count = 0
        
        if os.path.exists(target_dir):
            base_depth = target_dir.count(os.sep)
            for root, dirs, files in os.walk(target_dir):
                current_depth = root.count(os.sep)
                if current_depth - base_depth > 1:
                    del dirs[:]
                    continue
                
                file_count += len(files)
                if file_count >= 100:
                    file_count = 100
                    break
                    
        estimated_seconds = (file_count * self.SECONDS_PER_FILE) + (ctr_step_count * self.SECONDS_PER_STEP)
        
        return {
            "file_count": file_count,
            "step_count": ctr_step_count,
            "estimated_seconds": round(estimated_seconds, 1),
            "target_directory": target_dir,
            "optimized": True
        }
    
    def log_actual(self, feature_name: str, estimate: dict, actual_seconds: float) -> None:
        """Log the estimated vs actual performance to the database."""
        db = SQLiteManager()
        db.insert("performance_log", {
            "feature_name": feature_name,
            "estimated_seconds": estimate["estimated_seconds"],
            "actual_seconds": actual_seconds,
            "file_count": estimate["file_count"],
            "step_count": estimate["step_count"],
            "timestamp": datetime.utcnow().isoformat()
        })
        db.close()


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    import tempfile
    
    print("=== CostEstimator Demo ===\n")
    
    from db_manager import SQLiteManager as SQLiteManagerORG
    global SQLiteManager
    db_proxy = SQLiteManagerORG(db_path=":memory:")
    class P:
        def __init__(self, db_path=None): pass
        def __getattr__(self, n): return getattr(db_proxy, n)
        def close(self): pass
        
    from db_manager import SQLiteManager as SQLiteManagerORG
    global SQLiteManager
    SQLiteManager = P
    
    estimator = CostEstimator()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some files at various depths
        os.makedirs(os.path.join(tmpdir, "d1", "d2", "d3"))
        
        # Depth 0
        for i in range(10): 
            with open(os.path.join(tmpdir, f"f{i}.txt"), "w") as f: f.write("0")
        
        # Depth 1
        for i in range(10):
            with open(os.path.join(tmpdir, "d1", f"f{i}.txt"), "w") as f: f.write("1")
            
        # Depth 2
        for i in range(10):
            with open(os.path.join(tmpdir, "d1", "d2", f"f{i}.txt"), "w") as f: f.write("2")
            
        # Depth 3 (Should be ignored by regular estimate, which caps at depth 2)
        for i in range(150):
            with open(os.path.join(tmpdir, "d1", "d2", "d3", f"f{i}.txt"), "w") as f: f.write("3")
            
        print(f"Directory tree created with > 180 files at depth 0,1,2,3.")
        
        # Regular Estimate (Depth 2 max)
        # Expected files: 10 + 10 + 10 = 30
        est = estimator.estimate(tmpdir, ctr_step_count=4)
        print("\n--- Standard Estimate (Depth <= 2) ---")
        print(estimator.display_estimate(est))
        
        # Optimized Estimate (Depth 1 max, file limit 100)
        # Expected files: 10 + 10 = 20
        opt_est = estimator.optimized_estimate(tmpdir, ctr_step_count=4)
        print("\n--- Optimized Estimate (Depth <= 1) ---")
        print(estimator.display_estimate(opt_est))
        
        # Simulate execution
        print("\nSimulating execution for 2.1 seconds...")
        time.sleep(2.1)
        actual = 2.12
        
        print("\nLogging actual performance...")
        estimator.log_actual("demo_workflow", est, actual)
        
        rows = db_proxy.fetch_all("performance_log")
        print("Latest DB Row in performance_log:")
        for k, v in rows[0].items():
            print(f"  {k}: {v}")

# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    import tempfile
    
    print("\n=== Running Tests ===\n")
    
    from db_manager import SQLiteManager as SQLiteManagerORG
    global SQLiteManager
    db_proxy = SQLiteManagerORG(db_path=":memory:")
    class P:
        def __init__(self, db_path=None): pass
        def __getattr__(self, n): return getattr(db_proxy, n)
        def close(self): pass
        
    from db_manager import SQLiteManager as SQLiteManagerORG
    global SQLiteManager
    SQLiteManager = P
    
    estimator = CostEstimator()
    
    # Test 1: estimate() respects depth=2
    print("Test 1: estimate() depth limit")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "a", "b", "c"))
        with open(os.path.join(tmpdir, "f1.txt"), "w") as f: f.write("x")                     # depth 0
        with open(os.path.join(tmpdir, "a", "f2.txt"), "w") as f: f.write("x")                # depth 1
        with open(os.path.join(tmpdir, "a", "b", "f3.txt"), "w") as f: f.write("x")           # depth 2
        with open(os.path.join(tmpdir, "a", "b", "c", "f4.txt"), "w") as f: f.write("x")      # depth 3
        
        est = estimator.estimate(tmpdir, 10)
        assert est["file_count"] == 3, f"Expected 3 files, got {est['file_count']}"
        assert est["step_count"] == 10
    print("  PASSED\n")
    
    # Test 2: optimized_estimate() limits files to 100
    print("Test 2: optimized_estimate() file ceiling limit")
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(120):
            with open(os.path.join(tmpdir, f"f{i}.txt"), "w") as f: f.write("x")
            
        opt = estimator.optimized_estimate(tmpdir, 2)
        assert opt["file_count"] == 100, f"Expected 100 files, got {opt['file_count']}"
        assert opt["optimized"] is True
    print("  PASSED\n")
    
    # Test 3: display format matches strictly
    print("Test 3: display format strict matching")
    dummy_est = {"file_count": 50, "step_count": 4, "estimated_seconds": 2.1}
    out = estimator.display_estimate(dummy_est)
    expected = "Cost estimate: ~50 files, 4 steps, approximately 2.1s. [P]roceed / [O]ptimize / [C]ancel:"
    assert out == expected, f"Output format mismatch.\nExpected: {expected}\nGot:      {out}"
    print("  PASSED\n")
    
    print("=== All Tests Passed ===")

if __name__ == "__main__":
    _run_tests()
    print()
    run_demo()

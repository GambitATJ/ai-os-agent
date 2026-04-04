import docker
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

class Sandbox:
    def __init__(self):
        self.client = docker.from_env()
    
    def process_receipts(self, source_dir: str) -> Dict[str, Any]:
        from checkpoint_manager import CheckpointManager
        cm = CheckpointManager()
        affected = [source_dir]
        cm.capture(affected, command_text="Copy receipts to sandbox directory")

        # Copy files to temp sandbox
        sandbox_dir = Path(tempfile.mkdtemp())
        shutil.copytree(source_dir, sandbox_dir / "input", dirs_exist_ok=True)
        
        # Run OCR+LLM container
        container = self.client.containers.run(
            "ai-os-receipt-processor:latest",  # We'll build this
            volumes={str(sandbox_dir): {"bind": "/sandbox", "mode": "ro"}},
            command=["process", "/sandbox/input"],
            remove=True,
            mem_limit="512m"  # Sandbox limits
        )
        
        # Parse results
        results = container.logs().decode()
        shutil.rmtree(sandbox_dir)
        return {"structured": results, "sandbox": "isolated"}

from pathlib import Path
from jinja2 import Template
from typing import Dict
from core.ctr import CTR, validate_ctr
from core.policy import check_policy
from core.logger import log_ctr

TEMPLATES = {
    "invoice": """
INVOICE #{{ invoice_id }}
Date: {{ date }}
From: {{ sender_name }}
To: {{ recipient_name }}

Items:
{% for item in items %}
• {{ item.name }}: ${{ "%.2f"|format(item.price) }} × {{ item.qty }} = ${{ "%.2f"|format(item.total) }}
{% endfor %}

TOTAL: ${{ "%.2f"|format(total_amount) }}

Thank you! {{ sender_name }}
    """,
    "readme": "# {{ project_name }}\n\n{{ description }}\n\n## Features\n{{ features|join('\\n- ') }}",
    "email": """Subject: {{ subject }}

Dear {{ recipient }},

{{ body }}

Best,
{{ sender }}"""
}

def generate_template(template_name: str, output_path: str, dry_run: bool = True, **kwargs):
    """Generate file from Jinja2 template."""
    output = Path(output_path).expanduser()
    output.parent.mkdir(exist_ok=True)
    
    if template_name not in TEMPLATES:
        print(f"[TEMPLATES] ❌ Unknown template: {template_name}")
        print("Available: invoice, readme, email")
        return
    
    tmpl_str = TEMPLATES[template_name]
    template = Template(tmpl_str)
    
    if dry_run:
        print(f"[DRY-RUN] Would generate {output}")
        print(template.render(**kwargs)[:200] + "...")
    else:
        content = template.render(**kwargs)
        output.write_text(content)
        print(f"✅ Generated: {output}")

def generate_template_action(template_name: str, output_path: str, dry_run: bool = True):
    """CTR workflow for templates."""
    ctr = CTR(
        task_type="GENERATE_TEMPLATE",
        params={"template": template_name, "output": output_path}
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    log_ctr(ctr, "STARTED")
    validate_ctr(ctr)
    log_ctr(ctr, "VALIDATED")
    
    affected_paths = [output_path]
    check_policy(ctr, affected_paths)
    log_ctr(ctr, "POLICY_APPROVED")
    
    if dry_run:
        print("[EXECUTOR] DRY-RUN preview")
    else:
        # Default data for demo
        generate_template(template_name, output_path, False,
            invoice_id="INV001", date="2026-02-17",
            sender_name="Acme Corp", recipient_name="Client LLC",
            items=[{"name": "Consulting", "price": 150.0, "qty": 4, "total": 600.0}],
            total_amount=600.0,
            project_name="AI-OS Agent", description="CTR Architecture",
            features=["CTR Safety", "Audit Logging", "Sandbox Processing"],
            subject="Project Update", recipient="Team", sender="Aaron",
            body="Feature complete!")
        log_ctr(ctr, "COMPLETED")

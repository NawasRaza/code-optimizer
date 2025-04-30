import os
import json
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime

def generate_report(optimized_code: str, format: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)
    file_path = f"{output_dir}/report_{timestamp}.{format}"

    # Sample report data
    report_data = {
        "timestamp": timestamp,
        "optimized_code": optimized_code,
        "optimization_summary": "Basic optimizations applied (redundant assignments removed, constant folding)."
    }

    if format == "pdf":
        doc = SimpleDocTemplate(file_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Python Code Optimization Report", styles['Title']),
            Spacer(1, 12),
            Paragraph(f"Generated on: {timestamp}", styles['Normal']),
            Spacer(1, 12),
            Paragraph("Optimized Code:", styles['Heading2']),
            Paragraph(optimized_code, styles['Code']),
            Spacer(1, 12),
            Paragraph("Summary:", styles['Heading2']),
            Paragraph(report_data["optimization_summary"], styles['Normal'])
        ]
        doc.build(story)

    elif format == "csv":
        df = pd.DataFrame([report_data])
        df.to_csv(file_path, index=False)

    elif format == "json":
        with open(file_path, "w") as f:
            json.dump(report_data, f, indent=4)

    else:
        raise ValueError("Unsupported format")

    return file_path
"""
LLM Converter — гибридный подход
"""

import json
import re
from pathlib import Path
from model import MicroHydraModel

class LLMConverter:
    def __init__(self):
        self.model = None
        self.model_path = Path(__file__).parent / "trained_model.json"
        self.use_rules = True
        
        if self.model_path.exists():
            try:
                with open(self.model_path) as f:
                    data = json.load(f)
                    if data.get('type') != 'rules':
                        self.model = MicroHydraModel.load(str(self.model_path))
            except:
                pass
    
    def is_ready(self):
        return True  # Всегда готов (правила работают)
    
    def predict(self, code: str):
        # Строгие правила
        if 'def setup(client)' in code or 'modules_help' in code:
            return 'hydra', 1.0
        if 'from hikka import' in code.lower():
            return 'hikka', 1.0
        if 'from core import loader' in code.lower():
            return 'mcub', 1.0
        
        # Нейросеть если есть
        if self.model:
            return self.model.predict(code)
        
        return 'unknown', 0.33
    
    def analyze_and_convert(self, code: str, module_name: str):
        pred_type, conf = self.predict(code)
        
        info = {
            "original_type": pred_type,
            "confidence": conf,
            "converted": pred_type != "hydra",
            "method": "rules" if conf == 1.0 else "model"
        }
        
        if pred_type == "hikka":
            code = re.sub(r'from\s+hikka\s+import[^\n]*\n', '', code)
        elif pred_type == "mcub":
            code = code.replace('from core import', 'from utils.loader import')
            code = code.replace('@loader.command', '')
        
        return code, info

llm_converter = LLMConverter()

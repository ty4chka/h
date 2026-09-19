# utils/template_manager.py
"""Hydra Template Manager"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

DATA_DIR = Path("data")
TEMPLATES_FILE = DATA_DIR / "hydra_templates.json"
IMAGES_DIR = DATA_DIR / "images"

DEFAULT_TEMPLATES = {
    "ping": {
        "template": "<b>🏓 {emoji} {title}</b>\n\n<blockquote>🌐 Сеть: <code>{ping}ms</code>\n🛠 Ядро: <code>{core}ms</code>\n⏳ Аптайм: <code>{uptime}</code></blockquote>\n\n<i>{footer}</i>",
        "emoji": "🏓", "title": "РЕЗУЛЬТАТЫ", "footer": "Hydra Cython", "image_url": ""
    },
    "info": {
        "template": "<b>{emoji} {title}</b>\n\n<blockquote>👤 <code>{owner}</code>\n⏰ <code>{uptime}</code>\n⚡ <code>{core}ms</code>\n📦 <code>{modules}</code> модулей</blockquote>\n\n<i>{footer}</i>",
        "emoji": "🔱", "title": "HYDRA", "footer": "⚡ Cython Edition", "image_url": ""
    }
}

class TemplateManager:
    def __init__(self):
        self.templates = self.load()
    
    def load(self) -> Dict:
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True)
        if TEMPLATES_FILE.exists():
            try:
                with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        self.save(DEFAULT_TEMPLATES)
        return DEFAULT_TEMPLATES.copy()
    
    def save(self, templates: Dict = None):
        if templates:
            self.templates = templates
        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
    
    def get(self, module: str) -> Dict:
        return self.templates.get(module, {})
    
    def format(self, module: str, variables: Dict) -> str:
        tpl = self.get(module)
        template = tpl.get("template", "")
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template
    
    def set_field(self, module: str, field: str, value: Any) -> bool:
        if module in self.templates and field in self.templates[module]:
            self.templates[module][field] = value
            self.save()
            return True
        return False

tm = TemplateManager()

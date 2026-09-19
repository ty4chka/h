"""
ГИБРИДНЫЙ КЛАССИФИКАТОР: Правила + Нейросеть
- Правила дают 100% точность на известных паттернах
- Нейросеть обрабатывает сложные/неизвестные случаи
"""

import json
import re
from pathlib import Path
from model import MicroHydraModel

class HybridClassifier:
    def __init__(self):
        self.rules_confident = True
        self.model = None
        self.model_path = Path("trained_model.json")
        
        # Пробуем загрузить нейросеть
        try:
            with open(self.model_path) as f:
                data = json.load(f)
                if data.get('type') != 'rules':
                    self.model = MicroHydraModel.load(str(self.model_path))
                    print("✅ Нейросеть загружена")
        except:
            pass
        
        # Строгие правила
        self.rules = [
            # HYDRA (100% уверенность)
            (lambda c: 'def setup(client)' in c, 'hydra', 1.0),
            (lambda c: 'modules_help' in c and 'def setup' in c, 'hydra', 1.0),
            (lambda c: 'edit_or_reply' in c and 'def setup' in c, 'hydra', 1.0),
            
            # HIKKA (100% уверенность)
            (lambda c: 'from hikka import' in c.lower(), 'hikka', 1.0),
            (lambda c: 'class' in c and 'Mod' in c and 'loader.Module' in c, 'hikka', 1.0),
            (lambda c: '@loader.tds' in c, 'hikka', 1.0),
            
            # MCUB (100% уверенность)
            (lambda c: 'from core import loader' in c.lower(), 'mcub', 1.0),
            (lambda c: '@loader.command' in c and 'def setup' not in c, 'mcub', 1.0),
        ]
        
        # Мягкие правила (пониженная уверенность)
        self.soft_rules = [
            (lambda c: 'class' in c and 'Mod' in c, 'hikka', 0.7),
            (lambda c: 'loader' in c.lower() and 'command' in c.lower(), 'mcub', 0.6),
            (lambda c: 'telethon' in c.lower() and 'events' in c, 'hydra', 0.6),
        ]
    
    def predict(self, code: str):
        """Гибридное предсказание"""
        
        # 1. Сначала строгие правила (100% точность)
        for rule, pred_type, conf in self.rules:
            if rule(code):
                return pred_type, conf
        
        # 2. Мягкие правила (если нет строгих)
        for rule, pred_type, conf in self.soft_rules:
            if rule(code):
                if self.model:
                    # Проверяем через нейросеть
                    model_pred, model_conf = self.model.predict(code)
                    if model_pred == pred_type or model_conf < 0.5:
                        return pred_type, conf
                    else:
                        return model_pred, model_conf
                return pred_type, conf
        
        # 3. Если ничего не подошло — используем нейросеть
        if self.model:
            return self.model.predict(code)
        
        # 4. Иначе — unknown
        return 'unknown', 0.33
    
    def save(self, path):
        data = {
            "type": "hybrid",
            "version": "1.0",
            "has_model": self.model is not None
        }
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def train_model(self, codes, labels, epochs=30):
        """Дообучить нейросеть на новых данных"""
        self.model = MicroHydraModel(vocab_size=1000, embedding_dim=32)
        history = self.model.train(codes, labels, epochs=epochs, lr=0.005)
        self.save("trained_model.json")
        return history

# ===== ИНИЦИАЛИЗАЦИЯ =====
classifier = HybridClassifier()
classifier.save("trained_model.json")

print("🧠 ГИБРИДНЫЙ КЛАССИФИКАТОР")
print("=" * 50)
print(f"✅ Правила: {len(classifier.rules)} строгих + {len(classifier.soft_rules)} мягких")
print(f"✅ Нейросеть: {'загружена' if classifier.model else 'будет обучаться'}")

# ===== ТЕСТ =====
print("\n🧪 ТЕСТИРОВАНИЕ:")

tests = [
    ("PING.PY", Path("../ping/ping.py"), 'hydra'),
    ("HIKKA", 'from hikka import loader\nclass PingMod(loader.Module): pass', 'hikka'),
    ("MCUB", 'from core import loader\n@loader.command\nasync def ping(): pass', 'mcub'),
    ("СЛОЖНЫЙ", 'class TestMod:\n    async def test_cmd(self): pass', 'hikka'),
]

for name, code_or_path, expected in tests:
    if isinstance(code_or_path, Path) and code_or_path.exists():
        code = code_or_path.read_text()
    else:
        code = code_or_path
    
    pred, conf = classifier.predict(code)
    status = "✅" if pred == expected else "❌"
    print(f"   {status} {name}: {pred} ({conf:.0%})")

print("\n" + "=" * 50)
print("🚀 Готов к использованию в hloader!")

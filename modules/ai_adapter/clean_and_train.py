"""
Очистка данных и обучение на КАЧЕСТВЕННЫХ примерах
"""

import re
from pathlib import Path
from model import MicroHydraModel

training_dir = Path("training_data")

# Ключевые слова для ВАЛИДАЦИИ
VALIDATION = {
    "hikka": ['from hikka', 'loader.Module', '@loader.tds', 'class', 'Mod'],
    "mcub": ['from core', '@loader.command', 'loader'],
    "hydra": ['def setup', 'modules_help', 'from telethon', 'events.NewMessage']
}

print("🧹 ОЧИСТКА ДАННЫХ")
print("=" * 50)

clean_codes, clean_labels = [], []
label_map = {"hikka_samples": 0, "mcub_samples": 1, "hydra_samples": 2}

for folder, label in label_map.items():
    folder_path = training_dir / folder
    folder_type = folder.replace('_samples', '')
    keywords = VALIDATION[folder_type]
    
    kept = 0
    removed = 0
    
    for f in folder_path.glob("*.py"):
        try:
            code = f.read_text(encoding='utf-8')
            
            # Проверка на мусор
            if len(code) < 100:
                removed += 1
                continue
            
            # Проверка что файл соответствует типу
            matches = sum(1 for kw in keywords if kw in code)
            if matches == 0:
                removed += 1
                continue
            
            clean_codes.append(code)
            clean_labels.append(label)
            kept += 1
            
        except:
            removed += 1
    
    print(f"{folder}: ✅ {kept} | ❌ {removed}")

print(f"\n📊 ЧИСТЫХ ДАННЫХ: {len(clean_codes)} (было 123)")

# Обучаем на чистых данных
print("\n🎓 ОБУЧЕНИЕ НА ЧИСТЫХ ДАННЫХ")
print("=" * 50)

model = MicroHydraModel(vocab_size=1000, embedding_dim=32)
history = model.train(clean_codes, clean_labels, epochs=30, lr=0.005)

model.save("trained_model.json")
print(f"\n✅ Точность: {history['accuracy'][-1]:.1%}")

# Тест
ping_path = Path("../ping/ping.py")
if ping_path.exists():
    code = ping_path.read_text()
    pred, conf = model.predict(code)
    print(f"\n🧪 ping.py: {pred} ({conf:.1%}) {'✅' if pred == 'hydra' else '❌'}")

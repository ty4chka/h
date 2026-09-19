"""
ФИНАЛЬНОЕ ОБУЧЕНИЕ НА ЧИСТЫХ ДАННЫХ
"""

from pathlib import Path
from model import MicroHydraModel
import random

# 1. Загружаем только чистые данные
training_dir = Path("training_data")
codes, labels = [], []
label_map = {"hikka_samples": 0, "mcub_samples": 1, "hydra_samples": 2}

# Ключевые слова для валидации
VALIDATION = {
    "hikka": ['from hikka', 'loader.Module', '@loader.tds'],
    "mcub": ['from core', '@loader.command'],
    "hydra": ['def setup', 'modules_help']
}

print("📂 ЗАГРУЗКА ЧИСТЫХ ДАННЫХ")
print("=" * 50)

for folder, label in label_map.items():
    folder_path = training_dir / folder
    folder_type = folder.replace('_samples', '')
    keywords = VALIDATION[folder_type]
    
    for f in folder_path.glob("*.py"):
        try:
            code = f.read_text(encoding='utf-8')
            if len(code) < 100:
                continue
            
            # Проверяем что файл соответствует типу
            matches = sum(1 for kw in keywords if kw in code)
            if matches == 0:
                continue
            
            codes.append(code)
            labels.append(label)
        except:
            pass

print(f"✅ Загружено: {len(codes)} чистых примеров")

# 2. Перемешиваем
combined = list(zip(codes, labels))
random.shuffle(combined)
codes, labels = zip(*combined)
codes, labels = list(codes), list(labels)

# 3. Обучаем с оптимальными параметрами
print("\n🎓 ОБУЧЕНИЕ")
print("=" * 50)

model = MicroHydraModel(vocab_size=1000, embedding_dim=32)

history = model.train(
    codes, 
    labels, 
    epochs=50,      # Больше эпох
    lr=0.005        # Оптимальный LR
)

# 4. Сохраняем
model.save("trained_model.json")
print(f"\n✅ Модель сохранена!")
print(f"   Точность: {history['accuracy'][-1]:.1%}")

# 5. Финальный тест
print("\n🧪 ФИНАЛЬНЫЙ ТЕСТ:")
ping_path = Path("../ping/ping.py")
if ping_path.exists():
    code = ping_path.read_text()
    pred, conf = model.predict(code)
    status = "✅" if pred == "hydra" else "❌"
    print(f"   ping.py: {pred} ({conf:.1%}) {status}")
else:
    print("   ❌ ping.py не найден")

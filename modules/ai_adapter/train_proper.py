"""
Правильное обучение с оптимальными параметрами
"""

import json
import random
from pathlib import Path
from model import MicroHydraModel

# 1. Загружаем ВСЕ данные
training_dir = Path("training_data")
codes, labels = [], []
label_map = {"hikka_samples": 0, "mcub_samples": 1, "hydra_samples": 2}

print("📂 ЗАГРУЗКА ВСЕХ ДАННЫХ")
print("=" * 50)

for folder, label in label_map.items():
    folder_path = training_dir / folder
    files = list(folder_path.glob("*.py"))
    print(f"{folder}: {len(files)} файлов")
    
    for f in files:
        try:
            code = f.read_text(encoding='utf-8')
            if len(code) > 50:
                codes.append(code)
                labels.append(label)
        except:
            pass

print(f"\n📊 ВСЕГО: {len(codes)} примеров")

# 2. Перемешиваем
combined = list(zip(codes, labels))
random.shuffle(combined)
codes, labels = zip(*combined)
codes, labels = list(codes), list(labels)

# 3. Создаём модель с правильными параметрами
print("\n🔄 Создание модели...")
model = MicroHydraModel(
    vocab_size=2000,   # Больше слов
    embedding_dim=48   # Шире эмбеддинг
)

# 4. ОБУЧЕНИЕ С ПРАВИЛЬНЫМ LR
print("\n🎓 ОБУЧЕНИЕ")
print("=" * 50)
print(f"LR: 0.003 (оптимально для {len(codes)} примеров)")
print(f"Эпохи: 60\n")

history = model.train(
    codes, 
    labels, 
    epochs=60, 
    lr=0.003  # 🔥 КЛЮЧЕВОЕ ИЗМЕНЕНИЕ!
)

# 5. Сохраняем
model.save("trained_model.json")
print(f"\n✅ Модель сохранена!")
print(f"   Лучшая точность: {max(history['accuracy']):.1%}")
print(f"   Финальная точность: {history['accuracy'][-1]:.1%}")

# 6. Тест на ping.py
print("\n🧪 ТЕСТ НА РЕАЛЬНОМ МОДУЛЕ:")
ping_path = Path("../ping/ping.py")
if ping_path.exists():
    code = ping_path.read_text()
    pred, conf = model.predict(code)
    print(f"   ping.py: {pred} ({conf:.1%})")
    print(f"   {'✅' if pred == 'hydra' else '❌'}")

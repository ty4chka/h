"""
ПОЛНЫЙ СБРОС И ПРАВИЛЬНОЕ ОБУЧЕНИЕ
"""
import json
import random
from pathlib import Path
from model import MicroHydraModel

# 1. Проверяем данные
training_dir = Path("training_data")
all_codes = []
all_labels = []

label_map = {"hikka_samples": 0, "mcub_samples": 1, "hydra_samples": 2}

print("📂 ЗАГРУЗКА ДАННЫХ")
print("=" * 40)

for folder, label in label_map.items():
    folder_path = training_dir / folder
    if folder_path.exists():
        files = list(folder_path.glob("*.py"))
        print(f"{folder}: {len(files)} файлов")
        
        for f in files:
            try:
                code = f.read_text(encoding='utf-8')
                if len(code) > 50:  # Минимальная длина
                    all_codes.append(code)
                    all_labels.append(label)
            except:
                pass

print(f"\n📊 ВСЕГО: {len(all_codes)} примеров")

if len(all_codes) < 10:
    print("❌ СЛИШКОМ МАЛО ДАННЫХ!")
    exit(1)

# 2. Перемешиваем
combined = list(zip(all_codes, all_labels))
random.shuffle(combined)
all_codes, all_labels = zip(*combined)

# 3. Создаём НОВУЮ модель (сброс весов)
print("\n🔄 Создание новой модели...")
model = MicroHydraModel(vocab_size=1000, embedding_dim=32)

# 4. Обучение с правильными параметрами
print("\n🎓 ОБУЧЕНИЕ")
print("=" * 40)

# Конвертируем в списки
codes_list = list(all_codes)
labels_list = list(all_labels)

history = model.train(
    codes_list, 
    labels_list, 
    epochs=30, 
    lr=0.02  # Выше learning rate
)

# 5. Сохраняем
model.save("trained_model.json")
print(f"\n✅ Модель сохранена")
print(f"   Лучшая точность: {max(history['accuracy']):.1%}")

# 6. Тест на примере
print("\n🧪 ТЕСТ:")
test_code = codes_list[0]
pred, conf = model.predict(test_code)
real = labels_list[0]
types = ["hikka", "mcub", "hydra"]
print(f"  Реальный: {types[real]}")
print(f"  Предсказано: {pred} ({conf:.1%})")

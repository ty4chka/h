"""
Model Trainer - Обучение модели на собранных данных
"""

import json
import random
import asyncio
from pathlib import Path
from typing import List, Tuple, Dict
from .model import MicroHydraModel
from .github_collector import GitHubCollector

class ModelTrainer:
    def __init__(self):
        self.model = MicroHydraModel()
        self.training_dir = Path(__file__).parent / "training_data"
        self.model_path = Path(__file__).parent / "trained_model.json"
    
    def _create_synthetic_data(self) -> Tuple[List[str], List[int]]:
        """Создаёт синтетические примеры если реальных мало"""
        codes = []
        labels = []
        
        # Hikka (label 0)
        hikka_tmpl = '''from hikka import loader

class {name}Mod(loader.Module):
    """{desc}"""
    async def {cmd}_cmd(self, message):
        await message.edit("{text}")
'''
        # MCUB (label 1)
        mcub_tmpl = '''from core import loader

@loader.command
async def {cmd}_cmd(message):
    """{desc}"""
    await message.answer("{text}")
'''
        # Hydra (label 2)
        hydra_tmpl = '''from telethon import events
from utils.misc import edit_or_reply

def setup(client):
    @client.on(events.NewMessage(pattern=r"\\.{cmd}"))
    async def {cmd}_handler(event):
        """{desc}"""
        await edit_or_reply(event, "{text}")

modules_help = {{"{name}": {{"{cmd}": "{desc}"}}}}
'''
        
        modules = [
            ("ping", "ping", "Pong!", "Проверка связи"),
            ("echo", "echo", "Hello!", "Эхо команда"),
            ("help", "help", "Список команд", "Помощь"),
            ("info", "info", "Информация", "О боте"),
            ("stats", "stats", "Статистика", "Статистика"),
        ]
        
        for name, cmd, text, desc in modules:
            codes.append(hikka_tmpl.format(name=name.capitalize(), cmd=cmd, text=text, desc=desc))
            labels.append(0)
            
            codes.append(mcub_tmpl.format(cmd=cmd, text=text, desc=desc))
            labels.append(1)
            
            codes.append(hydra_tmpl.format(cmd=cmd, text=text, name=name, desc=desc))
            labels.append(2)
        
        return codes, labels
    
    def load_training_data(self) -> Tuple[List[str], List[int]]:
        """Загружает все собранные данные"""
        codes = []
        labels = []
        
        label_map = {"hikka_samples": 0, "mcub_samples": 1, "hydra_samples": 2}
        
        for folder, label in label_map.items():
            folder_path = self.training_dir / folder
            if folder_path.exists():
                for py_file in folder_path.glob("*.py"):
                    try:
                        code = py_file.read_text(encoding='utf-8')
                        if len(code) > 100:
                            codes.append(code)
                            labels.append(label)
                    except:
                        pass
        
        # Если данных мало, добавляем синтетику
        if len(codes) < 30:
            print(f"  ⚠️ Мало данных ({len(codes)}), добавляю синтетику...")
            synth_codes, synth_labels = self._create_synthetic_data()
            codes.extend(synth_codes)
            labels.extend(synth_labels)
        
        return codes, labels
    
    def train(self, epochs: int = 30, lr: float = 0.01) -> Dict:
        """Обучает модель"""
        codes, labels = self.load_training_data()
        
        print(f"\n🎓 ОБУЧЕНИЕ МОДЕЛИ")
        print("="*40)
        print(f"  Примеров: {len(codes)}")
        print(f"  Эпох: {epochs}")
        print(f"  LR: {lr}\n")
        
        history = self.model.train(codes, labels, epochs=epochs, lr=lr)
        self.model.is_trained = True
        
        # Сохраняем
        self.model.save(str(self.model_path))
        print(f"\n✅ Модель сохранена: {self.model_path}")
        print(f"  Размер: {self.model_path.stat().st_size / 1024:.1f} КБ")
        print(f"  Точность: {history['accuracy'][-1]:.2%}")
        
        return history
    
    async def collect_and_train(self, collect: bool = True, epochs: int = 30) -> Dict:
        """Полный цикл: сбор + обучение"""
        print("🧠 HYDRA AI TRAINING PIPELINE\n" + "="*50)
        
        if collect:
            print("\n📥 ШАГ 1: Сбор модулей")
            collector = GitHubCollector(self.training_dir)
            await collector.collect_from_repos(max_files=100)
            await collector.close()
        
        print("\n📂 ШАГ 2: Загрузка данных")
        codes, labels = self.load_training_data()
        print(f"  Всего примеров: {len(codes)}")
        
        print("\n🎓 ШАГ 3: Обучение")
        history = self.train(epochs=epochs)
        
        print("\n✅ ГОТОВО!")
        return history
    
    def evaluate(self, test_code: str) -> Dict:
        """Оценивает один пример"""
        if not self.model.is_trained:
            return {"error": "Модель не обучена"}
        
        pred_class, confidence = self.model.predict(test_code)
        
        from .ast_analyzer import ModuleASTAnalyzer
        ast_result = ModuleASTAnalyzer(test_code).analyze()
        
        return {
            "predicted": pred_class,
            "confidence": confidence,
            "ast_type": ast_result.get("module_type", "unknown"),
            "match": pred_class == ast_result.get("module_type", "unknown")
        }


async def async_main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Hydra Model Trainer")
    parser.add_argument("--collect", action="store_true", help="Собрать модули")
    parser.add_argument("--train", action="store_true", help="Обучить модель")
    parser.add_argument("--full", action="store_true", help="Полный цикл")
    parser.add_argument("--epochs", type=int, default=30, help="Количество эпох")
    
    args = parser.parse_args()
    
    trainer = ModelTrainer()
    
    if args.full:
        await trainer.collect_and_train(collect=True, epochs=args.epochs)
    elif args.collect:
        collector = GitHubCollector(trainer.training_dir)
        await collector.collect_from_repos(max_files=100)
        await collector.close()
    elif args.train:
        trainer.train(epochs=args.epochs)
    else:
        parser.print_help()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

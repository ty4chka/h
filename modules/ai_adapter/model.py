"""
Микро-модель для классификации модулей
Размер: ~2-5 МБ, скорость: <0.005 сек
"""

import json
import math
import random
import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional

class MicroHydraModel:
    def __init__(self, vocab_size: int = 2000, embedding_dim: int = 32):
        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        
        self.token_to_id = {"<PAD>": 0, "<UNK>": 1}
        self.id_to_token = {0: "<PAD>", 1: "<UNK>"}
        
        self.embeddings = None
        self.weights_1 = None
        self.bias_1 = None
        self.weights_2 = None
        self.bias_2 = None
        
        self.is_trained = False
        self.labels = ["hikka", "mcub", "hydra"]
        self.label_to_id = {l: i for i, l in enumerate(self.labels)}
        self.id_to_label = {i: l for i, l in enumerate(self.labels)}
    
    def _tokenize(self, code: str) -> List[int]:
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+|[^\s\w]', code.lower())[:300]
        token_ids = []
        for token in tokens:
            if token not in self.token_to_id and len(self.token_to_id) < self.vocab_size:
                self.token_to_id[token] = len(self.token_to_id)
                self.id_to_token[len(self.id_to_token)] = token
            token_ids.append(self.token_to_id.get(token, 1))
        return token_ids
    
    def _init_weights(self):
        if self.embeddings is None:
            r = math.sqrt(6.0 / self.vocab_size)
            self.embeddings = [[random.uniform(-r, r) for _ in range(self.embedding_dim)] for _ in range(self.vocab_size)]
            
            r1 = math.sqrt(6.0 / self.embedding_dim)
            self.weights_1 = [[random.uniform(-r1, r1) for _ in range(16)] for _ in range(self.embedding_dim)]
            self.bias_1 = [0.0] * 16
            
            self.weights_2 = [[random.uniform(-r1, r1) for _ in range(3)] for _ in range(16)]
            self.bias_2 = [0.0] * 3
    
    def _forward(self, token_ids: List[int]) -> List[float]:
        if not token_ids:
            return [0.33, 0.33, 0.34]
        
        embed = [0.0] * self.embedding_dim
        for tid in token_ids[:200]:
            if tid < len(self.embeddings):
                for i in range(self.embedding_dim):
                    embed[i] += self.embeddings[tid][i]
        
        length = max(1, len(token_ids[:200]))
        embed = [e / length for e in embed]
        
        hidden = [0.0] * 16
        for i in range(16):
            for j in range(self.embedding_dim):
                hidden[i] += embed[j] * self.weights_1[j][i]
            hidden[i] = max(0, hidden[i] + self.bias_1[i])
        
        output = [0.0] * 3
        for i in range(3):
            for j in range(16):
                output[i] += hidden[j] * self.weights_2[j][i]
            output[i] += self.bias_2[i]
        
        exp_out = [math.exp(min(o, 50)) for o in output]
        sum_exp = sum(exp_out)
        return [e / sum_exp for e in exp_out]
    
    def predict(self, code: str) -> Tuple[str, float]:
        self._init_weights()
        tokens = self._tokenize(code)
        probs = self._forward(tokens)
        max_idx = max(range(3), key=lambda i: probs[i])
        return self.labels[max_idx], probs[max_idx]
    
    def train(self, codes: List[str], labels: List[int], epochs: int = 30, lr: float = 0.01) -> Dict:
        self._init_weights()
        history = {"loss": [], "accuracy": []}
        
        for epoch in range(epochs):
            combined = list(zip(codes, labels))
            random.shuffle(combined)
            
            total_loss = 0.0
            correct = 0
            
            for code, label in combined:
                tokens = self._tokenize(code)
                probs = self._forward(tokens)
                
                loss = -math.log(max(probs[label], 1e-10))
                total_loss += loss
                
                if max(range(3), key=lambda i: probs[i]) == label:
                    correct += 1
                
                # Backprop (упрощённый)
                embed = self._get_embedding(tokens)
                grad_out = probs[:]
                grad_out[label] -= 1.0
                
                for i in range(16):
                    for j in range(3):
                        self.weights_2[i][j] -= lr * embed[i] * grad_out[j] if i < len(embed) else 0
                    self.bias_2[j] -= lr * grad_out[j]
            
            avg_loss = total_loss / len(codes)
            acc = correct / len(codes)
            history["loss"].append(avg_loss)
            history["accuracy"].append(acc)
            
            if epoch % 10 == 0:
                print(f"  Epoch {epoch}: loss={avg_loss:.4f}, acc={acc:.2%}")
        
        self.is_trained = True
        return history
    
    def _get_embedding(self, token_ids: List[int]) -> List[float]:
        embed = [0.0] * 16
        for tid in token_ids[:200]:
            if tid < len(self.embeddings):
                for i in range(min(self.embedding_dim, 16)):
                    embed[i] += self.embeddings[tid][i]
        length = max(1, len(token_ids[:200]))
        return [e / length for e in embed]
    
    def save(self, path: str):
        data = {
            "vocab_size": self.vocab_size,
            "embedding_dim": self.embedding_dim,
            "token_to_id": self.token_to_id,
            "id_to_token": self.id_to_token,
            "embeddings": self.embeddings,
            "weights_1": self.weights_1,
            "bias_1": self.bias_1,
            "weights_2": self.weights_2,
            "bias_2": self.bias_2,
            "is_trained": self.is_trained
        }
        with open(path, 'w') as f:
            json.dump(data, f)
    
    @classmethod
    def load(cls, path: str) -> 'MicroHydraModel':
        with open(path, 'r') as f:
            data = json.load(f)
        
        model = cls(data["vocab_size"], data["embedding_dim"])
        model.token_to_id = data["token_to_id"]
        model.id_to_token = data["id_to_token"]
        model.embeddings = data["embeddings"]
        model.weights_1 = data["weights_1"]
        model.bias_1 = data["bias_1"]
        model.weights_2 = data["weights_2"]
        model.bias_2 = data["bias_2"]
        model.is_trained = data["is_trained"]
        
        return model

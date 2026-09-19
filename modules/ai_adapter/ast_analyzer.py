"""
AST анализатор для точного определения структуры модуля
"""

import ast
import re
from typing import Dict, List, Any, Optional

class ModuleASTAnalyzer:
    def __init__(self, code: str):
        self.code = code
        try:
            self.tree = ast.parse(code)
            self.error = None
        except SyntaxError as e:
            self.tree = None
            self.error = str(e)
    
    def analyze(self) -> Dict[str, Any]:
        if self.error:
            return {"error": self.error, "module_type": "unknown"}
        
        classes = self._analyze_classes()
        functions = self._analyze_functions()
        imports = self._analyze_imports()
        
        module_type = self._detect_type(classes, functions, imports)
        
        return {
            "module_type": module_type,
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "has_setup": any(f["name"] == "setup" for f in functions),
            "command_count": len([f for f in functions if f["name"].endswith("_cmd") or f["name"].endswith("_handler")])
        }
    
    def _analyze_classes(self) -> List[Dict]:
        classes = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "methods": [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                })
        return classes
    
    def _analyze_functions(self) -> List[Dict]:
        functions = []
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [self._get_decorator_name(d) for d in node.decorator_list]
                })
        return functions
    
    def _analyze_imports(self) -> List[str]:
        imports = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"from {module} import {alias.name}")
        return imports
    
    def _get_decorator_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "unknown"
    
    def _detect_type(self, classes: List, functions: List, imports: List) -> str:
        code_lower = self.code.lower()
        
        # Hikka/Heroku
        for cls in classes:
            if cls["name"].endswith("Mod"):
                return "hikka"
        if "hikka" in code_lower or "heroku" in code_lower:
            return "hikka"
        
        # MCUB
        if any("from core" in imp for imp in imports):
            return "mcub"
        if any("loader" in str(f) for f in functions):
            return "mcub"
        
        # Hydra
        if any(f["name"] == "setup" for f in functions):
            return "hydra"
        if "modules_help" in code_lower:
            return "hydra"
        
        return "unknown"

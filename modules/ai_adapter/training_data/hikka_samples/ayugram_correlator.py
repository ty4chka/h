#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Digital Persona Correlator
Module for correlating entities and merging them into personas using graph-based approach
"""

import networkx as nx
from typing import List, Dict, Any, Set, Tuple, Optional
import uuid
import logging
from datetime import datetime
import difflib
import re
from collections import defaultdict, Counter

# Настройка логирования
logger = logging.getLogger(__name__)

class PersonaCorrelator:
    """
    Класс для корреляции сущностей и объединения их в персоны
    Использует графовый подход для поиска связных компонентов
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        """
        Инициализация коррелятора
        
        Args:
            similarity_threshold (float): Порог схожести для username (0.0 - 1.0)
        """
        self.graph = nx.Graph()
        self.similarity_threshold = similarity_threshold
        self.personas = []
        self.stats = {
            'total_entities': 0,
            'edges_created': 0,
            'rules_triggered': defaultdict(int),
            'personas_created': 0
        }
        logger.info(f"PersonaCorrelator инициализирован с порогом схожести {similarity_threshold}")
    
    def correlate(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Основной метод корреляции сущностей и формирования персон
        
        Args:
            entities (List[Dict[str, Any]]): Список нормализованных сущностей
            
        Returns:
            List[Dict[str, Any]]: Список сформированных персон
        """
        if not entities:
            logger.warning("Получен пустой список сущностей для корреляции")
            return []
        
        logger.info(f"Начало корреляции {len(entities)} сущностей")
        self.stats['total_entities'] = len(entities)
        
        # Шаг 1: Создание узлов графа
        self._create_nodes(entities)
        
        # Шаг 2: Построение связей на основе правил
        self._build_connections(entities)
        
        # Шаг 3: Поиск связных компонентов
        self._find_personas(entities)
        
        # Шаг 4: Обогащение персон дополнительной информацией
        self._enrich_personas()
        
        logger.info(f"Корреляция завершена. Создано {len(self.personas)} персон")
        logger.info(f"Статистика срабатывания правил: {dict(self.stats['rules_triggered'])}")
        
        return self.personas
    
    def _create_nodes(self, entities: List[Dict[str, Any]]) -> None:
        """
        Создание узлов графа для каждой сущности
        
        Args:
            entities (List[Dict[str, Any]]): Список сущностей
        """
        self.graph.clear()
        
        for entity in entities:
            node_id = entity['id']
            self.graph.add_node(node_id, **entity)
        
        logger.debug(f"Создано {len(entities)} узлов графа")
    
    def _build_connections(self, entities: List[Dict[str, Any]]) -> None:
        """
        Построение связей между узлами на основе правил корреляции
        
        Args:
            entities (List[Dict[str, Any]]): Список сущностей
        """
        # Группировка сущностей по типу для эффективного поиска
        entities_by_type = self._group_by_type(entities)
        entities_by_value = self._group_by_value(entities)
        
        # НОВОЕ: Правило точного совпадения для всех типов сущностей
        self._apply_exact_match_rule(entities_by_value)
        
        # Правило 1: Полное совпадение по номеру телефона
        self._apply_phone_match_rule(entities_by_type.get('phone', []), entities_by_value)
        
        # Правило 2: Номер встречается внутри email
        self._apply_phone_in_email_rule(
            entities_by_type.get('phone', []),
            entities_by_type.get('email', [])
        )
        
        # Правило 3: Username содержит фамилию
        self._apply_username_contains_surname_rule(
            entities_by_type.get('username', []),
            entities_by_type.get('name', [])
        )
        
        # Правило 4: Email содержит фамилию
        self._apply_email_contains_surname_rule(
            entities_by_type.get('email', []),
            entities_by_type.get('name', [])
        )
        
        # Правило 5: Фамилия повторяется в нескольких строках
        self._apply_surname_repetition_rule(
            entities_by_type.get('name', []),
            entities
        )
        
        # Правило 6: Схожесть username ≥ 70%
        self._apply_username_similarity_rule(entities_by_type.get('username', []))
        
        # Правило 7: Совпадение имени + года рождения
        self._apply_name_and_year_rule(
            entities_by_type.get('name', []),
            entities_by_type.get('date', [])
        )
        
        # Дополнительная связь: сущности из одной строки
        self._apply_same_line_rule(entities)
        
        logger.info(f"Создано {self.stats['edges_created']} связей")
    
    def _group_by_type(self, entities: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """Группировка сущностей по типу"""
        groups = defaultdict(list)
        for entity in entities:
            groups[entity['type']].append(entity)
        return groups
    
    def _group_by_value(self, entities: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Группировка ID сущностей по значению"""
        groups = defaultdict(list)
        for entity in entities:
            groups[entity['value']].append(entity['id'])
        return groups
    
    # НОВОЕ: правило точного совпадения
    def _apply_exact_match_rule(self, entities_by_value: Dict[str, List[str]]) -> None:
        """
        Правило: точное совпадение значения (для всех типов сущностей)
        """
        rule_name = 'exact_match'
        for value, ids in entities_by_value.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        self.graph.add_edge(ids[i], ids[j], rule=rule_name)
                        self.stats['edges_created'] += 1
                        self.stats['rules_triggered'][rule_name] += 1
        if self.stats['rules_triggered'][rule_name]:
            logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_phone_match_rule(self, phones: List[Dict], entities_by_value: Dict) -> None:
        """
        Правило 1: Полное совпадение по номеру телефона
        """
        rule_name = 'phone_match'
        phone_values = defaultdict(list)
        
        # Группировка телефонов по значению
        for phone in phones:
            phone_values[phone['value']].append(phone['id'])
        
        # Связывание всех телефонов с одинаковым значением
        for value, ids in phone_values.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        self.graph.add_edge(ids[i], ids[j], rule=rule_name)
                        self.stats['edges_created'] += 1
                        self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_phone_in_email_rule(self, phones: List[Dict], emails: List[Dict]) -> None:
        """
        Правило 2: Номер телефона встречается внутри email
        """
        rule_name = 'phone_in_email'
        
        for phone in phones:
            phone_digits = re.sub(r'\D', '', phone['value'])
            if len(phone_digits) < 7:
                continue
            
            for email in emails:
                local_part = email['value'].split('@')[0]
                # Проверяем, содержит ли локальная часть email цифры из телефона
                if phone_digits in local_part or any(
                    phone_digits.endswith(part) for part in re.findall(r'\d+', local_part)
                ):
                    self.graph.add_edge(phone['id'], email['id'], rule=rule_name)
                    self.stats['edges_created'] += 1
                    self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_username_contains_surname_rule(self, usernames: List[Dict], names: List[Dict]) -> None:
        """
        Правило 3: Username содержит фамилию
        """
        rule_name = 'username_contains_surname'
        
        for name in names:
            name_parts = name.get('name_parts', {})
            surname = name_parts.get('last_name', '').lower()
            
            if not surname or len(surname) < 3:
                continue
            
            for username in usernames:
                username_value = username['value'].lower()
                
                # Проверка на вхождение фамилии в username
                if surname in username_value:
                    self.graph.add_edge(name['id'], username['id'], rule=rule_name)
                    self.stats['edges_created'] += 1
                    self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_email_contains_surname_rule(self, emails: List[Dict], names: List[Dict]) -> None:
        """
        Правило 4: Email содержит фамилию
        """
        rule_name = 'email_contains_surname'
        
        for name in names:
            name_parts = name.get('name_parts', {})
            surname = name_parts.get('last_name', '').lower()
            
            if not surname or len(surname) < 3:
                continue
            
            for email in emails:
                local_part = email['value'].split('@')[0].lower()
                
                # Проверка на вхождение фамилии в локальную часть email
                if surname in local_part:
                    self.graph.add_edge(name['id'], email['id'], rule=rule_name)
                    self.stats['edges_created'] += 1
                    self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_surname_repetition_rule(self, names: List[Dict], all_entities: List[Dict]) -> None:
        """
        Правило 5: Фамилия повторяется в нескольких строках
        Связывает сущности, у которых совпадает фамилия
        """
        rule_name = 'surname_repetition'
        
        # Группировка имен по фамилии
        surnames = defaultdict(list)
        for name in names:
            name_parts = name.get('name_parts', {})
            surname = name_parts.get('last_name', '').lower()
            if surname and len(surname) >= 3:
                surnames[surname].append(name['id'])
        
        # Связывание всех сущностей с одинаковой фамилией
        for surname, ids in surnames.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        self.graph.add_edge(ids[i], ids[j], rule=rule_name, surname=surname)
                        self.stats['edges_created'] += 1
                        self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_username_similarity_rule(self, usernames: List[Dict]) -> None:
        """
        Правило 6: Схожесть username ≥ 70%
        Использует difflib для сравнения строк
        """
        rule_name = 'username_similarity'
        
        for i in range(len(usernames)):
            for j in range(i + 1, len(usernames)):
                username1 = usernames[i]['value'].lower()
                username2 = usernames[j]['value'].lower()
                
                # Пропускаем слишком короткие имена
                if len(username1) < 4 or len(username2) < 4:
                    continue
                
                # Расчет схожести
                similarity = difflib.SequenceMatcher(None, username1, username2).ratio()
                
                if similarity >= self.similarity_threshold:
                    self.graph.add_edge(
                        usernames[i]['id'], 
                        usernames[j]['id'], 
                        rule=rule_name,
                        similarity=similarity
                    )
                    self.stats['edges_created'] += 1
                    self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_name_and_year_rule(self, names: List[Dict], dates: List[Dict]) -> None:
        """
        Правило 7: Совпадение имени + года рождения
        """
        rule_name = 'name_and_year'
        
        # Извлечение годов из дат
        years_by_entity = {}
        for date in dates:
            date_info = date.get('date_info', {})
            year = date_info.get('year')
            if year:
                years_by_entity[date['id']] = year
        
        # Группировка имен по имени (без фамилии)
        first_names = defaultdict(list)
        for name in names:
            name_parts = name.get('name_parts', {})
            first_name = name_parts.get('first_name', '').lower()
            if first_name and len(first_name) >= 2:
                first_names[first_name].append(name['id'])
        
        # Поиск связей между именами и датами
        for first_name, name_ids in first_names.items():
            for name_id in name_ids:
                # Ищем даты, связанные с этим именем
                for date_id, year in years_by_entity.items():
                    # Проверяем, есть ли уже связь через другие правила
                    if not self.graph.has_edge(name_id, date_id):
                        # Проверяем, не слишком ли старый/новый год
                        if 1900 <= year <= datetime.now().year:
                            self.graph.add_edge(name_id, date_id, rule=rule_name, year=year)
                            self.stats['edges_created'] += 1
                            self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _apply_same_line_rule(self, entities: List[Dict]) -> None:
        """
        Дополнительное правило: сущности из одной строки связаны
        """
        rule_name = 'same_line'
        
        # Группировка сущностей по номеру строки
        line_groups = defaultdict(list)
        for entity in entities:
            line_num = entity.get('line')
            if line_num:
                line_groups[line_num].append(entity['id'])
        
        # Связывание всех сущностей из одной строки
        for line_num, ids in line_groups.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        if not self.graph.has_edge(ids[i], ids[j]):
                            self.graph.add_edge(ids[i], ids[j], rule=rule_name, line=line_num)
                            self.stats['edges_created'] += 1
                            self.stats['rules_triggered'][rule_name] += 1
        
        logger.debug(f"Правило {rule_name}: создано связей - {self.stats['rules_triggered'][rule_name]}")
    
    def _find_personas(self, entities: List[Dict]) -> None:
        """
        Поиск связных компонентов в графе и формирование персон
        
        Args:
            entities (List[Dict]): Список всех сущностей
        """
        # Словарь для быстрого доступа к сущностям по ID
        entities_dict = {e['id']: e for e in entities}
        
        # Поиск связных компонентов
        components = list(nx.connected_components(self.graph))
        
        self.personas = []
        
        for component in components:
            # Сбор всех сущностей в компоненте
            persona_entities = [entities_dict[node_id] for node_id in component if node_id in entities_dict]
            
            if not persona_entities:
                continue
            
            # Создание персоны
            persona = self._create_persona(persona_entities)
            self.personas.append(persona)
        
        # Добавление одиночных сущностей как отдельных персон
        all_connected = set().union(*components) if components else set()
        isolated = set(entities_dict.keys()) - all_connected
        
        for entity_id in isolated:
            persona = self._create_persona([entities_dict[entity_id]])
            self.personas.append(persona)
        
        self.stats['personas_created'] = len(self.personas)
        logger.info(f"Найдено {len(components)} связных компонентов и {len(isolated)} изолированных сущностей")
    
    def _create_persona(self, entities: List[Dict]) -> Dict[str, Any]:
        """
        Создание персоны из списка связанных сущностей
        
        Args:
            entities (List[Dict]): Список сущностей
            
        Returns:
            Dict[str, Any]: Сформированная персона
        """
        # Сбор всех уникальных значений по типам
        emails = set()
        phones = set()
        usernames = set()
        names = []
        dates = set()
        
        for entity in entities:
            entity_type = entity['type']
            value = entity['value']
            
            if entity_type == 'email':
                emails.add(value)
            elif entity_type == 'phone':
                phones.add(value)
            elif entity_type == 'username':
                usernames.add(value)
            elif entity_type == 'name':
                names.append(value)
            elif entity_type == 'date':
                dates.add(value)
        
        # Определение наиболее полного ФИО
        full_name = self._determine_best_name(names)
        
        # Создание персоны
        persona = {
            'id': str(uuid.uuid4()),
            'emails': sorted(list(emails)),
            'phones': sorted(list(phones)),
            'usernames': sorted(list(usernames)),
            'full_name': full_name,
            'dates': sorted(list(dates)),
            'entity_count': len(entities),
            'entities': [e['id'] for e in entities],  # Ссылки на исходные сущности
            'created_at': datetime.now().isoformat()
        }
        
        return persona
    
    def _determine_best_name(self, names: List[str]) -> Optional[str]:
        """
        Определение наиболее полного ФИО из списка
        
        Args:
            names (List[str]): Список имен
            
        Returns:
            Optional[str]: Наиболее полное имя
        """
        if not names:
            return None
        
        # Сортировка по длине (более длинные имена вероятно более полные)
        names.sort(key=len, reverse=True)
        
        # Выбор самого длинного имени
        best_name = names[0]
        
        # Проверка, содержит ли оно как минимум 2 части
        if len(best_name.split()) >= 2:
            return best_name
        
        # Если нет, ищем имя с минимум 2 частями
        for name in names:
            if len(name.split()) >= 2:
                return name
        
        # Если ничего не найдено, возвращаем первое
        return names[0]
    
    def _enrich_personas(self) -> None:
        """
        Обогащение персон дополнительной информацией
        """
        for persona in self.personas:
            # Добавление статистики по персоне
            persona['stats'] = {
                'total_entities': persona['entity_count'],
                'unique_emails': len(persona['emails']),
                'unique_phones': len(persona['phones']),
                'unique_usernames': len(persona['usernames']),
                'unique_dates': len(persona['dates'])
            }
            
            # Добавление информации о связях в графе
            entity_ids = persona['entities']
            persona_edges = []
            
            for u, v, data in self.graph.edges(data=True):
                if u in entity_ids and v in entity_ids:
                    persona_edges.append({
                        'from': u,
                        'to': v,
                        'rule': data.get('rule', 'unknown')
                    })
            
            persona['connections'] = persona_edges
            persona['connection_count'] = len(persona_edges)
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Получение статистики по графу
        
        Returns:
            Dict[str, Any]: Статистика графа
        """
        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'density': nx.density(self.graph),
            'components': nx.number_connected_components(self.graph)
        }
    
    def get_persona_by_id(self, persona_id: str) -> Optional[Dict]:
        """
        Получение персоны по ID
        
        Args:
            persona_id (str): ID персоны
            
        Returns:
            Optional[Dict]: Персона или None
        """
        for persona in self.personas:
            if persona['id'] == persona_id:
                return persona
        return None
    
    def find_similar_personas(self, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Поиск похожих персон (может использоваться для ручного объединения)
        
        Args:
            threshold (float): Порог схожести
            
        Returns:
            List[Tuple[str, str, float]]: Список пар похожих персон с коэффициентом схожести
        """
        similar_pairs = []
        
        for i in range(len(self.personas)):
            for j in range(i + 1, len(self.personas)):
                similarity = self._calculate_persona_similarity(
                    self.personas[i], 
                    self.personas[j]
                )
                
                if similarity >= threshold:
                    similar_pairs.append((
                        self.personas[i]['id'],
                        self.personas[j]['id'],
                        similarity
                    ))
        
        return similar_pairs
    
    def _calculate_persona_similarity(self, persona1: Dict, persona2: Dict) -> float:
        """
        Расчет схожести между двумя персонами
        
        Args:
            persona1 (Dict): Первая персона
            persona2 (Dict): Вторая персона
            
        Returns:
            float: Коэффициент схожести (0-1)
        """
        scores = []
        weights = {
            'email': 0.3,
            'phone': 0.3,
            'username': 0.2,
            'name': 0.2
        }
        
        # Сравнение email
        if persona1['emails'] and persona2['emails']:
            common_emails = set(persona1['emails']) & set(persona2['emails'])
            if common_emails:
                scores.append(weights['email'])
        
        # Сравнение телефонов
        if persona1['phones'] and persona2['phones']:
            common_phones = set(persona1['phones']) & set(persona2['phones'])
            if common_phones:
                scores.append(weights['phone'])
        
        # Сравнение username
        if persona1['usernames'] and persona2['usernames']:
            for u1 in persona1['usernames']:
                for u2 in persona2['usernames']:
                    similarity = difflib.SequenceMatcher(None, u1.lower(), u2.lower()).ratio()
                    if similarity >= 0.8:
                        scores.append(weights['username'] * similarity)
                        break
        
        # Сравнение имен
        if persona1['full_name'] and persona2['full_name']:
            name_similarity = difflib.SequenceMatcher(
                None, 
                persona1['full_name'].lower(), 
                persona2['full_name'].lower()
            ).ratio()
            if name_similarity >= 0.6:
                scores.append(weights['name'] * name_similarity)
        
        return sum(scores) if scores else 0.0
    
    def merge_personas(self, persona_ids: List[str]) -> Optional[Dict]:
        """
        Ручное объединение нескольких персон в одну
        
        Args:
            persona_ids (List[str]): Список ID персон для объединения
            
        Returns:
            Optional[Dict]: Объединенная персона или None
        """
        personas_to_merge = []
        remaining_personas = []
        
        for persona in self.personas:
            if persona['id'] in persona_ids:
                personas_to_merge.append(persona)
            else:
                remaining_personas.append(persona)
        
        if len(personas_to_merge) < 2:
            logger.warning("Недостаточно персон для объединения")
            return None
        
        # Объединение всех сущностей
        all_entities = []
        for persona in personas_to_merge:
            all_entities.extend(persona['entities'])
        
        # Создание новой персоны
        merged_persona = self._create_persona(all_entities)
        
        # Обновление списка персон
        self.personas = remaining_personas + [merged_persona]
        
        logger.info(f"Объединены персоны {persona_ids} в {merged_persona['id']}")
        
        return merged_persona
    
    def get_correlation_rules_stats(self) -> Dict[str, int]:
        """
        Получение статистики по сработавшим правилам
        
        Returns:
            Dict[str, int]: Статистика правил
        """
        return dict(self.stats['rules_triggered'])


# Пример использования
if __name__ == "__main__":
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO)
    
    # Создание коррелятора
    correlator = PersonaCorrelator(similarity_threshold=0.7)
    
    # Тестовые данные (эмуляция вывода из normalizer.py)
    test_entities = [
        # Персона 1: Иван Петров
        {'id': '1', 'type': 'name', 'value': 'Иван Петров', 'name_parts': {'last_name': 'Петров', 'first_name': 'Иван'}, 'line': 1},
        {'id': '2', 'type': 'email', 'value': 'ivan.petrov@email.com', 'line': 1},
        {'id': '3', 'type': 'phone', 'value': '+79001234567', 'line': 2},
        {'id': '4', 'type': 'username', 'value': 'ivan_petrov', 'line': 3},
        {'id': '5', 'type': 'date', 'value': '1985-05-15', 'date_info': {'year': 1985}, 'line': 4},
        
        # Персона 2: Петр Иванов (связан через фамилию)
        {'id': '6', 'type': 'name', 'value': 'Петр Иванов', 'name_parts': {'last_name': 'Иванов', 'first_name': 'Петр'}, 'line': 5},
        {'id': '7', 'type': 'email', 'value': 'petr.ivanov@mail.ru', 'line': 5},
        
        # Персона 3: John Smith (английское имя)
        {'id': '8', 'type': 'name', 'value': 'John Smith', 'name_parts': {'last_name': 'Smith', 'first_name': 'John'}, 'line': 6},
        {'id': '9', 'type': 'email', 'value': 'john.smith@gmail.com', 'line': 6},
        {'id': '10', 'type': 'username', 'value': 'john_smith_1980', 'line': 7},
        
        # Дополнительные данные для проверки правил
        {'id': '11', 'type': 'phone', 'value': '+79001234567', 'line': 8},  # Дубликат телефона Ивана
        {'id': '12', 'type': 'username', 'value': 'john_smith_1980', 'line': 9},  # Дубликат username
    ]
    
    # Корреляция
    personas = correlator.correlate(test_entities)
    
    # Вывод результатов
    print(f"Создано персон: {len(personas)}")
    print(f"\nСтатистика графа: {correlator.get_graph_stats()}")
    print(f"\nСрабатывания правил: {correlator.get_correlation_rules_stats()}")
    
    print("\nСформированные персоны:")
    for i, persona in enumerate(personas, 1):
        print(f"\n--- Персона {i} (ID: {persona['id'][:8]}) ---")
        print(f"  ФИО: {persona['full_name']}")
        print(f"  Email: {', '.join(persona['emails'])}")
        print(f"  Телефоны: {', '.join(persona['phones'])}")
        print(f"  Username: {', '.join(persona['usernames'])}")
        print(f"  Даты: {', '.join(persona['dates'])}")
        print(f"  Всего сущностей: {persona['entity_count']}")
        print(f"  Связей: {persona['connection_count']}")
    
    # Поиск похожих персон
    similar = correlator.find_similar_personas(threshold=0.3)
    if similar:
        print(f"\nПохожие персоны:")
        for p1, p2, sim in similar:
            print(f"  {p1[:8]} - {p2[:8]}: схожесть {sim:.2f}")

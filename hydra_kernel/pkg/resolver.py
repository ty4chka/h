"""L3 — resolver: топологическая сортировка модулей по зависимостям."""

from __future__ import annotations

from typing import Dict, List

from .manifest import Manifest


class CyclicDependency(Exception):
    pass


def resolve(manifests: Dict[str, Manifest]) -> List[str]:
    """Возвращает порядок загрузки: зависимости раньше зависимых.

    Алгоритм Кана. Цикл -> CyclicDependency с именами участников.
    """
    indeg: Dict[str, int] = {name: 0 for name in manifests}
    dependents: Dict[str, List[str]] = {name: [] for name in manifests}

    for name, man in manifests.items():
        for req in man.requires:
            if req in manifests:
                indeg[name] += 1
                dependents[req].append(name)

    queue = sorted(n for n, d in indeg.items() if d == 0)
    order: List[str] = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in sorted(dependents[cur]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
        queue.sort()

    if len(order) != len(manifests):
        cyclic = sorted(set(manifests) - set(order))
        raise CyclicDependency(f"циклическая зависимость: {', '.join(cyclic)}")
    return order

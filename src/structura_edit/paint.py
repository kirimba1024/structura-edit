from itertools import product
from math import ceil, floor, isfinite

from .condition import Condition
from .picking import EMPTY


MAX_STROKE_POINTS = 4096


def segment_distance_squared(point, start, stop):
    delta = tuple(b - a for a, b in zip(start, stop))
    length = sum(d * d for d in delta)
    t = max(0, min(1, sum((p - a) * d for p, a, d in zip(point, start, delta)) / length)) if length else 0
    return sum((p - a - t * d) ** 2 for p, a, d in zip(point, start, delta))


def segment_candidates(selection, start, stop, radius):
    lower = tuple(max(lo, floor(min(a, b) - radius - 0.5)) for a, b, lo in zip(start, stop, selection.lower))
    upper = tuple(min(hi, ceil(max(a, b) + radius - 0.5) + 1) for a, b, hi in zip(start, stop, selection.upper))
    if any(lo >= hi for lo, hi in zip(lower, upper)):
        return
    delta = tuple(b - a for a, b in zip(start, stop))
    axis = max(range(3), key=lambda i: abs(delta[i]))
    if not delta[axis]:
        yield from product(*(range(lo, hi) for lo, hi in zip(lower, upper)))
        return
    for coordinate in range(lower[axis], upper[axis]):
        ends = tuple((coordinate + 0.5 + sign * radius - start[axis]) / delta[axis] for sign in (-1, 1))
        first, last = max(0, min(ends)), min(1, max(ends))
        if first > last:
            continue
        bounds = []
        for i, (lo, hi) in enumerate(zip(lower, upper)):
            if i == axis:
                bounds.append(range(coordinate, coordinate + 1))
            else:
                a, b = start[i] + first * delta[i], start[i] + last * delta[i]
                bounds.append(range(max(lo, floor(min(a, b) - radius - 0.5)),
                                    min(hi, ceil(max(a, b) + radius - 0.5) + 1)))
        yield from product(*bounds)


def paint_stroke(session, selection, points, target, radius=1, condition=None):
    session._check_selection(selection)
    if not isinstance(radius, (int, float)) or isinstance(radius, bool) or not isfinite(radius) or not 0 < radius <= 16:
        raise ValueError("Brush radius must be greater than zero and at most 16")
    if not points or len(points) > MAX_STROKE_POINTS:
        raise ValueError("Stroke exceeds 4096 samples; use a shorter stroke")
    if condition is not None and not isinstance(condition, Condition):
        condition = Condition("materials", (condition,)) if condition else None
    selected, previous, work = set(), None, 0
    for sample in points:
        if sample is None:
            previous = None
            continue
        sample = tuple(sample)
        if len(sample) != 3 or any(not isfinite(v) for v in sample):
            raise ValueError("Brush points need three finite coordinates")
        start = previous or sample
        previous = sample
        for point in segment_candidates(selection, start, sample, radius):
            work += 1
            if work > session.operation_limit * 8:
                raise ValueError("Stroke exceeds the sampling budget; use a smaller radius or shorter stroke")
            if point in selected or point not in selection:
                continue
            center = tuple(value + 0.5 for value in point)
            if segment_distance_squared(center, start, sample) > radius * radius:
                continue
            session._check_destination(point)
            state = session.state_at(point)
            if not state or state.split("[", 1)[0] in EMPTY or (condition and not condition.at(session, point)):
                continue
            selected.add(point)
            if len(selected) > session.operation_limit:
                raise ValueError("Stroke exceeds the changed-cell budget")
    return session._change(sorted(selected), target, "Paint stroke")

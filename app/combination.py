"""AI level 2: readings where no single variable is odd but the combination is.

anomalies.py looks at one variable at a time and trend.py at one variable over time. Both miss the
same thing, and it is not an oversight in either: a reading can have every value inside what that
pond normally does and still be one that pond never produces.

The case is physical, not a curiosity. In a pond where temperature and pH move together — midday sun
warms the water and the algae raise the pH with it — cold water at 12 °C is ordinary and a pH of
7.5 is ordinary, but the two together never happen, because this pond's high pH comes from the
midday sun and midday water is not at 12 °C. That it happened means something other than the daily
cycle is moving the pH, and that is worth a look. Variable by variable, the reading passes.

Method: the Mahalanobis distance of the new reading to the cloud of previous ones. It is the
distance that counts the *shape* of the cloud, so a point off the relationship between the variables
comes out far even when each coordinate is close. Under normal readings the squared distance follows
a chi-squared with as many degrees of freedom as variables, which is where the cutoffs come from.

The centre is each column's median and not its mean, for the same reason the other modules use
medians: readings taken with the sensor out of the water stay in the history.

## The floor on the spread, which is the sensor's resolution

Each variable's variance is floored at its resolution squared, and it took a failing test to find
the second reason why. The first is arithmetic: without something on the diagonal, the matrix of a
pond whose two variables move almost identically has no inverse and there is nothing to divide by.

The second is that this distance is *hypersensitive* to a cloud with no noise in it. If the readings
fall exactly on a curve — temperature and pH tied by the daily cycle with nothing else moving them —
then a point a thousandth off that curve comes out enormously far, and the service would report an
anomaly for a reading that follows the pattern as closely as the instrument can measure. Measured on
a noiseless test pond: distance 3.61 against a cutoff of 3.04, for a pH four thousandths off.

Flooring at the resolution answers both at once and says something true: a deviation smaller than
what the sensor can distinguish is not a deviation. It is the same idea anomalies.py already applies
to a pond whose readings never moved, which is why the number comes from the same place —
`Variable.resolution`.

Without a floor the arithmetic is exact and useless, so a degenerate cloud comes back as "no answer"
rather than as a number nobody should trust.

No numpy. Three variables mean a 3x3 system, and Gaussian elimination for that is fifteen lines —
cheaper than making the whole service carry a dependency of a hundred megabytes for it.
"""

from dataclasses import dataclass
from statistics import median

from app.anomalies import VARIABLES, fmt

MIN_HISTORY = 20
"""
Estimating the shape of a cloud takes many more rows than the algebra's bare minimum of one more
than the number of variables. With fewer than this the covariance is mostly noise, and a cloud
whose shape is noise calls anything unusual.
"""

WINDOW = 200
"""Only the recent ones: the relationship between the variables of a pond changes with the season."""

CUTOFF = {1: 2.576, 2: 3.035, 3: 3.368}
"""
Mahalanobis distance of a normal reading, at the 1 % tail of the chi-squared for that many degrees
of freedom. One in a hundred normal readings crosses it by chance.

Written down rather than computed so the service does not have to carry scipy for three numbers.
"""

@dataclass(frozen=True)
class Combination:
    variables: tuple[str, ...]
    values: tuple[float, ...]
    distance: float
    cutoff: float
    message: str


def solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """`matrix · x = vector` by Gaussian elimination with partial pivoting. None if it is singular."""
    n = len(vector)
    rows = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for r in range(column + 1, n):
            factor = rows[r][column] / rows[column][column]
            for c in range(column, n + 1):
                rows[r][c] -= factor * rows[column][c]
    answer = [0.0] * n
    for r in reversed(range(n)):
        total = rows[r][n] - sum(rows[r][c] * answer[c] for c in range(r + 1, n))
        answer[r] = total / rows[r][r]
    return answer


def distance(point: list[float], cloud: list[list[float]],
             floors: list[float] | None = None) -> float | None:
    """
    How far the point is from the cloud, counting its shape. None when the cloud is too small.

    `floors` is the smallest spread each column can have, normally the sensor's resolution. Without
    it the arithmetic is exact and useless: see the note at the top of the module.
    """
    rows, columns = len(cloud), len(point)
    if rows < columns + 1:
        return None
    floors = floors or [0.0] * columns

    centre = [median([row[c] for row in cloud]) for c in range(columns)]
    centred = [[row[c] - centre[c] for c in range(columns)] for row in cloud]
    covariance = [[sum(r[i] * r[j] for r in centred) / (rows - 1) for j in range(columns)]
                  for i in range(columns)]

    for i in range(columns):
        covariance[i][i] = max(covariance[i][i], floors[i] ** 2) + floors[i] ** 2
    if sum(covariance[i][i] for i in range(columns)) <= 0:
        return None  # nothing moved and no resolution given: no shape to measure against

    delta = [point[c] - centre[c] for c in range(columns)]
    weighted = solve(covariance, delta)
    if weighted is None:
        return None
    squared = sum(d * w for d, w in zip(delta, weighted))
    # A negative only comes from rounding when the point sits almost on the centre
    return max(squared, 0.0) ** 0.5


def cutoff_for(columns: int) -> float:
    return CUTOFF.get(columns, CUTOFF[3])


def in_sentence(label: str) -> str:
    """
    A variable's label in the middle of a sentence: "Temperatura" -> "temperatura", "pH" -> "pH".

    Lowercasing the lot would read "ph", and pH is chemical notation rather than a word — written
    in lower case it is simply wrong, and it is the kind of detail that makes a caretaker trust the
    message less. A label with capitals after the first letter is left exactly as it is.
    """
    return label.lower() if label[1:].islower() else label


def evaluate(readings: list[dict]) -> Combination | None:
    """
    Judges the newest reading against the shape of the ones before it.

    Only readings carrying *every* variable count, and that is deliberate: filling a gap with the
    column's average would invent a combination nobody measured, and the combination is the whole
    point here. A pond where the caretaker measures temperature daily and oxygen weekly simply gets
    no answer from this module, which is the honest outcome.
    """
    readings = sorted(readings, key=lambda r: r["registrado_en"])
    *previous, newest = readings

    columns = tuple(v for v in VARIABLES if newest.get(v) is not None)
    if len(columns) < 2:
        return None
    cloud = [[r[v] for v in columns] for r in previous
             if all(r.get(v) is not None for v in columns)]
    if len(cloud) < MIN_HISTORY:
        return None

    point = [newest[v] for v in columns]
    far = distance(point, cloud, [VARIABLES[v].resolution for v in columns])
    if far is None:
        return None
    limit = cutoff_for(len(columns))
    if far <= limit:
        return None

    described = ", ".join(f"{in_sentence(VARIABLES[v].label)} {fmt(value)}{VARIABLES[v].unit}"
                          for v, value in zip(columns, point))
    return Combination(
        columns, tuple(point), round(far, 2), limit,
        f"Esta combinación no se había visto en el estanque: {described}. "
        f"Cada valor por separado puede estar en lo normal; juntos, no se parecen a nada "
        f"de lo medido antes.")

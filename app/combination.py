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

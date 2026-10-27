import math
import random
from datetime import datetime, timedelta, timezone

from app.anomalies import check as anomaly_check
from app.anomalies import VARIABLES
from app.combination import MIN_HISTORY, cutoff_for, distance, evaluate, solve

FLOORS = [VARIABLES["temp_c"].resolution, VARIABLES["ph"].resolution]

START = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)


def coupled(n=40, seed=7):
    """
    A pond where temperature and pH move together, over the daily cycle.

    Not an invention of the example: at midday the water warms and the algae consume CO2, and both
    push the pH up. So in this pond cold water comes with low pH and warm water with high pH, and
    never the other way round.

    It has to be a cycle and not a rising ramp. On a ramp from 12 to 17 °C, a reading of 12.3 at the
    end is genuinely surprising and anomalies.py flags it — correctly — which would make the test
    below pass for the wrong reason. On a cycle, 12.2 °C happens every night and 7.52 pH every
    noon, so each value on its own is unremarkable and only the pairing is new. That is the case
    this module is for.
    """
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        phase = math.sin(i * math.pi / 4)  # eight readings per cycle, six hours apart
        rows.append({
            "registrado_en": START + timedelta(hours=6 * i),
            "temp_c": round(14.5 + 2.5 * phase + rng.uniform(-0.1, 0.1), 2),
            "ph": round(7.2 + 0.35 * phase + rng.uniform(-0.02, 0.02), 3),
        })
    return rows


def with_newest(history, **values):
    newest = {"registrado_en": history[-1]["registrado_en"] + timedelta(hours=6)}
    newest.update(values)
    return history + [newest]


# ---------- the arithmetic, since there is no numpy to lean on ----------

def test_solve_returns_the_answer_of_a_small_system():
    answer = solve([[4.0, 1.0], [1.0, 3.0]], [1.0, 2.0])
    assert answer is not None
    assert round(4 * answer[0] + answer[1], 9) == 1.0
    assert round(answer[0] + 3 * answer[1], 9) == 2.0


def test_solve_says_no_on_a_singular_system():
    assert solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]) is None


def test_distance_of_the_centre_is_about_zero():
    cloud = [[12.0 + i * 0.1, 7.0 + i * 0.01] for i in range(30)]
    centre = [cloud[15][0], cloud[15][1]]
    far = distance(centre, cloud, FLOORS)
    assert far is not None and far < 0.5


def test_distance_needs_more_rows_than_variables():
    assert distance([12.0, 7.0, 9.0], [[12.0, 7.0, 9.0], [13.0, 7.1, 8.9], [12.5, 7.05, 9.1]]) is None


def test_distance_survives_two_variables_that_move_identically():
    # No inverse without a floor on the diagonal, and the whole thing would raise instead of answer
    column = [9.0 + i * 0.05 for i in range(20)]
    cloud = [[x, x] for x in column]
    far = distance([9.5, 9.5], cloud, FLOORS)
    assert far is not None and far == far  # not NaN


def test_without_a_floor_a_degenerate_cloud_gives_no_answer():
    """
    Readings that fall exactly on a curve, with no sensor noise, carry no usable shape. Answering a
    number there would mean reporting an anomaly for a reading off the curve by less than the
    instrument can measure: measured, distance 3.61 against a cutoff of 3.04 for four thousandths
    of pH. No answer is the right answer.
    """
    column = [9.0 + i * 0.05 for i in range(20)]
    assert distance([9.5, 9.5], [[x, x] for x in column]) is None


def test_a_pond_that_never_moved_gives_no_answer():
    assert distance([12.0, 7.0], [[12.0, 7.0]] * 30) is None


# ---------- what no single variable shows ----------

def test_cold_water_with_high_ph_is_caught_while_each_value_passes():
    """
    The claim this module is built on, with the other detector run on the same data to prove it.

    12.2 °C is an ordinary temperature for this pond and 7.52 an ordinary pH — the first happens
    every night and the second every noon. What never happened is the two together, because this
    pond's high pH comes from the midday sun and midday water is not at 12 °C.
    """
    history = coupled()
    readings = with_newest(history, temp_c=12.2, ph=7.52)

    # Variable by variable, the reading passes: anomalies.py has nothing to say about either
    for variable in ("temp_c", "ph"):
        values = [r[variable] for r in history]
        assert anomaly_check(variable, values, readings[-1][variable]) is None

    found = evaluate(readings)
    assert found is not None
    assert found.distance > found.cutoff
    assert found.variables == ("temp_c", "ph")
    assert "no se había visto" in found.message


def test_a_reading_that_follows_the_pattern_passes():
    # Warm water with high pH: exactly what this pond does every day at noon
    assert evaluate(with_newest(coupled(), temp_c=16.9, ph=7.54)) is None


def test_a_reading_in_the_middle_of_the_pattern_passes():
    assert evaluate(with_newest(coupled(), temp_c=14.5, ph=7.2)) is None


# ---------- when it keeps quiet ----------

def test_too_little_history_gives_no_answer():
    assert evaluate(with_newest(coupled(n=MIN_HISTORY - 1), temp_c=12.2, ph=7.52)) is None


def test_a_single_variable_is_not_a_combination():
    history = [{"registrado_en": START + timedelta(hours=6 * i), "temp_c": 12.0 + i * 0.05}
               for i in range(30)]
    assert evaluate(with_newest(history, temp_c=18.0)) is None


def test_an_incomplete_reading_gives_no_answer():
    """
    Filling the gap with the column's average would invent a combination nobody measured, and the
    combination is the whole point. No answer is the honest outcome.
    """
    history = coupled()
    readings = with_newest(history, temp_c=12.3)  # no pH
    assert evaluate(readings) is None


def test_history_rows_missing_a_variable_are_left_out():
    history = coupled()
    for row in history[:30]:
        row.pop("ph")
    # Only ten complete rows are left, below the minimum
    assert evaluate(with_newest(history, temp_c=12.2, ph=7.52)) is None


# ---------- the cutoffs ----------

def test_the_cutoff_grows_with_the_number_of_variables():
    assert cutoff_for(1) < cutoff_for(2) < cutoff_for(3)


def test_more_variables_than_expected_fall_back_to_the_last_cutoff():
    assert cutoff_for(9) == cutoff_for(3)

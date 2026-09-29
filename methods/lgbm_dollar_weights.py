"""lgbm.py, but every bucket weighted fully by dollars (alpha = 1).

lgbm.py gives construction and fabrication a lower alpha, which makes them care about
% error more than dollars. The scoreboard judges dollars, so this tests alpha = 1 everywhere.
"""
from methods import lgbm


def fit_predict(train, test):
    original = lgbm.VALUE_ALPHA
    lgbm.VALUE_ALPHA = {bucket: 1.0 for bucket in original}
    try:
        return lgbm.fit_predict(train, test)
    finally:
        lgbm.VALUE_ALPHA = original

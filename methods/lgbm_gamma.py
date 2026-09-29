"""LightGBM with a gamma objective on raw dollars - predicts the average price, not the median.

Same features, weights and tuned settings as lgbm.py. The median is right for one tank but
runs low when added up across many tanks; the average should not.
"""
import numpy as np
import pandas as pd

from prepare import FEATURES, PRICE
from methods.lgbm import PARAMS, training_rows, fit_lightgbm


def fit_predict(train, test):
    predictions = {}
    for bucket in PRICE:
        rows, weight = training_rows(train, bucket)
        params = dict(PARAMS[bucket], objective='gamma')   # gamma has its own log link: no offset
        models = fit_lightgbm(rows, rows[PRICE[bucket]], weight, params)
        predictions[bucket] = np.mean([model.predict(test[FEATURES]) for model in models], axis=0)
    return pd.DataFrame(predictions, index=test.index)

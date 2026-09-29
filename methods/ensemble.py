"""LightGBM + XGBoost + CatBoost, averaged in log space - the model that was last deployed.

All three learn the same thing: the correction on top of lgbm.py's offset, with the same
sample weights. XGBoost and CatBoost use fixed, untuned settings.
"""
import numpy as np
import pandas as pd
import xgboost
import catboost

from prepare import CATEGORICAL, FEATURES, PRICE
from methods.lgbm import predict_log


def as_strings(tanks):
    frame = tanks[FEATURES].copy()
    frame[CATEGORICAL] = frame[CATEGORICAL].astype(str)
    return frame


def fit_predict(train, test):
    predictions = {}
    for bucket in PRICE:
        lgbm_log, rows, weight, offset = predict_log(train, test, bucket)
        target = np.log(rows[PRICE[bucket]]) - (0.0 if offset is None else offset(rows))
        test_offset = 0.0 if offset is None else offset(test)

        xgb = xgboost.XGBRegressor(n_estimators=600, learning_rate=0.05, max_depth=6,
                                   subsample=0.8, colsample_bytree=0.8, tree_method='hist',
                                   objective='reg:absoluteerror', enable_categorical=True,
                                   random_state=0)
        xgb.fit(rows[FEATURES], target, sample_weight=weight)

        cat = catboost.CatBoostRegressor(iterations=800, learning_rate=0.05, depth=7,
                                         loss_function='MAE', random_seed=0, verbose=0,
                                         allow_writing_files=False, cat_features=CATEGORICAL)
        cat.fit(as_strings(rows), target, sample_weight=weight)

        xgb_log = xgb.predict(test[FEATURES]) + test_offset
        cat_log = cat.predict(as_strings(test)) + test_offset
        predictions[bucket] = np.exp((lgbm_log + xgb_log + cat_log) / 3)
    return pd.DataFrame(predictions, index=test.index)

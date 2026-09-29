"""LightGBM on log price, one model per bucket - the old production recipe, dollar-weighted.

Per bucket: start from a simple size-and-grade guess (the "offset"), let LightGBM learn the
correction, weight each tank by its dollars, add older revisions at half weight, average 4 seeds.
"""
import numpy as np
import pandas as pd
import lightgbm

from prepare import FEATURES, PRICE

SEEDS = 4
REVISION_WEIGHT = 0.5   # older revisions of a quote are real prices too, just less final

# The offset: log(area) + a typical log($/sqft) for the tank's group. The group level is
# shrunk toward the overall level when the group is small. None = no group, area only.
OFFSET_GROUP = {'material': 'Material', 'fabrication': 'Material', 'construction': 'Wage Type',
                'insul_material': 'Material', 'insul_construction': None}
OFFSET_SHRINK = {'material': 6.2, 'fabrication': 24.8, 'construction': 7.0,
                 'insul_material': 64.8, 'insul_construction': 114.9}

# Tuned with Optuna on this recipe.
PARAMS = {
    'material': dict(objective='regression_l1', learning_rate=0.0749, num_leaves=162,
                     min_data_in_leaf=40, feature_fraction=0.413, bagging_fraction=0.950,
                     lambda_l1=3.26, lambda_l2=0.0247, cat_smooth=71.2, cat_l2=13.5,
                     max_cat_threshold=51, num_boost_round=402),
    'fabrication': dict(objective='regression_l1', learning_rate=0.0309, num_leaves=28,
                        min_data_in_leaf=21, feature_fraction=0.488, bagging_fraction=0.855,
                        lambda_l1=0.208, lambda_l2=0.00321, cat_smooth=15.4, cat_l2=1.08,
                        max_cat_threshold=30, num_boost_round=1104),
    'construction': dict(objective='regression_l1', learning_rate=0.0445, num_leaves=164,
                         min_data_in_leaf=39, feature_fraction=0.455, bagging_fraction=0.664,
                         lambda_l1=0.165, lambda_l2=0.000322, cat_smooth=26.0, cat_l2=32.4,
                         max_cat_threshold=60, num_boost_round=452),
    'insul_material': dict(objective='regression_l1', learning_rate=0.0185, num_leaves=49,
                           min_data_in_leaf=19, feature_fraction=0.431, bagging_fraction=0.842,
                           lambda_l1=0.0713, lambda_l2=0.00663, cat_smooth=50.1, cat_l2=6.05,
                           max_cat_threshold=47, num_boost_round=508),
    'insul_construction': dict(objective='huber', learning_rate=0.0299, num_leaves=149,
                               min_data_in_leaf=9, feature_fraction=0.630, bagging_fraction=0.556,
                               lambda_l1=0.000472, lambda_l2=2.83, cat_smooth=2.00, cat_l2=21.8,
                               max_cat_threshold=45, num_boost_round=642),
}


def training_rows(train, bucket):
    """Tanks that have a price in this bucket, and a sample weight for each."""
    rows = train[train[PRICE[bucket]] > 0]
    price = rows[PRICE[bucket]].to_numpy()
    # Weight by dollars: a $2M tank counts 100x a $20K one, because dollars are what we are
    # judged on. Weaker weighting on some buckets bought % accuracy and lost dollars.
    weight = price / np.median(price)
    weight *= np.where(rows['is_firmest'] == 1, 1.0, REVISION_WEIGHT)
    weight /= weight.mean()
    # One corrupt price can get a giant weight. A $1.19 trillion row once reached training.
    assert weight.max() / np.median(weight) < 5000, f'{bucket}: absurd sample weight'
    return rows, weight


def fit_offset(rows, bucket):
    """Return a function tanks -> log-price starting guess, or None if the bucket has none.

    It must stay a LEVEL. A time trend in here extrapolates past the training dates and
    was measured to blow up (material bias -22% two quarters out)."""
    group = OFFSET_GROUP[bucket]
    if group is None:
        return None
    log_rate = np.log(rows[PRICE[bucket]]) - np.log(rows['total_area_sqft'])
    overall = log_rate.median()
    stats = log_rate.groupby(rows[group].astype(str)).agg(['median', 'size'])
    trust = stats['size'] / (stats['size'] + OFFSET_SHRINK[bucket])
    level = trust * stats['median'] + (1 - trust) * overall

    def offset(tanks):
        tank_level = tanks[group].astype(str).map(level).fillna(overall).to_numpy()
        return np.log(tanks['total_area_sqft'].to_numpy()) + tank_level
    return offset


def fit_lightgbm(rows, target, weight, params, init_score=None):
    models = []
    for seed in range(SEEDS):
        # init_score must be None when there is no offset - an all-zero array switches off
        # LightGBM's starting average, and under L1 it then learns nothing at all.
        data = lightgbm.Dataset(rows[FEATURES], target, weight=weight, init_score=init_score)
        model = lightgbm.train(dict(params, seed=seed, verbose=-1, bagging_freq=1), data)
        assert model.num_trees() > 0, 'model learned nothing - check init_score'
        models.append(model)
    return models


def predict_log(train, test, bucket):
    """Log-dollar prediction for each test tank, plus the offset (reused by ensemble.py)."""
    rows, weight = training_rows(train, bucket)
    offset = fit_offset(rows, bucket)
    train_offset = None if offset is None else offset(rows)
    test_offset = 0.0 if offset is None else offset(test)
    models = fit_lightgbm(rows, np.log(rows[PRICE[bucket]]), weight, PARAMS[bucket], train_offset)
    raw = np.mean([model.predict(test[FEATURES]) for model in models], axis=0)
    return raw + test_offset, rows, weight, offset


def fit_predict(train, test):
    return pd.DataFrame({bucket: np.exp(predict_log(train, test, bucket)[0]) for bucket in PRICE},
                        index=test.index)

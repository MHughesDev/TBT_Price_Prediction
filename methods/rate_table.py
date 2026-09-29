"""The baseline every model must beat: a price-per-square-foot lookup.

For each bucket and material grade, the median $/sqft of past tanks, times this tank's area.
"""
import pandas as pd

from prepare import PRICE


def fit_predict(train, test):
    train = train[train['is_firmest'] == 1]
    grade = test['Material'].astype(str)
    predictions = {}
    for bucket, column in PRICE.items():
        rows = train[train[column] > 0]
        rate = rows[column] / rows['total_area_sqft']
        rate_by_grade = rate.groupby(rows['Material'].astype(str)).median()
        test_rate = grade.map(rate_by_grade).fillna(rate.median())
        predictions[bucket] = test_rate * test['total_area_sqft']
    return pd.DataFrame(predictions, index=test.index)

"""Every competing method. Each one is a file with fit_predict(train, test) -> DataFrame of
predicted dollars, one column per bucket. To add a contender, add a file and one line here."""
from methods import rate_table, lgbm, lgbm_gamma, ensemble

METHODS = {
    'rate_table': rate_table.fit_predict,
    'lgbm': lgbm.fit_predict,
    'lgbm_gamma': lgbm_gamma.fit_predict,
    'ensemble': ensemble.fit_predict,
}

"""Loads the leakage-free exports and defines the feature contract the models consume."""
import pathlib
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
ROOT = str(pathlib.Path(__file__).resolve().parents[1])
TARGETS = ['target_material', 'target_fabrication', 'target_construction',
           'target_insul_material', 'target_insul_construction']


def load(which='training'):
    D = pd.read_parquet(str(pathlib.Path(ROOT) / 'exports' / f'{which}.parquet')).copy()
    for t in TARGETS:
        D[t] = np.where(D[t] <= 1, 0.0, D[t])
    D['Due Date'] = pd.to_datetime(D['Due Date'])
    D['_group'] = D['QuoteGroupID'].astype(str)
    D['t_month'] = (D['Due Date'].dt.year - 2020) * 12 + D['Due Date'].dt.month
    D['t_month'] = D.t_month.fillna(D.t_month.median()).astype(int)
    D['t_q'] = D['Due Date'].dt.to_period('Q')
    D['t_year'] = D['Due Date'].dt.year.fillna(2025)
    # scope gates reconstructed as LABELS (the app supplies the equivalent as an input)
    D['gate_construction'] = (D.target_construction > 0).astype(int)
    D['gate_insul'] = (D.target_insul_material > 0).astype(int)
    return D


MAN = pd.read_csv(str(pathlib.Path(ROOT) / 'exports' / 'column_manifest.csv'))
FEATURES_ALL = MAN.loc[MAN.role == 'feature', 'column'].tolist()


def feature_cols(D, extra=(), drop=()):
    cols = [c for c in FEATURES_ALL if c in D.columns and c not in drop]
    return cols + [c for c in extra if c in D.columns and c not in cols]


def Xy(D, cols, target):
    cols = [c for c in cols if c in D.columns]
    X = D[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ('str', 'string'):
            X[c] = X[c].astype('category')
        elif str(X[c].dtype) == 'boolean':
            X[c] = X[c].astype(float)
    return X, D[target]


def metrics(y, p):
    y = np.asarray(y, float); p = np.maximum(np.asarray(p, float), 0.0)
    m = y > 0
    ape = np.abs(p[m] - y[m]) / y[m]
    return dict(n=int(m.sum()), MdAPE=float(np.median(ape)), MAPE=float(ape.mean()),
                w10=float((ape <= .10).mean()), w20=float((ape <= .20).mean()),
                bias=float(np.median(p[m] / y[m]) - 1),
                wMAPE=float(np.abs(p[m] - y[m]).sum() / y[m].sum()))


def fmt(rows):
    df = pd.DataFrame(rows)
    for c in ['MdAPE', 'MAPE', 'w10', 'w20', 'bias', 'wMAPE']:
        if c in df:
            df[c] = df[c].map(lambda x: f'{x:6.3f}')
    return df.to_string(index=False)

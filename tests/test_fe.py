"""交替投影的雙向固定效應：與「直接放虛擬變數」的 OLS 比對。"""
import numpy as np
import pandas as pd

from fe import demean, fit_twfe


def make_panel(seed=0, n_entity=30, n_time=40):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame([(i, t) for i in range(n_entity) for t in range(n_time)], columns=["e", "t"])
    d = d.sample(frac=0.8, random_state=seed).reset_index(drop=True)   # 不平衡面板
    d["x"] = rng.normal(size=len(d)) + 0.3 * d["e"]                   # x 與固定效應相關
    d["y"] = 2.0 * d["x"] + 0.5 * d["e"] - 0.1 * d["t"] + rng.normal(size=len(d))
    d["cl"] = d["e"] % 5
    return d


def test_matches_dummy_variable_ols():
    d = make_panel()
    X = pd.get_dummies(d[["e", "t"]].astype(str), drop_first=True).astype(float)
    X.insert(0, "x", d["x"])
    X.insert(0, "const", 1.0)
    beta_dummy = np.linalg.lstsq(X.to_numpy(), d["y"].to_numpy(), rcond=None)[0][1]

    res = fit_twfe(d, "y", ["x"], "e", "t", "cl")
    assert np.isclose(res.loc["x", "係數"], beta_dummy, atol=1e-8)


def test_demean_removes_both_group_means():
    d = make_panel(seed=1)
    groups = [pd.factorize(d["e"])[0], pd.factorize(d["t"])[0]]
    z = demean(d["y"].to_numpy(), groups)[:, 0]
    assert np.abs(pd.Series(z).groupby(d["e"]).mean()).max() < 1e-8
    assert np.abs(pd.Series(z).groupby(d["t"]).mean()).max() < 1e-8


def test_drops_missing_rows():
    d = make_panel(seed=2)
    d.loc[:9, "x"] = np.nan
    res = fit_twfe(d, "y", ["x"], "e", "t", "cl")
    assert res.attrs["nobs"] == len(d) - 10
    assert res.attrs["clusters"] == 5

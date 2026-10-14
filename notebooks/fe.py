"""雙向固定效應 + cluster 標準誤，以交替投影（alternating projections）實作。

linearmodels 在 8/31 之後的面板（700 萬列 × 1,777 站 × 4,000 個時段）上
需要超過 6 GB 記憶體。依 Frisch–Waugh–Lovell 定理，先對兩組固定效應反覆去平均、
再對殘差跑 OLS，係數與虛擬變數迴歸相同，記憶體只需數個與樣本等長的陣列。

在 8/20–8/28 的資料上與 linearmodels.PanelOLS 的係數一致（見 tests/test_fe.py 與 notebook）。
"""
import numpy as np
import pandas as pd
from scipy import stats


def _codes(s):
    return pd.factorize(s, sort=False)[0]


def demean(M, groups, tol=1e-10, max_iter=1000):
    """對 M 的每一欄，依序減去各組平均，直到收斂。M 會被複製，不修改輸入。"""
    M = np.array(M, dtype=float, copy=True)
    if M.ndim == 1:
        M = M[:, None]
    counts = [np.bincount(g) for g in groups]
    for _ in range(max_iter):
        delta = 0.0
        for g, n in zip(groups, counts):
            for j in range(M.shape[1]):
                means = np.bincount(g, weights=M[:, j]) / n
                M[:, j] -= means[g]
                delta = max(delta, np.abs(means).max())
        if delta < tol:
            return M
    raise RuntimeError(f"demean 未在 {max_iter} 次內收斂（delta={delta:.2e}）")


def fit_twfe(df, y, x, entity, time, cluster):
    """回傳係數表（DataFrame）與樣本數。

    cluster 為單一欄位名稱；標準誤為 CR1（G/(G-1) 校正），p 值以 t(G-1) 計算，
    cluster 數少時較常態近似保守。
    """
    d = df[[y, *x, entity, time, cluster]].dropna()
    groups = [_codes(d[entity]), _codes(d[time])]
    Z = demean(d[[y, *x]].to_numpy(), groups)
    yd, Xd = Z[:, 0], Z[:, 1:]

    XtX_inv = np.linalg.inv(Xd.T @ Xd)
    beta = XtX_inv @ Xd.T @ yd
    e = yd - Xd @ beta

    c = _codes(d[cluster])
    G = c.max() + 1
    scores = np.column_stack([np.bincount(c, weights=Xd[:, j] * e, minlength=G)
                              for j in range(Xd.shape[1])])
    V = XtX_inv @ (scores.T @ scores) @ XtX_inv * G / (G - 1)
    se = np.sqrt(np.diag(V))

    t = beta / se
    out = pd.DataFrame({
        "係數": beta, "標準誤": se, "p 值": 2 * stats.t.sf(np.abs(t), df=G - 1),
    }, index=x)
    out.attrs.update(nobs=len(d), clusters=G)
    return out

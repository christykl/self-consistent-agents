"""Is o4-mini hacking predictable from Qwen3-4B's representation of the task prompt alone?

    python -m probe.probe --features probe/features_qwen3_4b.npz

L2 logistic regression on mean-pooled prompt features -> per-rollout outcome, with grouped 5-fold
CV over problems (a problem's rollouts never split across train/test).  Reports AUC / Brier /
accuracy vs the base rate and a shuffled-features control.  Targets: hack, success (legit solve).
"""
import argparse

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from probe.labels import NO_ASK_RUNS, load_rollouts


def cv_predict(X, y, groups, folds):
    """Out-of-fold probabilities from grouped CV; C chosen by an inner grouped CV, features standardized."""
    pred = np.zeros(len(y))
    for train, test in GroupKFold(folds).split(X, y, groups):
        clf = GridSearchCV(make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
                           {"logisticregression__C": [1e-4, 1e-3, 1e-2, 1e-1, 1.0]},
                           cv=GroupKFold(3), scoring="roc_auc")
        clf.fit(X[train], y[train], groups=groups[train])
        pred[test] = clf.predict_proba(X[test])[:, 1]
    return pred


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--features", required=True)
    p.add_argument("--runs", nargs="+", default=NO_ASK_RUNS)
    p.add_argument("--folds", type=int, default=5)
    args = p.parse_args()

    f = np.load(args.features)
    feat = dict(zip(f["ids"], f["X"]))
    rows = [r for r in load_rollouts(args.runs) if r[0] in feat]
    X = np.stack([feat[r[0]] for r in rows])
    groups = np.array([r[0] for r in rows])
    print(f"{len(rows)} rollouts on {len(set(groups))} problems, {X.shape[1]}-dim features")

    for name, col in [("hack", 3), ("success", 4)]:
        y = np.array([r[col] for r in rows], dtype=int)
        if y.min() == y.max():
            print(f"{name}: constant ({y.mean():.3f}), skipped")
            continue
        pred = cv_predict(X, y, groups, args.folds)
        base = y.mean()
        print(f"{name}: {y.sum()} positives, base rate {base:.3f} | probe AUC {roc_auc_score(y, pred):.3f}, Brier {np.mean((pred - y) ** 2):.3f} "
              f"(base-rate Brier {base * (1 - base):.3f}), accuracy {np.mean((pred >= 0.5) == y):.3f} (majority {max(base, 1 - base):.3f})")
        tids = sorted(set(groups)); aucs = []
        for seed in range(5):
            perm = dict(zip(tids, np.random.default_rng(seed).permutation(tids)))
            aucs.append(roc_auc_score(y, cv_predict(np.stack([feat[perm[t]] for t in groups]), y, groups, args.folds)))
        print(f"   shuffled-features control: AUC {np.mean(aucs):.3f} +- {np.std(aucs):.3f} over 5 shuffles")
        rate = np.array([y[groups == t].mean() for t in tids]); ppred = np.array([pred[groups == t].mean() for t in tids])
        print(f"   per-problem correlation(probe, empirical rate) = {np.corrcoef(ppred, rate)[0, 1]:.3f}")
    print("caveat: few hack positives -> wide AUC uncertainty; compare against the shuffled control")


if __name__ == "__main__":
    main()

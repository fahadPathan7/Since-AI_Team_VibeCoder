import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.config import (BINARY_L4, BINARY_XT, CLASS_LAYOUTS, CORE, DRIVER_FEATURES, HORIZON_STEPS, LOGIT_C, LOGIT_FEATURES,
                        MIN_LEAF_FLOOR, PRICE_FEATURES_DECAY, PRICE_LAYOUTS, QUANTILE, REFERENCE, SEEDS, SPIKE_FEATURES,
                        SPIKE_MARGIN)

QUANTILES = {"q10": 0.1, "q50": 0.5, "q90": 0.9}


# Minimum leaf size scaled to the share of steps in a bucket
def bucket_settings(settings, low, high, floor):
    share = (high - low + 1) / HORIZON_STEPS
    return dict(settings, min_child_samples=max(floor, int(settings["min_child_samples"] * share)))


# Rows whose step falls in a bucket
def in_bucket(rows, low, high):
    return ((rows["step"] >= low) & (rows["step"] <= high)).to_numpy()


# Train one quantile model per seed on the spread
def fit_quantile(train, features, alpha, settings, seeds):
    return [lgb.LGBMRegressor(alpha=alpha, random_state=seed, **settings).fit(train[features], train["y_spread"]) for seed in seeds]


# Train one binary model per seed
def fit_binary(rows, labels, features, settings, seeds):
    return [lgb.LGBMClassifier(random_state=seed, **settings).fit(rows[features], labels) for seed in seeds]


# Train the logistic direction model with percentile clipping from training rows
def fit_logit(rows, labels):
    lower, upper = rows[LOGIT_FEATURES].quantile(0.005), rows[LOGIT_FEATURES].quantile(0.995)
    pipeline = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=LOGIT_C, max_iter=500))
    pipeline.fit(rows[LOGIT_FEATURES].clip(lower, upper, axis=1), labels)
    return {"pipeline": pipeline, "lower": lower, "upper": upper}


# Price models for every bucket of every price layout
def fit_price(train, seeds):
    models = []
    for buckets, features in PRICE_LAYOUTS:
        for low, high in buckets:
            part = train[in_bucket(train, low, high)]
            settings = bucket_settings(QUANTILE, low, high, MIN_LEAF_FLOOR["quantile"])
            fitted = {name: fit_quantile(part, features, alpha, settings, seeds) for name, alpha in QUANTILES.items()}
            models.append({"low": low, "high": high, "features": features, **fitted})
    return models


# Spike and direction models for every bucket of every classifier layout
def fit_classifiers(train, seeds):
    models = []
    for buckets in CLASS_LAYOUTS:
        for low, high in buckets:
            part = train[in_bucket(train, low, high)]
            l4 = bucket_settings(BINARY_L4, low, high, MIN_LEAF_FLOOR["binary_l4"])
            xt = bucket_settings(BINARY_XT, low, high, MIN_LEAF_FLOOR["binary_xt"])
            directional = part[part["y_dir"] != 0]
            up = (directional["y_dir"] == 1).astype(int)
            models.append({
                "low": low, "high": high,
                "spike_high": fit_binary(part, (part["y_spread"] > SPIKE_MARGIN).astype(int), SPIKE_FEATURES, l4, seeds),
                "spike_low": fit_binary(part, (part["y_spread"] < -SPIKE_MARGIN).astype(int), SPIKE_FEATURES, l4, seeds),
                "up_l4": fit_binary(directional, up, CORE, l4, seeds),
                "up_xt": fit_binary(directional, up, CORE, xt, seeds),
                "up_logit": fit_logit(directional, up),
            })
    return models


# Train every model of the design on rows with usable labels
def fit_all(train, seeds=SEEDS):
    assert train["y_price"].notna().all(), "training rows need usable labels"
    assert not set(REFERENCE) & set(PRICE_FEATURES_DECAY + SPIKE_FEATURES + LOGIT_FEATURES), "reference column used as a feature"
    return {"price": fit_price(train, seeds), "classifiers": fit_classifiers(train, seeds)}


# Average the positive-class probability across seeds
def mean_probability(group, rows, features):
    return np.mean([model.predict_proba(rows[features])[:, 1] for model in group], axis=0)


# Predict raw spread quantiles and probabilities before post-processing, averaged over layouts
def predict_all(models, rows):
    raw = {name: np.zeros(len(rows)) for name in [*QUANTILES, "p_high", "p_low", "p_up_raw"]}
    for model in models["price"]:
        mask = in_bucket(rows, model["low"], model["high"])
        part = rows.loc[mask, model["features"]]
        for name in QUANTILES:
            raw[name][mask] += np.mean([m.predict(part) for m in model[name]], axis=0) / len(PRICE_LAYOUTS)
    for model in models["classifiers"]:
        mask = in_bucket(rows, model["low"], model["high"])
        part = rows[mask]
        logit = model["up_logit"]
        clipped = part[LOGIT_FEATURES].clip(logit["lower"], logit["upper"], axis=1)
        raw["p_high"][mask] += mean_probability(model["spike_high"], part, SPIKE_FEATURES) / len(CLASS_LAYOUTS)
        raw["p_low"][mask] += mean_probability(model["spike_low"], part, SPIKE_FEATURES) / len(CLASS_LAYOUTS)
        up = (mean_probability(model["up_l4"], part, CORE) + mean_probability(model["up_xt"], part, CORE)
              + logit["pipeline"].predict_proba(clipped)[:, 1]) / 3
        raw["p_up_raw"][mask] += up / len(CLASS_LAYOUTS)
    return pd.DataFrame(raw, index=rows.index)


# Average SHAP contributions of the p50 models across seeds and layouts, without the bias term
def p50_contributions(models, rows):
    columns = {name: i for i, name in enumerate(DRIVER_FEATURES)}
    total = np.zeros((len(rows), len(DRIVER_FEATURES)))
    for model in models["price"]:
        mask = in_bucket(rows, model["low"], model["high"])
        contrib = np.mean([m.predict(rows.loc[mask, model["features"]], pred_contrib=True)[:, :-1] for m in model["q50"]], axis=0)
        positions = [columns[name] for name in model["features"]]
        total[np.ix_(np.flatnonzero(mask), positions)] += contrib / len(PRICE_LAYOUTS)
    return total


# Name the three largest contributions on each row
def top_drivers(contributions, count=3):
    names = np.array(DRIVER_FEATURES)
    order = np.argsort(-np.abs(contributions), axis=1)[:, :count]
    return [";".join(row) for row in names[order]]


# Mean absolute contribution of each feature to the p50 model
def global_importance(contributions):
    table = pd.DataFrame({"feature": DRIVER_FEATURES, "mean_abs_contribution": np.abs(contributions).mean(axis=0)})
    return table.sort_values("mean_abs_contribution", ascending=False, ignore_index=True)

"""Scoring against the ground truth the generator kept back."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _pairs(sizes: pd.Series) -> float:
    s = sizes.to_numpy(dtype=float)
    return float((s * (s - 1) / 2).sum())


def pairwise(labels: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    """Precision, recall and F1 over all record pairs placed in the same party."""
    frame = pd.DataFrame({"party": labels, "person": truth})
    predicted = _pairs(frame.groupby("party").size())
    actual = _pairs(frame.groupby("person").size())
    correct = _pairs(frame.groupby(["party", "person"]).size())
    precision = correct / predicted if predicted else 1.0
    recall = correct / actual if actual else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "predicted_pairs": predicted, "true_pairs": actual, "correct_pairs": correct}


def party_errors(labels: np.ndarray, truth: np.ndarray, balance: np.ndarray) -> dict[str, float]:
    """What the errors mean for a single customer view.

    - ``false_merge_parties``: parties holding records of more than one real person
    - ``people_in_false_merges``: real people who share a party with someone else
    - ``people_split``: real people whose records are spread over more than one party
    - ``exposure_wrong``: share of multi-record people whose total exposure, read off the party that
      holds their largest balance, is off by more than 1%
    - ``exposure_understated_rand``: total balance missing from those parties because of splits
    """
    frame = pd.DataFrame({"party": labels, "person": truth, "balance": balance})
    persons_per_party = frame.groupby("party")["person"].nunique()
    merged_parties = persons_per_party[persons_per_party > 1].index
    people_in_merges = frame[frame["party"].isin(merged_parties)]["person"].nunique()
    parties_per_person = frame.groupby("person")["party"].nunique()
    split_people = int((parties_per_person > 1).sum())

    true_exposure = frame.groupby("person")["balance"].sum()
    party_exposure = frame.groupby("party")["balance"].sum()
    anchor = frame.sort_values("balance", ascending=False).drop_duplicates("person").set_index("person")
    seen = party_exposure.reindex(anchor["party"]).to_numpy()
    true = true_exposure.reindex(anchor.index).to_numpy()
    multi = frame.groupby("person").size().reindex(anchor.index).to_numpy() > 1
    wrong = np.abs(seen - true) > 0.01 * true
    own_share = frame.groupby(["person", "party"])["balance"].sum()
    held = own_share.reindex(list(zip(anchor.index, anchor["party"], strict=True))).to_numpy()
    understated = float(np.clip(true - held, 0, None).sum())
    return {
        "parties": int(frame["party"].nunique()),
        "people": int(frame["person"].nunique()),
        "false_merge_parties": len(merged_parties),
        "people_in_false_merges": int(people_in_merges),
        "people_split": split_people,
        "multi_record_people": int(multi.sum()),
        "exposure_wrong_multi": float(wrong[multi].mean()) if multi.any() else 0.0,
        "exposure_wrong_people": int(wrong.sum()),
        "exposure_understated_rand": understated,
    }

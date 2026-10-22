"""Pure speaker-vector rules and provider availability error."""

import math


class SpeakerUnavailable(Exception):
    pass


def similarity(left, right):
    if not left or len(left) != len(right):
        return -1.0
    ln = math.sqrt(sum(v * v for v in left))
    rn = math.sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / (ln * rn) if ln and rn else -1.0


def centroid(vectors):
    vector = [sum(column) / len(vectors) for column in zip(*vectors, strict=False)]
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise ValueError("录入样本不一致，请重新录入")
    return [v / norm for v in vector]


def identify(
    vector,
    model_id,
    profiles,
    threshold=0.65,
    margin=0.12,
    *,
    diagnostics=False,
):
    # Provisional conservative gates, not accuracy claims or authorization.
    ranked = sorted(
        [
            (similarity(vector, p["embedding"]), p)
            for p in profiles
            if p["model_id"] == model_id and p["status"] == "active"
        ],
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked:
        result = {"status": "unknown"}
        if diagnostics:
            result.update(
                {
                    "candidate_count": 0,
                    "best_similarity": None,
                }
            )
        return result
    best, profile = ranked[0]
    if best < threshold:
        result = {"status": "unknown"}
        if diagnostics:
            result.update(
                {
                    "candidate_count": len(ranked),
                    "best_similarity": best,
                }
            )
        return result
    if len(ranked) > 1 and best - ranked[1][0] < margin:
        result = {"status": "uncertain"}
        if diagnostics:
            result.update(
                {
                    "candidate_count": len(ranked),
                    "best_similarity": best,
                }
            )
        return result
    result = {
        "status": "matched",
        "person_id": profile["person_id"],
        "display_name": profile["display_name"],
        "similarity": best,
    }
    if diagnostics:
        result.update(
            {
                "candidate_count": len(ranked),
                "best_similarity": best,
            }
        )
    return result
